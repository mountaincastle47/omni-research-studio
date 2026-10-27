"""Standalone Production PyInstaller Packaging Harness for OmniResearch Studio."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import shutil
import subprocess
import sys


SPEC_TEMPLATE = """# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

hidden_imports = [
    'PyQt6.QtMultimedia',
    'PyQt6.QtPrintSupport',
    'edge_tts',
    'rapidocr_onnxruntime',
    'faster_whisper',
    'pymupdf4llm',
    'trafilatura',
    'docx',
    'chardet',
    'mutagen',
    'rank_bm25',
    'PIL',
    'httpx',
    'youtube_transcript_api',
    'requests',
    'google.genai',
]

datas = []
# Collect data files for critical native and neural backends
for pkg in ['rapidocr_onnxruntime', 'trafilatura', 'faster_whisper', 'pymupdf']:
    try:
        datas += collect_data_files(pkg)
    except Exception:
        pass

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'scipy'],
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
    exclude_binaries=True,
    name='OmniResearchStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console={console_flag},
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='OmniResearchStudio',
)
"""


def generate_spec_file(output_path: Path = Path("OmniResearchStudio.spec"), console: bool = False) -> None:
    """Generate canonical PyInstaller spec file."""
    spec_content = SPEC_TEMPLATE.replace("{console_flag}", "True" if console else "False")
    output_path.write_text(spec_content, encoding="utf-8")
    print(f"[Build Harness] Generated PyInstaller spec: {output_path.resolve()}")


def run_build(clean: bool = True, spec_only: bool = False, console: bool = False) -> int:
    """Execute PyInstaller frozen binary packaging."""
    spec_file = Path("OmniResearchStudio.spec")
    generate_spec_file(spec_file, console=console)

    if spec_only:
        print("[Build Harness] Spec-only flag specified; skipping full compilation.")
        return 0

    if clean:
        print("[Build Harness] Cleaning previous build artifacts...")
        shutil.rmtree("build", ignore_errors=True)
        shutil.rmtree("dist", ignore_errors=True)

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", str(spec_file)]
    print(f"[Build Harness] Running build command: {' '.join(cmd)}")
    res = subprocess.run(cmd)
    return res.returncode


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OmniResearch Studio PyInstaller Build Harness")
    parser.add_argument("--spec-only", action="store_true", help="Generate .spec file without compiling")
    parser.add_argument("--no-clean", action="store_true", help="Do not clean build/ and dist/ directories before building")
    parser.add_argument("--console", action="store_true", help="Build with console window enabled for debugging")
    args = parser.parse_args()

    exit_code = run_build(clean=not args.no_clean, spec_only=args.spec_only, console=args.console)
    sys.exit(exit_code)
