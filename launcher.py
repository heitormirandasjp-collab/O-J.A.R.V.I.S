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


def _acquire_single_lock() -> bool:
    """True se esta é a primeira instância do JARVIS (Windows: mutex nomeado).

    O mutex fica aberto até o processo morrer (o SO libera sozinho — nada de
    lock órfão). Rodar o `.exe` de novo com o app aberto NÃO deve abrir outra
    janela: deve focar a existente.
    """
    if sys.platform != "win32":
        return True  # projeto é Windows-only; sem trava aqui
    import ctypes

    ERROR_ALREADY_EXISTS = 183
    # use_last_error=True + get_last_error(): forma confiável de ler o
    # GetLastError sem corrida com as chamadas internas do próprio ctypes.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p)
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    kernel32.CreateMutexW(None, False, "JARVIS_Singleton_Mutex")
    return ctypes.get_last_error() != ERROR_ALREADY_EXISTS


def _focus_existing_window() -> bool:
    """Traz para frente a janela do JARVIS (Edge --app ou Electron); True se achou.

    A janela do app tem o título da página (`JARVIS — Command Center`). Consoles
    (a janela preta do próprio `.exe`, incluindo o Windows Terminal) ficam de
    fora: o foco é para a interface, não para o terminal.
    """
    if sys.platform != "win32":
        return False
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    # BOOL CALLBACK EnumWindows(HWND, LPARAM) — o wintypes deste Python não
    # traz WNDENUMPROC, então o tipo do callback é montado aqui.
    WNDENUMPROC = ctypes.WINFUNCTYPE(
        wintypes.BOOL, wintypes.HWND, wintypes.LPARAM
    )
    # argtypes/restype explícitos: sem eles o ctypes converte HWND/param por
    # padrão (c_int) e 64 bits pode estourar ou truncar.
    user32.EnumWindows.argtypes = (WNDENUMPROC, wintypes.LPARAM)
    user32.EnumWindows.restype = wintypes.BOOL
    user32.IsWindowVisible.argtypes = (wintypes.HWND,)
    user32.IsWindowVisible.restype = wintypes.BOOL
    user32.GetClassNameW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetClassNameW.restype = ctypes.c_int
    user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
    user32.GetWindowTextLengthW.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.IsIconic.argtypes = (wintypes.HWND,)
    user32.IsIconic.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.ShowWindow.restype = wintypes.BOOL
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.BringWindowToTop.argtypes = (wintypes.HWND,)
    user32.BringWindowToTop.restype = wintypes.BOOL
    _EXCLUIR_CLASSES = {"ConsoleWindowClass", "CASCADIA_HOSTING_WINDOW_CLASS"}
    achados: list[int] = []

    @WNDENUMPROC
    def _enum(hwnd, _):
        if not user32.IsWindowVisible(hwnd):
            return True
        classe = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, classe, 64)
        if classe.value in _EXCLUIR_CLASSES:
            return True
        tam = user32.GetWindowTextLengthW(hwnd)
        if tam <= 0:
            return True
        buf = ctypes.create_unicode_buffer(tam + 1)
        user32.GetWindowTextW(hwnd, buf, tam + 1)
        if buf.value.startswith("JARVIS"):
            achados.append(hwnd)
        return True

    user32.EnumWindows(_enum, 0)
    if not achados:
        return False
    hwnd = achados[0]
    SW_RESTORE = 9
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    user32.SetForegroundWindow(hwnd)
    user32.BringWindowToTop(hwnd)
    return True


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

    # ── instância única: segunda execução foca a janela existente ──────────
    if not _acquire_single_lock():
        url = f"http://127.0.0.1:{UI_PORT}"
        if os.environ.get("JARVIS_NO_WINDOW") == "1":
            # backend secundário (ex.: Electron): a instância dona do mutex já
            # serve tudo — só confirmamos que a interface responde e saímos.
            ok = wait_http(UI_PORT, "/")
            print(f"\n  instância única já ativa — interface "
                  f"{'OK' if ok else 'indisponível'} ({url})")
            return 0
        if _focus_existing_window():
            print("\n  O JARVIS já está em execução — janela existente em foco.")
            return 0
        # instância viva mas sem janela (a anterior foi fechada com o console
        # ainda no ar): reabre a interface apontando para os serviços dela.
        if wait_http(UI_PORT, "/"):
            open_window(url)
            print(f"\n  O JARVIS já está em execução — nova janela em {url}")
        else:
            print(f"\n  O JARVIS já está em execução, mas a interface não "
                  f"respondeu ({url}).")
        return 0

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
