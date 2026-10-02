import pytest

from aurum.satsync import vault


def test_store_open_roundtrip():
    status = vault.store("demo", b"CER-BYTES", b"KEY-BYTES", "ciec-pass", "correct horse battery staple")
    assert status["present"] is True

    creds = vault.open_vault("demo", "correct horse battery staple")
    assert creds.cer_bytes == b"CER-BYTES"
    assert creds.key_bytes == b"KEY-BYTES"
    assert creds.password == "ciec-pass"


def test_wrong_passphrase_raises():
    vault.store("demo2", b"a", b"b", "p", "right-passphrase")
    with pytest.raises(vault.VaultBadPassphrase):
        vault.open_vault("demo2", "wrong-passphrase")


def test_status_never_returns_material():
    vault.store("demo3", b"secret-cer", b"secret-key", "pw", "pp")
    status = vault.status("demo3")
    dumped = str(status)
    assert "secret-cer" not in dumped
    assert "secret-key" not in dumped
    assert "pp" not in dumped


def test_missing_vault_raises_not_found():
    with pytest.raises(vault.VaultNotFound):
        vault.open_vault("no-such-ws", "whatever")


def test_purge():
    vault.store("demo4", b"a", b"b", "p", "pp")
    assert vault.status("demo4")["present"] is True
    assert vault.purge("demo4") is True
    assert vault.status("demo4")["present"] is False
    assert vault.purge("demo4") is False


def test_roundtrip_when_salt_contains_newline(monkeypatch):
    """Regression: the salt is random bytes and can contain 0x0A; parsing must not split on it."""
    import os as _os

    real = _os.urandom
    newline_salt = bytes([10]) * vault._SALT_LEN
    monkeypatch.setattr(vault.os, "urandom", lambda n: newline_salt if n == vault._SALT_LEN else real(n))
    vault.store("demo-nl", b"C", b"K", "pw", "pp")
    creds = vault.open_vault("demo-nl", "pp")
    assert creds.cer_bytes == b"C" and creds.password == "pw"
