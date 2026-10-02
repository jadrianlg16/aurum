from aurum.satsync.client import FakeSAT


def test_fake_sat_roundtrip(tmp_path):
    (tmp_path / "recibidos").mkdir()
    (tmp_path / "recibidos" / "a.xml").write_text("<x/>", encoding="utf-8")
    (tmp_path / "recibidos" / "b.xml").write_text("<x/>", encoding="utf-8")

    client = FakeSAT(tmp_path)
    req_id = client.request("demo", "2026-08-01", "2026-08-31", "recibidos")
    assert client.verify(req_id) == "ready"
    files = client.download(req_id)
    assert len(files) == 2
    assert all(f.suffix == ".xml" for f in files)


def test_fake_sat_flat_dir_fallback(tmp_path):
    (tmp_path / "one.xml").write_text("<x/>", encoding="utf-8")
    client = FakeSAT(tmp_path)
    req_id = client.request("demo", "2026-08-01", "2026-08-31", "emitidos")
    assert client.verify(req_id) == "ready"
    files = client.download(req_id)
    assert len(files) == 1
