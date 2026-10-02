"""Light OCR for receipt photos.

Two engines behind one call, picked by ``AURUM_OCR_BACKEND`` (``auto`` by default):

- ``tesseract`` — the Tesseract CLI run directly on the photo (~0.3 s per ticket on a desktop). Found
  through ``AURUM_TESSERACT_CMD``, else ``tesseract`` on PATH, else the Windows installer's default path
  (runtime detection — nothing machine-specific is hard-coded). Languages ``AURUM_OCR_LANGS``
  (``spa+eng``) intersected with what is installed; ``--psm 4`` (a column of lines, what a ticket is).
- ``ocr-engine`` — an optional external OCR HTTP service, used when ``AURUM_OCR_URL`` is set: create a
  job (``POST /v1/ocr/jobs``), poll it, read the text output. Usually slower than a local Tesseract; kept
  for machines without one.

``auto`` = tesseract when found, else ocr-engine when a URL is set, else off. Off, failing or timing
out is never an error for the caller: the photo is still kept and the person types the amount by hand
(manual first). The image is cleaned for OCR only — EXIF rotation, grayscale, upscale small photos,
autocontrast — in a temp file; the stored copy is written by ``receipts.py``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..core.config import env

_WIN_DEFAULT = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")


@dataclass
class OcrResult:
    text: str
    engine: str | None  # tesseract | ocr-engine | None (off)
    ok: bool
    error: str | None
    seconds: float


def _timeout() -> int:
    try:
        return max(5, int(env("AURUM_OCR_TIMEOUT", "30")))
    except ValueError:
        return 30


def tesseract_cmd() -> str | None:
    configured = env("AURUM_TESSERACT_CMD", "").strip()
    if configured:
        return configured if (Path(configured).exists() or shutil.which(configured)) else None
    found = shutil.which("tesseract")
    if found:
        return found
    if os.name == "nt" and _WIN_DEFAULT.exists():
        return str(_WIN_DEFAULT)
    return None


@lru_cache(maxsize=8)
def _installed_langs(cmd: str) -> frozenset[str]:
    try:
        out = subprocess.run([cmd, "--list-langs"], capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    lines = (out.stdout or out.stderr or "").splitlines()
    return frozenset(ln.strip() for ln in lines[1:] if ln.strip())


def lang_arg(cmd: str) -> str | None:
    wanted = [x for x in env("AURUM_OCR_LANGS", "spa+eng").split("+") if x]
    installed = _installed_langs(cmd)
    keep = [x for x in wanted if x in installed] or (["eng"] if "eng" in installed else [])
    return "+".join(keep) or None


def backend() -> str | None:
    """The engine a scan would use right now: ``tesseract``, ``ocr-engine`` or None (off)."""
    choice = env("AURUM_OCR_BACKEND", "auto").strip().lower()
    url = env("AURUM_OCR_URL", "").strip()
    if choice == "off":
        return None
    if choice == "tesseract":
        return "tesseract" if tesseract_cmd() else None
    if choice == "ocr-engine":
        return "ocr-engine" if url else None
    if tesseract_cmd():
        return "tesseract"
    return "ocr-engine" if url else None


def _prepared(src: Path, workdir: Path) -> Path:
    """A grayscale, upright, readable-size PNG for the OCR engine. Pillow missing → the original."""
    try:
        from PIL import Image, ImageOps
    except ImportError:  # pragma: no cover - Pillow ships with reportlab
        return src
    try:
        with Image.open(src) as im:
            img = ImageOps.exif_transpose(im).convert("L")
    except OSError:
        return src
    longest = max(img.size)
    if longest < 1400:  # small photos read badly; Tesseract likes ~300 dpi text
        scale = 1400 / longest
        img = img.resize((round(img.width * scale), round(img.height * scale)))
    elif longest > 3200:
        scale = 3200 / longest
        img = img.resize((round(img.width * scale), round(img.height * scale)))
    img = ImageOps.autocontrast(img, cutoff=1)
    out = workdir / "ocr.png"
    img.save(out)
    return out


def _run_tesseract(image: Path) -> OcrResult:
    t0 = time.monotonic()
    cmd = tesseract_cmd()
    if cmd is None:
        return OcrResult("", None, False, "tesseract_not_found", 0.0)
    langs = lang_arg(cmd)
    args = [cmd, str(image), "stdout", "--psm", "4"] + (["-l", langs] if langs else [])
    try:
        out = subprocess.run(args, capture_output=True, timeout=_timeout(), check=False)
    except subprocess.TimeoutExpired:
        return OcrResult("", "tesseract", False, "timeout", time.monotonic() - t0)
    except OSError as e:
        return OcrResult("", "tesseract", False, f"os_error:{e.errno}", time.monotonic() - t0)
    text = out.stdout.decode("utf-8", errors="replace")
    ok = out.returncode == 0
    return OcrResult(text if ok else "", "tesseract", ok, None if ok else f"exit_{out.returncode}",
                     time.monotonic() - t0)


def _run_ocr_engine(image: Path, url: str) -> OcrResult:
    import httpx

    t0 = time.monotonic()
    deadline = t0 + _timeout()
    base = url.rstrip("/")
    try:
        with httpx.Client(timeout=15) as client:
            with image.open("rb") as fh:
                r = client.post(f"{base}/v1/ocr/jobs", files={"file": (image.name, fh, "image/png")},
                                data={"languages": env("AURUM_OCR_LANGS", "spa+eng")})
            r.raise_for_status()
            job_id = r.json()["id"]
            status = r.json().get("status")
            while status in ("queued", "processing"):
                if time.monotonic() > deadline:
                    return OcrResult("", "ocr-engine", False, "timeout", time.monotonic() - t0)
                time.sleep(0.5)
                status = client.get(f"{base}/v1/ocr/jobs/{job_id}").json().get("status")
            if status != "completed":
                return OcrResult("", "ocr-engine", False, f"job_{status}", time.monotonic() - t0)
            text = client.get(f"{base}/v1/ocr/jobs/{job_id}/outputs/text").text
    except (httpx.HTTPError, KeyError, ValueError) as e:
        return OcrResult("", "ocr-engine", False, type(e).__name__, time.monotonic() - t0)
    return OcrResult(text, "ocr-engine", True, None, time.monotonic() - t0)


def ocr_image(path: Path) -> OcrResult:
    """OCR one stored receipt photo. Never raises: off / missing / failing → ``ok=False`` with a code."""
    engine = backend()
    if engine is None:
        return OcrResult("", None, False, "ocr_off", 0.0)
    with tempfile.TemporaryDirectory(prefix="aurum-ocr-") as tmp:
        image = _prepared(path, Path(tmp))
        if engine == "tesseract":
            return _run_tesseract(image)
        return _run_ocr_engine(image, env("AURUM_OCR_URL", ""))
