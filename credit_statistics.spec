# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for 哈工程学分统计系统.
Bundles ddddocr ONNX models and onnxruntime DLLs into a single executable.
"""
import os
import sys
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs

# ddddocr 需要 ONNX 模型文件
ddddocr_datas = collect_data_files("ddddocr", include_py_files=False)
# onnxruntime 需要动态库
ort_binaries = collect_dynamic_libs("onnxruntime")

a = Analysis(
    ["credit_statistics.py"],
    pathex=[],
    binaries=ort_binaries,
    datas=ddddocr_datas,
    hiddenimports=[
        "ddddocr",
        "onnxruntime",
        "PIL",
        "numpy",
        "requests",
        "urllib3",
        "certifi",
        "charset_normalizer",
        "idna",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "scipy", "pandas", "IPython", "notebook"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="CreditStatistics",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,   # macOS argv emulation
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,              # 如有 .ico 文件可指定
)
