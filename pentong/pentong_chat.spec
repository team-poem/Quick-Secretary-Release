# -*- mode: python ; coding: utf-8 -*-
"""뚝딱비서 — PyInstaller 빌드 설정."""

import os

block_cipher = None

a = Analysis(
    ['pentong_chat.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('pentong_system_prompt.txt', '.'),
        # v0.0.25: markdown harness 토대 skill 모듈 (_invariants 등). 빌드시
        # _MEIPASS/prompts/skills/ 로 들어가고, 첫 실행 시 _load_system_prompt
        # 가 base 와 합성해 ~/.ddukddak/system_prompt.txt 로 보장.
        ('prompts', 'prompts'),
        ('templates', 'templates'),
        ('core', 'core'),
        # rhwp bridge (Node.js + @rhwp/core WASM) — HWP 처리를 COM 없이 하는
        # 번들. 3.9MB. 첫 실행 시 ~/.ddukddak/rhwp_bridge/ 로 복사됨.
        ('rhwp_bridge', 'rhwp_bridge'),
    ],
    hiddenimports=[
        'openpyxl',
        'openpyxl.utils',
        'openpyxl.styles',
        'openpyxl.workbook',
        'openpyxl.worksheet',
        'win32com',
        'win32com.client',
        'pythoncom',
        'pywintypes',
        'windnd',
        'json',
        'tkinter',
        'tkinter.ttk',
        'tkinter.filedialog',
        'tkinter.scrolledtext',
        'tkinter.messagebox',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib', 'numpy', 'scipy',
        'pytest', 'unittest',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='뚝딱비서',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
