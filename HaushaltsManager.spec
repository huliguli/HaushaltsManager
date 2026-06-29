# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — builds a ONEDIR Windows app (folder, not single file).

Onedir is used deliberately: the Python runtime (incl. python3xx.dll) lives
permanently next to the executable in _internal/, so there is NO per-launch
temp extraction to %TEMP%\\_MEI… . That removes the "Failed to load Python DLL"
class of failures that onefile suffered after a self-replace update, and makes
startup faster and antivirus-friendly. The folder is wrapped into a signed
Inno Setup installer (installer/HaushaltsManager.iss) for distribution.

Bundled data (collected into _internal/ at the matching relative path):
    * src/database/schema.sql  -> read at first run to create the database
    * version.json             -> the app's own version (update check baseline)
    * assets/app.ico           -> window/app icon
"""

block_cipher = None

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/database/schema.sql', 'src/database'),
        ('version.json', '.'),
        ('assets/app.ico', 'assets'),
        # NOTE: seed.sample.json is deliberately NOT bundled — a shipped build
        # must start with an empty database, never with demo data.
    ],
    hiddenimports=[
        'matplotlib.backends.backend_qtagg',
        'matplotlib.backends.backend_agg',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'PyQt5', 'PySide6', 'PySide2', 'PyQt6.QtWebEngineCore'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,   # onedir: binaries go into COLLECT, not the exe
    name='HaushaltsManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app.ico',
    version='version_info.txt',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='HaushaltsManager',
)
