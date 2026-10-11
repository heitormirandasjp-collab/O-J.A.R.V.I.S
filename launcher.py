"""
JARVIS — inicializador do aplicativo (vira JARVIS.exe).

Sobe os dois serviços no mesmo processo e abre a janela do app:
  • backend de ferramentas/voz  → http://127.0.0.1:8000
  • interface + chat (Groq)     → http://127.0.0.1:8755
"""
from __future__ import annotations

import importlib.util
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

# Módulos usados por backend/main.py. Ele é carregado como DADO (via importlib), então o
# PyInstaller não enxerga os imports dele — declaramos aqui só para garantir o empacotamento.
import edge_tts  # noqa: F401  (vozes neurais do Edge TTS)
import psutil  # noqa: F401
import shutil  # noqa: F401
import tempfile  # noqa: F401
import uuid  # noqa: F401
import wave  # noqa: F401
import xml.etree.ElementTree  # noqa: F401

import app as ui_module  # noqa: E402  (interface + chat)

HERE = Path(__file__).resolve().parent
TOOLS_PORT = int(os.environ.get("JARVIS_TOOLS_PORT", "8000"))
UI_PORT = int(os.environ.get("JARVIS_UI_PORT", "8755"))


def resource_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", HERE))
    return HERE


def load_tools_app():
    """Carrega backend/main.py (o mesmo arquivo do modo dev)."""
    backend_dir = resource_dir() / "backend"
    candidates = [backend_dir / "main.py", HERE / "backend" / "main.py"]
    for path in candidates:
        if path.is_file():
            spec = importlib.util.spec_from_file_location("jarvis_tools", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)  # type: ignore[union-attr]
            return module.app
    raise RuntimeError("backend/main.py não encontrado")


def port_open(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.4)
        return s.connect_ex(("127.0.0.1", port)) == 0


def serve(app_obj, port: int, label: str) -> None:
    config = uvicorn.Config(app_obj, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    threading.Thread(target=server.run, name=label, daemon=True).start()


def wait_http(port: int, path: str, timeout: float = 40.0) -> bool:
    import urllib.request

    end = time.time() + timeout
    while time.time() < end:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.4)
    return False


def open_window(url: str) -> None:
    """Abre uma janela de app (sem barra de endereço) no Edge/Chrome; senão, navegador padrão."""
    profile = Path(os.environ.get("APPDATA") or Path.home()) / "JARVIS" / "browser"
    profile.mkdir(parents=True, exist_ok=True)
    candidates = [
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
    ]
    for exe in candidates:
        if exe.is_file():
            try:
                subprocess.Popen(
                    [
                        str(exe),
                        f"--app={url}",
                        f"--user-data-dir={profile}",
                        "--no-first-run",
                        "--no-default-browser-check",
                    ]
                )
                return
            except Exception:  # noqa: BLE001
                continue
    webbrowser.open(url)


def main() -> int:
    print("=" * 58)
    print("  JARVIS — Command Center")
    print("=" * 58)

    if port_open(TOOLS_PORT):
        print(f"  ferramentas/voz: já em execução na porta {TOOLS_PORT}")
    else:
        serve(load_tools_app(), TOOLS_PORT, "jarvis-tools")
        print(f"  ferramentas/voz: subindo na porta {TOOLS_PORT}...")

    if port_open(UI_PORT):
        print(f"  interface:       já em execução na porta {UI_PORT}")
    else:
        serve(ui_module.app, UI_PORT, "jarvis-ui")
        print(f"  interface:       subindo na porta {UI_PORT}...")

    tools_ok = wait_http(TOOLS_PORT, "/health")
    ui_ok = wait_http(UI_PORT, "/")
    print(f"  ferramentas/voz: {'OK' if tools_ok else 'INDISPONÍVEL'}")
    print(f"  interface:       {'OK' if ui_ok else 'INDISPONÍVEL'}")

    url = f"http://127.0.0.1:{UI_PORT}"
    if os.environ.get("JARVIS_NO_WINDOW") == "1":
        print(f"\n  janela não aberta (JARVIS_NO_WINDOW=1) — interface em {url}")
    elif ui_ok:
        open_window(url)
        print(f"\n  JARVIS aberto em {url}")
    else:
        print("\n  Não foi possível subir a interface.")

    print("  (feche esta janela ou pressione Ctrl+C para encerrar)\n")
    try:
        while True:
            time.sleep(2)
    except KeyboardInterrupt:
        print("  encerrando JARVIS...")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
