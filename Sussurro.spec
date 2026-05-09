# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules, collect_data_files, collect_dynamic_libs

hidden = []
hidden += collect_submodules("faster_whisper")
hidden += collect_submodules("ctranslate2")
hidden += collect_submodules("tokenizers")
hidden += collect_submodules("huggingface_hub")
hidden += collect_submodules("onnxruntime")
hidden += collect_submodules("av")
hidden += collect_submodules("meeting")
hidden += collect_submodules("sentence_transformers")
hidden += collect_submodules("silero_vad")
hidden += collect_submodules("groq")
hidden += collect_submodules("pypdf")
hidden += collect_submodules("pyaudiowpatch")
hidden += ["sounddevice", "soundfile", "cffi", "yaml", "keyboard", "pyperclip", "win32api", "win32con"]

datas = []
datas += collect_data_files("faster_whisper")
datas += collect_data_files("ctranslate2")
datas += collect_data_files("tokenizers")
datas += collect_data_files("onnxruntime")
datas += collect_data_files("av")
datas += collect_data_files("sentence_transformers")
datas += collect_data_files("silero_vad")
datas += [("config.yaml", "."), ("meeting/meeting_config.yaml", "meeting")]

binaries = []
binaries += collect_dynamic_libs("ctranslate2")
binaries += collect_dynamic_libs("onnxruntime")
binaries += collect_dynamic_libs("sounddevice")
binaries += collect_dynamic_libs("av")


a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter", "matplotlib", "pytest", "IPython", "jupyter", "notebook",
        "torchvision",
        "llvmlite", "numba",
        "pandas",
        "cv2",
        "PIL", "Pillow",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Sussurro",
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
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Sussurro",
)
