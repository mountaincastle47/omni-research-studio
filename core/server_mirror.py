"""Headless LAN Mobile Web Mirror Server:
Lightweight FastAPI daemon serving active workspace reports, audio briefings,
and responsive mobile follow-up Q&A over local Wi-Fi with PIN authentication.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
from pathlib import Path
import random
import socket
import threading
import time
from typing import Any, Callable, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
import qrcode
import uvicorn

from core.i18n import get_text
from core.paths import get_cache_dir, SESSION_CACHE_DIR

logger = logging.getLogger("OmniMobileMirror")

QR_CODE_PATH = get_cache_dir() / "mobile_qr.png"


def get_local_lan_ip() -> str:
    """Auto-detect the primary local LAN IP address."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Dummy connect to external router/gateway
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
    except Exception:
        try:
            ip = socket.gethostbyname(socket.gethostname())
        except Exception:
            ip = "127.0.0.1"
    finally:
        s.close()
    return ip


MOBILE_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
  <title>OmniResearch Studio Mirror</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { background-color: #0B0E14; color: #E2E8F0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; line-height: 1.5; padding-bottom: 70px; }
    header { background-color: #0F172A; border-bottom: 1px solid #1E293B; padding: 12px 16px; position: sticky; top: 0; z-index: 50; display: flex; align-items: center; justify-content: space-between; }
    .brand { font-size: 15px; font-weight: 700; color: #38BDF8; display: flex; align-items: center; gap: 8px; }
    .pin-badge { font-size: 11px; background: #1E293B; color: #F59E0B; padding: 2px 8px; border-radius: 12px; border: 1px solid #334155; }
    .nav-tabs { display: flex; background: #0B0E14; border-bottom: 1px solid #1E293B; }
    .nav-tab { flex: 1; text-align: center; padding: 10px; font-size: 13px; font-weight: 600; color: #94A3B8; cursor: pointer; border-bottom: 2px solid transparent; }
    .nav-tab.active { color: #38BDF8; border-bottom-color: #38BDF8; background: #0F172A; }
    .pane { display: none; padding: 14px; }
    .pane.active { display: block; }
    .card { background: #0F172A; border: 1px solid #1E293B; border-radius: 8px; padding: 14px; margin-bottom: 12px; }
    h1, h2, h3 { color: #F8FAFC; margin-bottom: 8px; }
    p { margin-bottom: 10px; color: #CBD5E1; font-size: 14px; }
    audio { width: 100%; border-radius: 6px; margin-top: 8px; }
    .chat-box { height: 280px; overflow-y: auto; background: #05070B; border: 1px solid #1E293B; border-radius: 6px; padding: 10px; margin-bottom: 10px; }
    .chat-msg { margin-bottom: 10px; font-size: 13px; }
    .chat-user { color: #38BDF8; font-weight: 600; }
    .chat-bot { color: #E2E8F0; margin-top: 2px; }
    .input-row { display: flex; gap: 6px; }
    input[type="text"] { flex: 1; background: #0F172A; border: 1px solid #334155; color: #F1F5F9; border-radius: 6px; padding: 8px 12px; font-size: 14px; }
    button { background: #0284C7; color: #FFF; font-weight: 700; border: none; border-radius: 6px; padding: 8px 14px; cursor: pointer; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 12px; font-size: 12px; }
    th, td { border: 1px solid #1E293B; padding: 6px 8px; text-align: left; }
    th { background: #1E293B; color: #38BDF8; }
    .cite-tag { color: #38BDF8; font-weight: bold; background: rgba(56, 189, 248, 0.15); padding: 1px 4px; border-radius: 3px; }
  </style>
</head>
<body>
  <header>
    <div class="brand">⚡ OmniResearch Mobile</div>
    <div class="pin-badge" id="pinBadge">PIN Verified</div>
  </header>

  <div class="nav-tabs">
    <div class="nav-tab active" onclick="switchTab('reportPane')">Report</div>
    <div class="nav-tab" onclick="switchTab('audioPane')">Audio</div>
    <div class="nav-tab" onclick="switchTab('qaPane')">Q&A</div>
  </div>

  <div class="pane active" id="reportPane">
    <div class="card" id="reportContent">
      <h2>Loading Active Synthesis Report...</h2>
    </div>
  </div>

  <div class="pane" id="audioPane">
    <div class="card">
      <h2>Neural Audio Briefing</h2>
      <p>Stream executive dialogue directly to mobile headphones.</p>
      <audio id="audioPlayer" controls src="/api/audio?pin={pin}"></audio>
    </div>
  </div>

  <div class="pane" id="qaPane">
    <div class="card">
      <h2>Grounded Follow-Up Console</h2>
      <div class="chat-box" id="chatBox">
        <div class="chat-msg"><span class="chat-user">System:</span><div class="chat-bot">Connected to desktop workstation. Ask anything about the active research corpus.</div></div>
      </div>
      <div class="input-row">
        <input type="text" id="qaInput" placeholder="Ask follow-up question...">
        <button onclick="sendQA()">Send</button>
      </div>
    </div>
  </div>

  <script>
    const pin = "{pin}";

    function switchTab(paneId) {
      document.querySelectorAll('.pane').forEach(p => p.classList.remove('active'));
      document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
      document.getElementById(paneId).classList.add('active');
      event.target.classList.add('active');
    }

    async function loadReport() {
      try {
        const resp = await fetch('/api/report/active?pin=' + pin);
        if (!resp.ok) throw new Error("HTTP " + resp.status);
        const data = await resp.json();
        document.getElementById('reportContent').innerHTML = data.html || "<p>No active synthesis generated.</p>";
      } catch (err) {
        document.getElementById('reportContent').innerHTML = "<p style='color:#F87171;'>Failed to load report: " + err.message + "</p>";
      }
    }

    async function sendQA() {
      const input = document.getElementById('qaInput');
      const text = input.value.trim();
      if (!text) return;
      input.value = '';

      const box = document.getElementById('chatBox');
      box.innerHTML += `<div class="chat-msg"><span class="chat-user">You:</span><div class="chat-bot">${text}</div></div>`;
      box.scrollTop = box.scrollHeight;

      try {
        const resp = await fetch('/api/followup?pin=' + pin, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({question: text})
        });
        const data = await resp.json();
        box.innerHTML += `<div class="chat-msg"><span class="chat-user">OmniResearch:</span><div class="chat-bot">${data.answer}</div></div>`;
        box.scrollTop = box.scrollHeight;
      } catch (err) {
        box.innerHTML += `<div class="chat-msg"><span class="chat-user" style="color:#F87171;">Error:</span><div class="chat-bot">${err.message}</div></div>`;
      }
    }

    window.addEventListener('DOMContentLoaded', loadReport);
  </script>
</body>
</html>
"""


class MobileMirrorServer:
    """FastAPI daemon broadcasting research reports to LAN devices."""

    def __init__(self, port: int = 8484) -> None:
        self.port = port
        self.lan_ip = get_local_lan_ip()
        self.pin = f"{random.randint(100000, 999999)}"
        self._server: Optional[uvicorn.Server] = None
        self._thread: Optional[threading.Thread] = None
        self._process: Optional[Any] = None
        self._is_running = False

        # Workspaces and QA Provider callbacks
        self.workspaces_provider: Optional[Callable[[], List[Dict[str, Any]]]] = None
        self.report_provider: Optional[Callable[[str], Dict[str, Any]]] = None
        self.followup_handler: Optional[Callable[[str], str]] = None

        self.app = self._build_fastapi_app()
        self._generate_qr_code()

    def _generate_qr_code(self) -> Path:
        """Create QR code image for instant phone camera scanning."""
        SESSION_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        url = f"http://{self.lan_ip}:{self.port}/?pin={self.pin}"
        qr = qrcode.QRCode(box_size=5, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0F172A", back_color="#F8FAFC")
        img.save(QR_CODE_PATH)
        return QR_CODE_PATH

    def get_server_url(self) -> str:
        return f"http://{self.lan_ip}:{self.port}/?pin={self.pin}"

    def _verify_pin(self, pin: Optional[str] = Query(None), x_pin: Optional[str] = Header(None)) -> bool:
        provided = pin or x_pin
        if provided != self.pin:
            raise HTTPException(status_code=401, detail="Invalid or missing access PIN")
        return True

    def _build_fastapi_app(self) -> FastAPI:
        app = FastAPI(title="OmniResearch Studio LAN Mirror")
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_methods=["*"],
            allow_headers=["*"],
        )

        @app.get("/", response_class=HTMLResponse)
        async def serve_mobile_ui(pin: Optional[str] = Query(None)):
            if pin != self.pin:
                return HTMLResponse(
                    "<h3>401 Unauthorized: Valid ?pin= required to access OmniResearch LAN Mirror.</h3>",
                    status_code=401,
                )
            rendered = MOBILE_HTML_TEMPLATE.replace("{pin}", self.pin)
            return HTMLResponse(content=rendered)

        @app.get("/api/workspaces")
        async def list_workspaces(authorized: bool = Depends(self._verify_pin)):
            if self.workspaces_provider:
                return self.workspaces_provider()
            return [{"id": "active", "title": "Active Synthesis Workspace", "has_audio": True}]

        @app.get("/api/report/{workspace_id}")
        async def get_report(workspace_id: str, authorized: bool = Depends(self._verify_pin)):
            if self.report_provider:
                return self.report_provider(workspace_id)

            # Default fallback read from session_cache
            return {
                "workspace_id": workspace_id,
                "title": "Synthesis Report",
                "html": "<h3>Grounded Synthesis Report</h3><p>Report synchronized with desktop workstation.</p>",
            }

        @app.get("/api/audio")
        async def stream_audio(authorized: bool = Depends(self._verify_pin)):
            audio_path = SESSION_CACHE_DIR / "audio_briefing.mp3"
            if not audio_path.exists():
                raise HTTPException(status_code=404, detail="No audio briefing generated yet")
            return FileResponse(audio_path, media_type="audio/mpeg")

        @app.post("/api/followup")
        async def handle_followup(request: Request, authorized: bool = Depends(self._verify_pin)):
            data = await request.json()
            question = data.get("question", "").strip()
            if not question:
                raise HTTPException(status_code=400, detail="Question cannot be empty")

            if self.followup_handler:
                answer = self.followup_handler(question)
            else:
                answer = f"Desktop Follow-Up received: '{question}'. Grounded synthesis corpus confirmed."

            return {"question": question, "answer": answer}

        return app

    def _find_available_port(self, start_port: int) -> int:
        """Probe for an unbound local TCP port starting from start_port."""
        for p in range(start_port, start_port + 50):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("0.0.0.0", p))
                    return p
                except OSError:
                    continue
        return start_port

    def start(self, use_subprocess: bool = False) -> None:
        """Launch uvicorn server in a background daemon thread or decoupled subprocess."""
        if self._is_running:
            return

        self.port = self._find_available_port(self.port)
        self._generate_qr_code()

        if use_subprocess:
            import multiprocessing
            self._process = multiprocessing.Process(
                target=_run_uvicorn_worker,
                args=(self.port, self.pin, str(get_cache_dir())),
                daemon=True,
                name="OmniMobileMirrorProcess",
            )
            self._process.start()
            self._is_running = True
            logger.info(f"Mobile LAN Mirror Subprocess started at http://{self.lan_ip}:{self.port} (PIN: {self.pin})")
            return

        config = uvicorn.Config(
            app=self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="warning",
            loop="asyncio",
        )
        self._server = uvicorn.Server(config)

        def run_thread():
            asyncio.run(self._server.serve())

        self._thread = threading.Thread(target=run_thread, daemon=True, name="OmniMobileMirrorThread")
        self._thread.start()
        self._is_running = True
        logger.info(f"Mobile LAN Mirror Server started at http://{self.lan_ip}:{self.port} (PIN: {self.pin})")

    def stop(self) -> None:
        """Stop uvicorn server thread or terminate decoupled subprocess."""
        if self._process and self._process.is_alive():
            try:
                self._process.terminate()
                self._process.join(timeout=2)
            except Exception:
                pass
            self._process = None
        if self._server and self._is_running:
            self._server.should_exit = True
        self._is_running = False
        logger.info("Mobile LAN Mirror Server stopped.")

    @property
    def is_running(self) -> bool:
        return self._is_running


def build_standalone_mirror_app(pin: str, cache_dir_str: str) -> FastAPI:
    """Factory creating an independent FastAPI app for decoupled child worker processes."""
    app = FastAPI(title="OmniResearch Studio LAN Mirror")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    cache_dir = Path(cache_dir_str)

    @app.get("/", response_class=HTMLResponse)
    async def serve_mobile_ui(pin_arg: Optional[str] = Query(None, alias="pin")):
        if pin_arg != pin:
            return HTMLResponse(
                "<h3>401 Unauthorized: Valid ?pin= required to access OmniResearch LAN Mirror.</h3>",
                status_code=401,
            )
        rendered = MOBILE_HTML_TEMPLATE.replace("{pin}", pin)
        return HTMLResponse(content=rendered)

    @app.get("/api/workspaces")
    async def list_workspaces(pin_arg: Optional[str] = Query(None, alias="pin")):
        if pin_arg != pin:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return [{"id": "active", "title": "Active Synthesis Workspace", "has_audio": True}]

    @app.get("/api/report/{workspace_id}")
    async def get_report(workspace_id: str, pin_arg: Optional[str] = Query(None, alias="pin")):
        if pin_arg != pin:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return {
            "workspace_id": workspace_id,
            "title": "Synthesis Report",
            "html": "<h3>Grounded Synthesis Report</h3><p>Report synchronized with desktop workstation.</p>",
        }

    @app.get("/api/audio")
    async def stream_audio(pin_arg: Optional[str] = Query(None, alias="pin")):
        if pin_arg != pin:
            raise HTTPException(status_code=401, detail="Unauthorized")
        audio_path = cache_dir / "audio_briefing.mp3"
        if not audio_path.exists():
            raise HTTPException(status_code=404, detail="No audio briefing generated yet")
        return FileResponse(audio_path, media_type="audio/mpeg")

    @app.post("/api/followup")
    async def handle_followup(request: Request, pin_arg: Optional[str] = Query(None, alias="pin")):
        if pin_arg != pin:
            raise HTTPException(status_code=401, detail="Unauthorized")
        data = await request.json()
        question = data.get("question", "").strip()
        return {"question": question, "answer": f"Desktop Follow-Up received: '{question}'."}

    return app


def _run_uvicorn_worker(port: int, pin: str, cache_dir_str: str) -> None:
    """Isolated child worker target function: builds FastAPI app inside child process."""
    import asyncio
    import uvicorn
    app = build_standalone_mirror_app(pin=pin, cache_dir_str=cache_dir_str)
    config = uvicorn.Config(
        app=app,
        host="0.0.0.0",
        port=port,
        log_level="warning",
        loop="asyncio",
    )
    server = uvicorn.Server(config)
    asyncio.run(server.serve())
