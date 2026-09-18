# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ["src/rvb_vault/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[("assets/rvb_vault.ico", "assets")],
    hiddenimports=[
        "winrt.windows.foundation",
        "winrt.windows.foundation.collections",
        "winrt.windows.security.credentials.ui",
        "winrt.windows.storage",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="RVB Vault",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/rvb_vault.ico",
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="RVB Vault",
)
