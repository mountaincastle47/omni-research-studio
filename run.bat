@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [OmniResearch Studio] Creating virtual environment .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment. Ensure Python 3 is installed and on PATH.
        pause
        exit /b 1
    )
)

echo [OmniResearch Studio] Verifying dependencies...
".venv\Scripts\python.exe" -c "import PyQt6, google.genai, pypdf, markdown, edge_tts, pymupdf4llm, docx, chardet, mutagen, rank_bm25, PIL, httpx, youtube_transcript_api, faster_whisper, requests, PyInstaller, networkx, fastapi, uvicorn, cryptography, matplotlib, numpy, keyring" 2>nul
if errorlevel 1 (
    echo [OmniResearch Studio] Installing required packages from requirements.txt...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [ERROR] Dependency installation failed.
        pause
        exit /b 1
    )
)

echo [OmniResearch Studio] Launching desktop application...
".venv\Scripts\python.exe" main.py
endlocal
