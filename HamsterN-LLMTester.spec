# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['launcher.py'],
    pathex=['src'],
    binaries=[],
    datas=[
        ('resources/test_cases/*', 'resources/test_cases'), 
        ('dist/test_suites/test_cases/*', 'dist/test_suites/test_cases')
    ],
    hiddenimports=[
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
        'PyQt6.QtSvg',
        'PyQt6.QtNetwork',
        'qasync',
        'asyncio',
        'json',
        'os',
        'sys',
        'platform',
        'openai',
        'anthropic',
        'google.generativeai'
    ],
    hookspath=[],
    hooksconfig={
        'PyQt6': {
            'true_globals': [
                'QtCore', 'QtGui', 'QtWidgets', 'QtSvg', 'QtNetwork'
            ]
        }
    },
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='HamsterN-LLMTester',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon='resources/icon.ico' if os.path.exists('resources/icon.ico') else None,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
