"""Tests for the updater's version comparison and checksum helpers."""

import hashlib

from modules.updater import updater


def test_version_compare():
    assert updater.parse_version("v1.2.3") == (1, 2, 3)
    assert updater.is_newer("v1.0.1", "1.0.0") is True
    assert updater.is_newer("1.0.0", "1.0.0") is False
    assert updater.is_newer("v1.0.0", "1.0.1") is False


def test_parse_sha256():
    digest = "a" * 64
    assert updater._parse_sha256(f"{digest}  HaushaltsManager.exe") == digest
    assert updater._parse_sha256("KEINE PRUEFSUMME") is None
    assert updater._parse_sha256("") is None


def test_sha256_of_file(tmp_path):
    f = tmp_path / "blob.bin"
    payload = b"HaushaltsManager update payload"
    f.write_bytes(payload)
    assert updater.sha256_of_file(str(f)) == hashlib.sha256(payload).hexdigest()


def test_fetch_checksum_rejects_non_github():
    # Host allow-list: a non-GitHub URL yields None without any network call.
    assert updater.fetch_checksum("http://evil.example.com/x.sha256") is None
    assert updater.fetch_checksum("https://evil.example.com/x.sha256") is None


def test_verify_download_match_mismatch_and_none(tmp_path):
    f = tmp_path / "u.exe"
    f.write_bytes(b"payload")
    good = updater.sha256_of_file(str(f))
    assert updater.verify_download(str(f), good) is True
    assert updater.verify_download(str(f), good.upper()) is True   # case-insensitive
    assert updater.verify_download(str(f), "0" * 64) is False      # mismatch rejected
    # No checksum available -> cannot verify here; HTTPS + Authenticode guard.
    assert updater.verify_download(str(f), None) is True
    assert updater.verify_download(str(f), "") is True


def test_is_trusted_installer_pins_thumbprint(monkeypatch):
    pinned = updater._TRUSTED_CERT_THUMBPRINTS[0]
    monkeypatch.setattr(updater, "authenticode_thumbprint", lambda p: pinned.lower())
    assert updater.is_trusted_installer("x.exe") is True            # case-insensitive match
    monkeypatch.setattr(updater, "authenticode_thumbprint", lambda p: "DEADBEEF")
    assert updater.is_trusted_installer("x.exe") is False           # wrong cert rejected
    monkeypatch.setattr(updater, "authenticode_thumbprint", lambda p: None)
    assert updater.is_trusted_installer("x.exe") is False           # unsigned rejected


def test_authenticode_thumbprint_unsigned_is_none(tmp_path):
    # Exercises the real PowerShell/subprocess + regex path (no monkeypatch): an
    # unsigned file has no signer certificate, so no 40-hex thumbprint is found.
    # Guards the env handling (PSModulePath strip) and decode from regressing.
    f = tmp_path / "plain.exe"
    f.write_bytes(b"MZ this file is not Authenticode signed")
    assert updater.authenticode_thumbprint(str(f)) is None
    assert updater.is_trusted_installer(str(f)) is False


def test_apply_update_dev_gate_never_launches(monkeypatch):
    # In a non-frozen run apply_update_and_restart must return False without ever
    # spawning the installer (the gate that prevents the dev/onefile DLL trap).
    import subprocess
    monkeypatch.setattr(subprocess, "Popen",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no launch in dev")))
    assert updater.apply_update_and_restart("setup.exe") is False


def test_apply_update_rejects_untrusted_signature(monkeypatch):
    # Frozen build + untrusted signature: fail-closed, no launch, temp removed.
    import subprocess
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    monkeypatch.setattr(updater, "is_trusted_installer", lambda p: False)
    removed = {}
    monkeypatch.setattr(updater, "_safe_remove", lambda p: removed.__setitem__("p", p))
    monkeypatch.setattr(subprocess, "Popen",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no untrusted launch")))
    assert updater.apply_update_and_restart("tampered.exe") is False
    assert removed.get("p") == "tampered.exe"


def test_apply_update_trusted_launches_silently(monkeypatch):
    # Frozen build + trusted signature: the installer launches with silent flags.
    import subprocess
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    monkeypatch.setattr(updater, "is_trusted_installer", lambda p: True)
    calls = {}
    monkeypatch.setattr(subprocess, "Popen",
                        lambda args, **k: calls.__setitem__("args", args) or object())
    assert updater.apply_update_and_restart("setup.exe") is True
    assert calls["args"][0] == "setup.exe"
    assert "/VERYSILENT" in calls["args"]
