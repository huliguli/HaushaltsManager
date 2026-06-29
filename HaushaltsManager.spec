# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec — builds a single-file Windows executable.

Bundled data:
    * src/database/schema.sql  -> read at first run to create the database
    * version.json             -> the app's own version (update check baseline)
    * database/seed.sample.json -> anonymised demo seed (never the real data)

The real seed (seed.local.json) is intentionally NOT bundled; a user who wants
to preload their own data drops it next to the executable or into
%APPDATA%/HaushaltsManager.
"""

block_cipher = None

a = Analysis(
    ['src/main.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('src/database/schema.sql', 'src/database'),
        ('version.json', '.'),
        ('database/seed.sample.json', 'database'),
        ('assets/app.ico', 'assets'),
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
    a.binaries,
    a.datas,
    [],
    name='HaushaltsManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/app.ico',
    version='version_info.txt',
)
