# OmniResearch Studio

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green.svg)](https://www.riverbankcomputing.com/software/pyqt/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Platform: Windows 10/11 64-bit](https://img.shields.io/badge/platform-Windows%2010%2F11%2064--bit-blue)](https://microsoft.com/windows)

> A standalone, local-first research workstation combining multi-perspective web grounding, strict citation verification, and epistemic synthesis.

---

## Overview

**OmniResearch Studio** is a sovereign research environment engineered for researchers, engineers, and analysts who require uncompromising grounded intelligence. Unlike conventional LLM wrappers that produce hallucinated overviews, OmniResearch Studio enforces strict citation provenance down to specific document pages, isolates empirical contradictions in a dedicated matrix, and runs completely locally with sandboxed OS isolation and user-space credential isolation.

---

## Core Capabilities

- **Multi-Perspective OmniSweep**: Automated web discovery parallelized across four distinct analytical vectors:
  - *Architect*: System topology, mechanistic causality, and implementation feasibility.
  - *Skeptic*: Adversarial threat models, failure modes, counter-evidence, and edge cases.
  - *Strategist*: Macro-economic tradeoffs, market positioning, and deployment ROI.
  - *Historian*: Chronological precedent, evolution of paradigms, and legacy root causes.
- **Grounded Epistemic Synthesis**: Enforces strict page-level and source-level citation tokens (`[DocID:p.X]`). Every synthesis paragraph links back to verifiable evidence, accompanied by an interactive modal source inspector for instantaneous provenance audits.
- **Contested Claims Matrix**: Automatic isolation, categorization, and side-by-side comparison of conflicting empirical claims, anomalous telemetry points, and diverging statistics across ingested corpora.
- **Local Document Pipeline**: Robust multi-format document ingestion (PDF, DOCX, TXT, ArXiv, DOI, YouTube transcripts, audio briefings) with native `pymupdf4llm` parsing and fallback OCR via `rapidocr-onnxruntime`. Process sandboxing isolates ingestion inside dedicated sub-processes to provide complete OS segfault immunity.
- **Dual-Host Neural Audio Studio**: High-fidelity multi-voice conversational podcast and briefing generation powered by Edge-TTS and PyDub, complete with waveform scrubbing and timeline navigation.
- **Local Hardware Acceleration**: Seamless ONNX Runtime integration with automatic CPU thread tuning, DirectML / CUDA device detection, and real-time inference telemetry.

---

## Architecture & Tech Stack

| Component | Technology | Description |
| :--- | :--- | :--- |
| **Frontend Workstation** | [PyQt6](https://www.riverbankcomputing.com/software/pyqt/) (Qt6) | Hardware-accelerated desktop workstation with reactive state management, bilingual i18n, and custom theme styling |
| **Reasoning & Synthesis** | [Google Gemini API](https://ai.google.dev/) | Multi-model epistemic reasoning (Gemini Flash & Pro) with pre-flight token budgeting and live spend telemetry |
| **Local Compute Engine** | [ONNX Runtime](https://onnxruntime.ai/) | DirectML / CUDA / CPU auto-tuning for local document OCR and embeddings |
| **Document Processing** | [PyMuPDF](https://pymupdf.readthedocs.io/) & [RapidOCR](https://github.com/RapidAI/RapidOCR) | Segfault-immune process sandboxing for PDF parsing, text extraction, and OCR |
| **Neural Audio Studio** | [Edge-TTS](https://github.com/rany2/edge-tts) & [Mutagen](https://mutagen.readthedocs.io/) | Multi-speaker voice synthesis with timeline metadata injection |
| **Packaging & Delivery** | [PyInstaller](https://pyinstaller.org/) | Single-file zero-dependency binary compilation (`--onefile`) |

---

## Installation & Running from Source

### Prerequisites
- Windows 10 or 11 (64-bit)
- Python 3.10, 3.11, or 3.12 (Python 3.14 compatible)
- Git

### Quick Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/mountaincastle47/omni-research-studio.git
   cd omni-research-studio
   ```

2. **One-Click Bootstrapping (Recommended)**:
   Double-click `run.bat` or run:
   ```cmd
   run.bat
   ```
   *The launcher automatically initializes a clean Python virtual environment (`.venv`), installs all required dependencies, and boots the workstation.*

3. **Manual Setup**:
   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install --upgrade pip
   pip install -r requirements.txt
   python main.py
   ```

---

## Compiling Standalone Executable

OmniResearch Studio includes an automated single-file build harness that produces a standalone Windows executable (`dist/OmniResearchStudio.exe`):

```bash
.venv\Scripts\activate
python package.py
```

### Build Harness Highlights
- **Single-File (`--onefile`) Packaging**: Packages all application logic, Qt binaries, ONNX models, and assets into a single distribution binary.
- **Post-Build Sanitization Audit**: Automatically scans the build output for blacklisted patterns (`.env`, `*.db`, credentials) and raw API keys before certifying release integrity.
- **Dynamic Path Virtualization**: Automatically routes asset lookups through `sys._MEIPASS` when frozen, while directing all databases, settings, and logs to OS user-space.

---

## Security & Privacy Architecture

- **Sovereign User-Space Credential Storage**: API keys are **never** stored in the application directory, executable binary, or project root. Keys are persisted strictly in standard OS user-space (`QSettings` / Windows Registry `HKCU\Software\OmniResearch\OmniResearchStudio` and `%APPDATA%\OmniResearchStudio\settings.json`).
- **Zero Third-Party Telemetry**: OmniResearch Studio does not transmit user data, analytics, or search queries to any proprietary telemetry services. Direct requests are dispatched exclusively to the user-specified API endpoint.
- **Client-Side Sensitive Pattern Scrubbing**: Pre-flight regex filtering automatically sanitizes accidental leaks of email addresses, Korean RRNs, IP addresses, and private keys before dispatching synthesis prompts.

---

## License

This project is licensed under the [MIT License](LICENSE).
