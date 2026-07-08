"""Cross-platform behaviour: per-user data dir + the OS 'open path' helper."""

from pathlib import Path


def test_data_dir_per_os(monkeypatch, tmp_path):
    import app_meta
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

    # macOS -> ~/Library/Application Support/HaushaltsManager
    monkeypatch.setattr(app_meta.sys, "platform", "darwin")
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    assert app_meta.data_dir() == tmp_path / "Library" / "Application Support" / "HaushaltsManager"

    # Linux -> $XDG_DATA_HOME/HaushaltsManager (or ~/.local/share/...)
    monkeypatch.setattr(app_meta.sys, "platform", "linux")
    assert app_meta.data_dir() == tmp_path / ".local" / "share" / "HaushaltsManager"

    # APPDATA (any OS) overrides so tests can redirect the whole data dir.
    monkeypatch.setenv("APPDATA", str(tmp_path / "roaming"))
    assert app_meta.data_dir() == tmp_path / "roaming" / "HaushaltsManager"


def test_open_path_uses_the_platform_command(monkeypatch):
    from modules import platform_util
    seen = {}
    monkeypatch.setattr(platform_util.subprocess, "Popen",
                        lambda argv, **k: seen.__setitem__("argv", argv))

    monkeypatch.setattr(platform_util.sys, "platform", "darwin")
    platform_util.open_path("/some/folder")
    assert seen["argv"] == ["open", "/some/folder"]

    monkeypatch.setattr(platform_util.sys, "platform", "linux")
    platform_util.open_path("/some/folder")
    assert seen["argv"] == ["xdg-open", "/some/folder"]

    # Windows uses os.startfile (created via raising=False on non-Windows runners).
    started = {}
    monkeypatch.setattr(platform_util.sys, "platform", "win32")
    monkeypatch.setattr(platform_util.os, "startfile",
                        lambda p: started.__setitem__("p", p), raising=False)
    platform_util.open_path("C:/data")
    assert started["p"] == "C:/data"


def test_open_path_never_raises(monkeypatch):
    from modules import platform_util
    monkeypatch.setattr(platform_util.sys, "platform", "linux")
    monkeypatch.setattr(platform_util.subprocess, "Popen",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("no opener")))
    platform_util.open_path("/x")  # must swallow the error
