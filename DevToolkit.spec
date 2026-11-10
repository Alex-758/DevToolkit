# -*- mode: python ; coding: utf-8 -*-
"""DevToolkit 打包配置：单文件、无控制台、轻量化（剔除未用模块）。"""

import os

BLOCK_CIPHER = None

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # 压缩库为可选依赖，显式声明确保进入包体（自检模式会验证）
        'brotli',
        'zstandard',
        'lz4.frame',
        'Crypto.Cipher.AES',
        'Crypto.Cipher.ChaCha20_Poly1305',
        'Crypto.Cipher.PKCS1_OAEP',
        'Crypto.Cipher.PKCS1_v1_5',
        'Crypto.Hash.SHA256',
        'Crypto.PublicKey.RSA',
        'Crypto.Signature.pss',
        'Crypto.Util.Padding',
        'PySide6.QtSvg',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 未使用的第三方库
        'tkinter', 'matplotlib', 'numpy', 'scipy', 'pandas', 'PIL',
        'setuptools', 'pip', 'wheel', 'pytest', 'pygments', 'IPython',
        # 未使用的 PySide6 模块（显著减小体积）
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebChannel',
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuick3D', 'PySide6.QtQuickWidgets',
        'PySide6.QtQmlModels',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets',
        'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
        'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtGraphs',
        'PySide6.QtSql', 'PySide6.QtTest', 'PySide6.QtDesigner', 'PySide6.QtUiTools',
        'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtPositioning',
        'PySide6.QtLocation', 'PySide6.QtSensors', 'PySide6.QtSerialPort',
        'PySide6.QtWebSockets', 'PySide6.QtRemoteObjects', 'PySide6.QtScxml',
        'PySide6.QtStateMachine', 'PySide6.QtTextToSpeech', 'PySide6.QtNetworkAuth',
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput',
        'PySide6.Qt3DLogic', 'PySide6.Qt3DAnimation', 'PySide6.Qt3DExtras',
        'PySide6.QtHelp', 'PySide6.QtDBus', 'PySide6.QtOpenGLWidgets',
        'PySide6.QtSpatialAudio', 'PySide6.QtHttpServer', 'PySide6.QtQuickControls2',
    ],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='DevToolkit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets\\icon.ico',
    version='version_info.txt',
)
