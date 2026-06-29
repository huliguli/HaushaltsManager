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
