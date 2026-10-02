"""Receipt photos end to end (aurum/ingest/receipts.py + router + pf attachment).

The OCR engine is faked for the deterministic tests (``receipt_ocr.ocr_image``); one test runs the
real Tesseract CLI on a drawn ticket and is skipped where Tesseract is not installed.
"""

from __future__ import annotations

import io
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient
from PIL import Image, ImageDraw, ImageFont

from aurum.api.app import create_app
from aurum.core.config import settings
from aurum.core.workspaces import Workspace, save_workspace
from aurum.ingest import receipt_ocr, receipts
from aurum.ingest.receipt_ocr import OcrResult

WS = "rcp-ws"
TODAY = date.today()
TICKET = f"""OXXO
CADENA COMERCIAL OXXO SA DE CV
FECHA: {TODAY:%d/%m/%Y} 18:42
SUBTOTAL 68.53
IVA 16% 10.97
TOTAL 79.50
EFECTIVO 100.00
CAMBIO 20.50"""


def _jpeg(with_gps: bool = False, size=(600, 900)) -> bytes:
    img = Image.new("RGB", size, (250, 248, 240))
    buf = io.BytesIO()
    if with_gps:
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"  # Make
        exif[0x8825] = {1: "N", 2: (25.0, 40.0, 0.0)}  # GPSInfo
        img.save(buf, "JPEG", exif=exif)
    else:
        img.save(buf, "JPEG")
    return buf.getvalue()


@pytest.fixture()
def client(monkeypatch) -> TestClient:
    save_workspace(Workspace(id=WS, name="Recibos", base_currency="MXN", jurisdictions=["MX"]))
    monkeypatch.setattr(receipt_ocr, "ocr_image", lambda path: OcrResult(TICKET, "tesseract", True, None, 0.1))
    c = TestClient(create_app())
    r = c.post(f"/api/pf/{WS}/accounts", json={"name": "Efectivo", "type": "cash"})
    assert r.status_code == 200, r.text
    c.account_id = r.json()["id"]  # type: ignore[attr-defined]
    return c


def _scan(client: TestClient, data: bytes | None = None, name: str = "ticket.jpg") -> dict:
    r = client.post(f"/api/ingest/{WS}/receipts", files={"file": (name, data or _jpeg(), "image/jpeg")})
    assert r.status_code == 200, r.text
    return r.json()


def _label_id(client: TestClient, name: str) -> str:
    labels = client.get(f"/api/pf/{WS}/labels", params={"kind": "expense"}).json()
    return next(lbl["id"] for lbl in labels if lbl["name"] == name)


def test_scan_suggests_amount_date_shop_and_category(client) -> None:
    body = _scan(client)
    s = body["suggestion"]
    assert s["amount"] == {"amount": "79.50", "currency": "MXN"}
    assert s["date"] == TODAY.isoformat()
    assert s["payee"] == "OXXO"
    assert s["label_name"] == "Súper" and s["label_id"] == _label_id(client, "Súper")
    assert s["confidence"] == {"amount": "high", "date": "high", "payee": "high", "label": "high"}
    assert any("TOTAL 79.50" in r for r in body["reasons"])
    assert any("subtotal" in r.lower() for r in body["reasons"])
    assert body["message"] is None
    assert body["ocr"]["engine"] == "tesseract" and body["ocr"]["chars"] > 0


def test_photo_is_kept_without_exif_and_served(client) -> None:
    body = _scan(client, _jpeg(with_gps=True, size=(3000, 4000)))
    rid = body["receipt"]["id"]
    path = settings().workspace_dir(WS) / "docs" / "receipts" / f"{rid}.jpg"
    assert path.is_file()
    with Image.open(path) as im:
        assert max(im.size) <= receipts.MAX_SIDE
        assert len(im.getexif()) == 0  # GPS and maker gone
    img = client.get(f"/api/ingest/{WS}/receipts/{rid}/image")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert img.content == path.read_bytes()
    assert client.get(f"/api/ingest/{WS}/receipts/rcp-000000000000/image").status_code == 404
    assert client.get(f"/api/ingest/{WS}/receipts/..%2F..%2Fworkspace.json/image").status_code in (400, 404)
    again = client.get(f"/api/ingest/{WS}/receipts/{rid}").json()
    assert again["suggestion"]["amount"]["amount"] == "79.50"


def test_non_images_and_heic_are_refused_with_a_plain_message(client) -> None:
    r = client.post(f"/api/ingest/{WS}/receipts", files={"file": ("x.pdf", b"%PDF-1.7 hello", "application/pdf")})
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "unsupported_image"
    heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 32
    r = client.post(f"/api/ingest/{WS}/receipts", files={"file": ("x.heic", heic, "image/heic")})
    assert r.status_code == 400 and "HEIC" in r.json()["detail"]["message"]
    r = client.post(f"/api/ingest/{WS}/receipts", files={"file": ("x.jpg", b"", "image/jpeg")})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "empty_file"


