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
    monkeypatch.setattr(updater.sys, "platform", "win32")   # exercise the Windows branch on any runner
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
    monkeypatch.setattr(updater.sys, "platform", "win32")   # exercise the Windows branch on any runner
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    monkeypatch.setattr(updater, "is_trusted_installer", lambda p: True)
    calls = {}
    monkeypatch.setattr(subprocess, "Popen",
                        lambda args, **k: calls.__setitem__("args", args) or object())
    assert updater.apply_update_and_restart("setup.exe") is True
    assert calls["args"][0] == "setup.exe"
    assert "/VERYSILENT" in calls["args"]


def test_select_asset_matches_platform_and_checksum():
    # A release carrying BOTH platforms' assets: each platform must pick its own
    # binary AND the checksum named after that binary (not the other one).
    assets = [
        {"name": "HaushaltsManager-macOS.dmg", "browser_download_url": "https://github.com/x/dmg"},
        {"name": "HaushaltsManager-macOS.dmg.sha256", "browser_download_url": "https://github.com/x/dmgsha"},
        {"name": "HaushaltsManager-Setup.exe", "browser_download_url": "https://github.com/x/exe"},
        {"name": "HaushaltsManager-Setup.exe.sha256", "browser_download_url": "https://github.com/x/exesha"},
    ]
    assert updater._select_asset_and_checksum(assets, ".exe") == (
        "https://github.com/x/exe", "https://github.com/x/exesha")
    assert updater._select_asset_and_checksum(assets, ".dmg") == (
        "https://github.com/x/dmg", "https://github.com/x/dmgsha")
    # No matching asset -> both empty.
    assert updater._select_asset_and_checksum([], ".exe") == ("", "")


def test_apply_update_macos_without_bundle_returns_false(monkeypatch):
    # Frozen macOS run but not inside a .app bundle (e.g. sys.executable is the
    # interpreter): no swap is scheduled and nothing is launched.
    import subprocess
    monkeypatch.setattr(updater.sys, "platform", "darwin")
    monkeypatch.setattr(updater, "is_frozen", lambda: True)
    monkeypatch.setattr(subprocess, "Popen",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("no swap without a bundle")))
    assert updater.apply_update_and_restart("update.dmg") is False


def test_macos_update_requires_checksum(monkeypatch, tmp_path):
    # macOS has no signature backstop, so a missing/unfetchable checksum must
    # fail CLOSED; Windows (Authenticode backstop) still proceeds without one.
    import os as _os
    _os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    try:
        from PyQt6.QtWidgets import QApplication
    except Exception as exc:  # pragma: no cover - Qt unavailable
        import pytest
        pytest.skip(f"Qt nicht verfügbar: {exc}")
    QApplication.instance() or QApplication([])

    # macOS + checksum cannot be fetched -> reject, temp removed, no 'ready'.
    dmg = tmp_path / "u.dmg"
    dmg.write_bytes(b"payload")
    monkeypatch.setattr(updater, "download_asset", lambda *a, **k: str(dmg))
    monkeypatch.setattr(updater, "fetch_checksum", lambda url: None)
    monkeypatch.setattr(updater.sys, "platform", "darwin")
    inst = updater.UpdateInstaller("https://github.com/x/u.dmg", "https://github.com/x/u.dmg.sha256")
    seen = {}
    inst.ready.connect(lambda p: seen.setdefault("ready", p))
    inst.failed.connect(lambda m: seen.setdefault("failed", m))
    inst.run()
    assert "failed" in seen and "ready" not in seen
    assert not dmg.exists()

    # Windows + no checksum asset -> proceeds (the Authenticode check guards apply).
    exe = tmp_path / "u.exe"
    exe.write_bytes(b"payload")
    monkeypatch.setattr(updater, "download_asset", lambda *a, **k: str(exe))
    monkeypatch.setattr(updater.sys, "platform", "win32")
    inst2 = updater.UpdateInstaller("https://github.com/x/u.exe", "")
    seen2 = {}
    inst2.ready.connect(lambda p: seen2.setdefault("ready", p))
    inst2.failed.connect(lambda m: seen2.setdefault("failed", m))
    inst2.run()
    assert "ready" in seen2 and "failed" not in seen2


def test_macos_swap_script_is_wellformed(tmp_path):
    import os
    from pathlib import Path
    stage = tmp_path / "stage" / "HaushaltsManager.app"
    bundle = Path("/Applications/HaushaltsManager.app")
    path = updater._write_macos_swap_script(4321, stage, bundle)
    try:
        text = Path(path).read_text(encoding="utf-8")
        assert text.startswith("#!/bin/bash")
        assert "pid=4321" in text
        # Restores the old bundle on a failed copy, then relaunches.
        assert "ditto" in text and "mv " in text and "open " in text
        assert "HaushaltsManager.app" in text
    finally:
        os.unlink(path)
