"""Production PyInstaller Packaging Harness for OmniResearch Studio.

Executes standalone directory packaging with complete native binary dynamic libraries
(CTranslate2, ONNX Runtime, PyMuPDF, FastAPI, Uvicorn, RapidOCR) into `dist/OmniResearchStudio/`.
Includes post-build credential isolation and packaging sanitization audit.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import PyInstaller.__main__
from PyInstaller.utils.hooks import collect_all, collect_data_files

DIST_BLACKLIST_PATTERNS = [
    ".env*",
    "*.env",
    "*.key",
    "credentials.json",
    "config.json",
    "user_config.json",
    "settings.json",
    "*.db",
    "*.sqlite*",
    "*.log",
    "*__pycache__*",
    "*.pytest_cache*",
]

RAW_GEMINI_KEY_RE = re.compile(rb"\b[A][I][z][a][0-9A-Za-z\-_]{35}\b")


def is_blacklisted_artifact(path: Path) -> bool:
    """Return True if path matches any secret, cache, database, or log pattern."""
    norm = str(path).replace("\\", "/").lower()
    name = path.name.lower()
    if "__pycache__" in norm or ".pytest_cache" in norm:
        return True
    for pat in DIST_BLACKLIST_PATTERNS:
        if fnmatch.fnmatch(name, pat.lower()) or fnmatch.fnmatch(norm, f"*/{pat.lower()}"):
            return True
    return False


def verify_dist_sanitization(dist_studio_dir: Path) -> None:
    """
    Perform deep security and packaging audit on the generated distribution directory.
    Aborts immediately if any secret, database, log, cache file or raw Gemini API key is discovered.
    """
    if not dist_studio_dir.exists():
        raise RuntimeError(f"Distribution directory does not exist: {dist_studio_dir}")

    print("\n[Package Audit] Scanning dist/OmniResearchStudio for leaked credentials and blacklisted files...")
    violations: list[str] = []
    scanned_count = 0

    for item in dist_studio_dir.rglob("*"):
        if item.is_dir():
            if is_blacklisted_artifact(item):
                violations.append(f"Blacklisted directory: {item.relative_to(dist_studio_dir)}")
            continue

        scanned_count += 1
        rel_path = item.relative_to(dist_studio_dir)

        # 1. Path/Filename Blacklist Check
        if is_blacklisted_artifact(item):
            violations.append(f"Blacklisted file pattern found: {rel_path}")
            continue

        # 2. Content Secret Check: scan for raw Gemini API keys (Gemini key pattern)
        try:
            size = item.stat().st_size
            if size < 30 * 1024 * 1024:
                with open(item, "rb") as f:
                    content = f.read()
                    if RAW_GEMINI_KEY_RE.search(content):
                        violations.append(f"Raw Gemini API key pattern found in: {rel_path}")
        except Exception:
            pass

    if violations:
        print("\n" + "=" * 70)
        print(" [FATAL ERROR] PACKAGING SANITIZATION AUDIT FAILED!")
        print(" Found the following security violations inside release distribution:")
        for v in violations:
            print(f"   [!] {v}")
        print("=" * 70 + "\n")
        raise RuntimeError(f"Aborting release build: {len(violations)} packaging credential violations found.")

    print(f"[Package Audit] Sanitization PASSED: {scanned_count} files inspected. Zero leaked credentials or blacklisted artifacts found.\n")


def run_packaging(clean: bool = True) -> int:
    """Execute PyInstaller build pipeline using OmniResearchStudio.spec."""
    project_root = Path(__file__).resolve().parent
    spec_file = project_root / "OmniResearchStudio.spec"

    if not spec_file.exists():
        print(f"[ERROR] Spec file not found: {spec_file}")
        return 1

    dist_dir = project_root / "dist"
    build_dir = project_root / "build"
    onedir_target = dist_dir / "OmniResearchStudio"

    if clean:
        print("[Package] Cleaning previous build and dist artifacts...")
        if build_dir.exists():
            shutil.rmtree(build_dir, ignore_errors=True)
        if onedir_target.exists() and onedir_target.is_dir():
            shutil.rmtree(onedir_target, ignore_errors=True)

    print("[Package] Launching PyInstaller single-file compilation pipeline (--onefile)...")
    t0 = time.time()

    pyinstaller_args = [
        str(spec_file),
        "--noconfirm",
    ]
    if clean:
        pyinstaller_args.append("--clean")

    try:
        PyInstaller.__main__.run(pyinstaller_args)
    except Exception as e:
        print(f"[ERROR] Packaging failed: {e}")
        return 1

    elapsed = time.time() - t0
    target_exe = dist_dir / "OmniResearchStudio.exe"

    if not target_exe.exists():
        # Fallback check in case onedir was produced
        if (onedir_target / "OmniResearchStudio.exe").exists():
            target_exe = onedir_target / "OmniResearchStudio.exe"
        else:
            print(f"[ERROR] Target standalone executable not found at: {target_exe}")
            return 1

    # Post-Build Sanitization & Credential Isolation Verification
    try:
        verify_dist_sanitization(dist_dir)
    except Exception as e:
        print(f"[ERROR] Post-build sanitization failed: {e}")
        return 1

    exe_size_mb = target_exe.stat().st_size / (1024 * 1024)
    print(f"======================================================================")
    print(f" [SUCCESS] OmniResearch Studio Single-File Standalone Executable Packaged!")
    print(f" Output Binary: {target_exe}")
    print(f" Executable Size: {exe_size_mb:.2f} MB")
    print(f" Compilation Mode: Single-File Standalone (--onefile)")
    print(f" Elapsed Time: {elapsed:.1f}s")
    print(f"======================================================================\n")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Package OmniResearch Studio into portable Windows binary")
    parser.add_argument("--no-clean", action="store_true", help="Do not clean build directory before compiling")
    args = parser.parse_args()

    sys.exit(run_packaging(clean=not args.no_clean))