def test_last_choice_for_the_same_shop_wins(client) -> None:
    comida = _label_id(client, "Comida fuera")
    r = client.post(
        f"/api/pf/{WS}/entries",
        json={"kind": "expense", "date": TODAY.isoformat(), "amount": {"amount": "50", "currency": "MXN"},
              "account_id": client.account_id, "label_id": comida, "payee": "Oxxo"},
    )
    assert r.status_code == 200, r.text
    s = _scan(client)["suggestion"]
    assert s["label_id"] == comida and s["confidence"]["label"] == "high"


def test_movement_keeps_the_receipt(client) -> None:
    rid = _scan(client)["receipt"]["id"]
    super_id = _label_id(client, "Súper")
    r = client.post(
        f"/api/pf/{WS}/entries",
        json={"kind": "expense", "date": TODAY.isoformat(), "amount": {"amount": "79.50", "currency": "MXN"},
              "account_id": client.account_id, "label_id": super_id, "payee": "OXXO", "attachment": rid},
    )
    assert r.status_code == 200, r.text
    entry = r.json()
    assert entry["attachment"] == rid
    edited = client.put(f"/api/pf/{WS}/entries/{entry['id']}", json={"note": "refrescos"}).json()
    assert edited["attachment"] == rid  # an edit keeps the photo
    listed = client.get(f"/api/pf/{WS}/entries").json()["entries"]
    assert listed[0]["attachment"] == rid
    bad = client.post(
        f"/api/pf/{WS}/entries",
        json={"kind": "expense", "date": TODAY.isoformat(), "amount": {"amount": "1", "currency": "MXN"},
              "account_id": client.account_id, "attachment": "rcp-ffffffffffff"},
    )
    assert bad.status_code == 404


def test_scanning_the_same_ticket_twice_warns(client) -> None:
    photo = _jpeg()
    first = _scan(client, photo)
    assert first["duplicate"] is None
    r = client.post(
        f"/api/pf/{WS}/entries",
        json={"kind": "expense", "date": TODAY.isoformat(), "amount": {"amount": "79.50", "currency": "MXN"},
              "account_id": client.account_id, "payee": "OXXO", "attachment": first["receipt"]["id"]},
    )
    assert r.status_code == 200, r.text
    same = _scan(client, photo)
    assert same["duplicate"]["entry_id"] == r.json()["id"] and same["duplicate"]["same_photo"] is True
    other_photo = _scan(client, _jpeg(size=(610, 900)))  # a new picture of the same ticket
    assert other_photo["duplicate"]["entry_id"] == r.json()["id"]
    assert other_photo["duplicate"]["same_photo"] is False
    assert other_photo["duplicate"]["amount"] == {"amount": "79.50", "currency": "MXN"}


def test_workspace_backup_carries_the_photo(client) -> None:
    rid = _scan(client)["receipt"]["id"]
    z = client.get(f"/api/workspaces/{WS}/backup.zip")
    assert z.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert f"docs/receipts/{rid}.jpg" in names


def test_ocr_off_keeps_the_photo_and_says_so(client, monkeypatch) -> None:
    monkeypatch.setattr(receipt_ocr, "ocr_image", lambda path: OcrResult("", None, False, "ocr_off", 0.0))
    body = _scan(client)
    assert body["suggestion"] is None
    assert body["message"] and "a mano" in body["message"]
    assert (settings().workspace_dir(WS) / "docs" / "receipts" / f"{body['receipt']['id']}.jpg").is_file()


@pytest.mark.skipif(receipt_ocr.tesseract_cmd() is None, reason="Tesseract is not installed on this machine")
def test_real_tesseract_reads_a_drawn_ticket(monkeypatch) -> None:
    monkeypatch.setenv("AURUM_OCR_BACKEND", "tesseract")
    save_workspace(Workspace(id=WS, name="Recibos", base_currency="MXN", jurisdictions=["MX"]))
    font = ImageFont.load_default(size=30)
    lines = TICKET.splitlines()
    img = Image.new("RGB", (820, 60 + 44 * len(lines)), (250, 248, 240))
    draw = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        draw.text((40, 30 + 44 * i), line, fill=(30, 30, 30), font=font)
    buf = io.BytesIO()
    img.rotate(1.2, expand=True, fillcolor=(210, 210, 210)).save(buf, "JPEG", quality=85)
    body = receipts.scan(WS, buf.getvalue(), "drawn.jpg")
    assert body["ocr"]["ok"], body["ocr"]
    assert receipts.amount_decimal(body["suggestion"]) == receipts.Decimal("79.50")
    assert body["suggestion"]["payee"] == "OXXO"
