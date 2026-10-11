"""
JARVIS — backend local (FastAPI), feito do zero.
Porta 8000 (localhost apenas).

Endpoints:
  POST /exec        -> executa um comando no Windows (shell=True; exige X-Jarvis-Token)
  POST /read-file   -> lê o conteúdo de um arquivo
  GET  /sysinfo     -> CPU, RAM e disco reais (psutil)
  POST /tts         -> sintetiza voz com Piper (WAV, pt-BR); Edge TTS é a reserva
  GET  /stocks      -> cotações (brapi.dev para BR, Yahoo para o resto)
  GET  /currencies  -> USD/BRL, EUR/BRL, USD/EUR (AwesomeAPI)
  GET  /weather     -> clima atual + previsão de hoje (wttr.in; open-meteo de reserva)
  GET  /health      -> status do backend
"""
from __future__ import annotations

import html
import io
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import tempfile
import time
import uuid
import wave
import webbrowser
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import psutil
import requests
from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

# ── caminhos ────────────────────────────────────────────────────────────
APP_DIR = Path(__file__).resolve().parent          # jarvis/backend
PROJECT_ROOT = APP_DIR.parent.parent               # raiz do projeto JARVIS

MODEL_NAME = "pt-BR-razo-medium.onnx"
VOICES_DIR = PROJECT_ROOT / "voices"
def _app_dir() -> Path:
    """Pasta do executável (quando empacotado) ou do backend (modo dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return APP_DIR


_VOICE_FILES = (MODEL_NAME, "pt_BR-faber-medium.onnx", "pt_BR-cadu-medium.onnx")


def _voice_dirs() -> list[Path]:
    """Pastas onde procurar a voz: projeto, pasta do exe e até 4 níveis acima dele."""
    exe = _app_dir()
    dirs: list[Path] = [VOICES_DIR, PROJECT_ROOT, exe, exe / "voices"]
    up = exe
    for _ in range(4):
        up = up.parent
        dirs += [up, up / "voices"]
    seen: set[str] = set()
    out: list[Path] = []
    for d in dirs:
        key = str(d)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def _voice_candidates() -> list[str]:
    """Caminhos absolutos possíveis para o modelo de voz."""
    out = [os.environ.get("PIPER_MODEL", ""), os.environ.get("JARVIS_PIPER_MODEL", "")]
    for base in _voice_dirs():
        out += [str(base / name) for name in _VOICE_FILES]
    return out


MODEL_CANDIDATES = [c for c in _voice_candidates() if c]

# vozes pt-BR que podem ser baixadas sob demanda (qualidade melhor que a razo)
DOWNLOADABLE_VOICES = {
    "pt_BR-faber-medium": (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx"
    ),
    "pt_BR-cadu-medium": (
        "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/cadu/medium/pt_BR-cadu-medium.onnx"
    ),
}


def _voices_download_dir() -> Path:
    """Onde salvar uma voz baixada: pasta do exe (empacotado) ou voices/ do projeto."""
    if getattr(sys, "frozen", False):
        return _app_dir() / "voices"
    return VOICES_DIR


def list_voices() -> list[Path]:
    """Todos os modelos Piper (.onnx) já presentes na máquina."""
    found: list[Path] = []
    for base in _voice_dirs():
        if base.is_dir():
            found += [p for p in sorted(base.glob("*.onnx")) if not p.name.endswith(".json")]
    seen = set()
    uniq: list[Path] = []
    for p in found:
        if p.name not in seen:
            seen.add(p.name)
            uniq.append(p)
    return uniq


def find_model() -> Path | None:
    """Escolhe o modelo de voz: ambiente > melhor qualidade (faber/cadu) > qualquer .onnx."""
    for env_name in ("PIPER_MODEL", "JARVIS_PIPER_MODEL"):
        env_val = os.environ.get(env_name, "")
        if env_val and Path(env_val).is_file():
            return Path(env_val)

    dirs = _voice_dirs()
    # preferência por voz mais natural, independente da pasta
    # ordem de preferência: cadu (voz masculina mais grave) → faber → razo
    for name in ("pt_BR-cadu-medium.onnx", "pt_BR-faber-medium.onnx", MODEL_NAME):
        for base in dirs:
            cand = base / name
            if cand.is_file():
                return cand
    voices = list_voices()
    if voices:
        return voices[0]
    for hit in PROJECT_ROOT.glob("**/*.onnx"):
        if hit.is_file() and not hit.name.endswith(".json"):
            return hit
    return None


MODEL_PATH = find_model()
CONFIG_PATH = MODEL_PATH.with_suffix(".onnx.json") if MODEL_PATH else None

app = FastAPI(title="JARVIS Backend", version="1.0.0")


def _allowed_origins() -> list[str]:
    """Só a própria UI local pode chamar o backend — nunca "*" (ajustável por env)."""
    env = os.environ.get("JARVIS_ALLOWED_ORIGINS")
    if env:
        return [o.strip() for o in env.split(",") if o.strip()]
    return ["http://127.0.0.1:8755", "http://localhost:8755"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)


@app.middleware("http")
async def _security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


UA = {"User-Agent": "Mozilla/5.0 (JARVIS local assistant)"}


def _decode_output(data: bytes | None) -> str:
    """Decodifica a saída de ferramentas do Windows (OEM = cp850, ANSI = cp1252)."""
    if not data:
        return ""
    for enc in ("utf-8", "cp850", "cp1252"):
        try:
            return data.decode(enc).strip()
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace").strip()


# ── segurança: limites, blacklist e log ────────────────────────────────
EXEC_TIMEOUT_MAX = 30          # segundos por comando
EXEC_OUTPUT_LIMIT = 10_000     # caracteres de saída por comando
READ_MAX_BYTES = 1_000_000     # 1 MB por arquivo
TTS_MAX_CHARS = 2000           # texto máximo enviado ao Piper
_EXEC_HISTORY_LIMIT = 200
_SECURITY_LOCK = threading.Lock()

# comandos destrutivos/perigosos: bloqueados ANTES de qualquer execução
_EXEC_BLOCK_RE = re.compile(
    r"|".join(
        [
            r"\brm\s+-[a-z]*[rf]",          # rm -rf / rm -f
            r"\bdel\s+/[fsq]",              # del /f /s /q
            r"\bformat\s+[a-z]:",           # format C:
            r"\bmkfs\b", r"\bdiskpart\b", r"\bfdisk\b", r"\bdd\s+if=",
            r":\(\)\s*\{",                 # fork bomb
            r"\bshutdown\b", r"\bpoweroff\b", r"\breboot\b",   # energia tem endpoint próprio (/power)
            r"\bbcdedit\b", r"\bvssadmin\b", r"\bcipher\s+/[wW]", r"\bwevtutil\s+cl\b",
            r"\breg\s+delete\b", r"\btakeown\b", r"\bicacls\b.*/grant", r"\bnet\s+(user|localgroup)\b",
            r"\bsc\s+delete\b", r"\bschtasks\b.*/create", r"\bnetsh\s+firewall\b", r"\bwmic\b.*delete",
            r"\bRemove-Item\b.*-Recurse", r"\bmklink\b",
            # v1.0.16 — furos fechados (auditoria): encoding do PowerShell, rd /s /q,
            # Remove-Item -Force (mesmo sem -Recurse), Storage cmdlets, parar serviços,
            # taskkill com força + nome de imagem
            r"\b(?:powershell|pwsh)\b[^|\n]*\s-(?:e|enc|enco|encod|encode|encodedcommand)\b",
            r"(?:rmdir|rd)\s+/s\s+/q\b",
            r"\bRemove-Item\b.*-Force",
            r"\bFormat-Volume\b", r"\bClear-Disk\b",
            r"\bnet\s+stop\b",
            r"\btaskkill\b(?=[^|\n]*/f)(?=[^|\n]*/im)",
        ]
    ),
    re.IGNORECASE,
)


def _security_log(kind: str, detail: str, blocked: bool = False) -> None:
    """Registra evento de segurança em %APPDATA%\\JARVIS\\security.log."""
    line = f"{datetime.now().isoformat(timespec='seconds')} [{kind}] {'BLOQUEADO ' if blocked else ''}{detail}\n"
    try:
        with _SECURITY_LOCK:
            with (_data_dir() / "security.log").open("a", encoding="utf-8") as fh:
                fh.write(line)
    except Exception:  # noqa: BLE001
        pass


@app.exception_handler(Exception)
async def _unhandled_error(request: Request, exc: Exception) -> JSONResponse:
    """Camada extra: qualquer exceção não tratada vira 500 JSON e vai para o security.log.

    Não substitui os try/except existentes — só garante que nenhum 500 cru chegue ao front.
    O stacktrace NUNCA é devolvido ao cliente; tipo + mensagem ficam só no log.
    """
    detail = str(exc).strip() or type(exc).__name__
    _security_log(
        "erro",
        f"{request.method} {request.url.path} -> 500 {type(exc).__name__}: {detail}",
    )
    return JSONResponse({"error": "internal_server_error", "detail": detail}, status_code=500)


def _append_exec_history(entry: dict[str, Any]) -> None:
    """Guarda os últimos comandos executados em exec_history.json (APPDATA\\JARVIS)."""
    path = _data_dir() / "exec_history.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else []
        if not isinstance(data, list):
            data = []
    except Exception:  # noqa: BLE001
        data = []
    data.append(entry)
    try:
        with _SECURITY_LOCK:
            path.write_text(json.dumps(data[-_EXEC_HISTORY_LIMIT:], ensure_ascii=False, indent=1), encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


# ── modelos de entrada ──────────────────────────────────────────────────
class ExecIn(BaseModel):
    cmd: str
    timeout: int = 30


class ReadFileIn(BaseModel):
    path: str
    max_bytes: int = READ_MAX_BYTES


class TTSIn(BaseModel):
    text: str
    rate: float = 1.0  # > 1 = mais lento (length_scale do Piper); 1.0 = padrão do modelo
    voice: str | None = None  # Piper: arquivo .onnx · Edge: ShortName (ex.: pt-BR-AntonioNeural)
    pitch: float = 0.0  # semitons: negativo = voz mais grave (ex.: -2)
    engine: str | None = None  # "piper" (padrão) ou "edge" (vozes neurais da Microsoft)


class VoiceIn(BaseModel):
    name: str


# ── autenticação de /exec e /power (v1.0.16) ─────────────────────────────
def require_exec_token(x_jarvis_token: str | None = Header(default=None)) -> str:
    """Dependência obrigatória de POST /exec e POST /power.

    Exige o header X-Jarvis-Token igual à variável de ambiente JARVIS_EXEC_TOKEN.
    Sem a env configurada as rotas ficam proibidas (403) — deny-by-default.
    """
    expected = (os.environ.get("JARVIS_EXEC_TOKEN") or "").strip()
    if not expected:
        _security_log("auth", "JARVIS_EXEC_TOKEN não configurada — /exec e /power proibidos", blocked=True)
        raise HTTPException(
            status_code=403,
            detail=(
                "JARVIS_EXEC_TOKEN não configurada: /exec e /power estão proibidos. "
                "Defina a variável de ambiente JARVIS_EXEC_TOKEN para habilitá-los."
            ),
        )
    if not x_jarvis_token or not secrets.compare_digest(
        x_jarvis_token.encode("utf-8"), expected.encode("utf-8")
    ):
        _security_log("auth", "token ausente/inválido em /exec ou /power", blocked=True)
        raise HTTPException(
            status_code=403,
            detail=(
                "token ausente ou inválido: envie o header X-Jarvis-Token "
                "com o valor de JARVIS_EXEC_TOKEN."
            ),
        )
    return expected


# ── 1. /exec ────────────────────────────────────────────────────────────
@app.post("/exec")
def exec_cmd(body: ExecIn, _exec_token: str = Depends(require_exec_token)):
    cmd = (body.cmd or "").strip()
    if not cmd:
        return JSONResponse({"output": "", "error": "comando vazio"}, status_code=400)
    if len(cmd) > 1000:
        _security_log("exec", f"comando grande demais ({len(cmd)} chars)", blocked=True)
        return JSONResponse(
            {"output": "", "error": "comando grande demais", "cmd": cmd[:80], "exit_code": -1, "blocked": True},
            status_code=413,
        )
    # blacklist: comandos destrutivos/de sistema não passam daqui
    if _EXEC_BLOCK_RE.search(cmd):
        _security_log("exec", f"comando bloqueado (blacklist): {cmd}", blocked=True)
        return JSONResponse(
            {
                "output": "",
                "error": "🔒 comando bloqueado por segurança (destrutivo ou de sistema)",
                "cmd": cmd,
                "exit_code": -1,
                "blocked": True,
            },
            status_code=403,
        )
    timeout = max(1, min(int(body.timeout or EXEC_TIMEOUT_MAX), EXEC_TIMEOUT_MAX))
    entry = {"at": datetime.now().isoformat(timespec="seconds"), "cmd": cmd, "timeout": timeout}
    try:
        proc = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            timeout=timeout,
            cwd=str(PROJECT_ROOT),
        )
        out = _decode_output(proc.stdout)[:EXEC_OUTPUT_LIMIT]
        err = _decode_output(proc.stderr)[:EXEC_OUTPUT_LIMIT]
        entry["exit_code"] = proc.returncode
        _append_exec_history(entry)
        _security_log("exec", f"cmd={cmd!r} exit={proc.returncode}")
        return {
            "output": out,
            "error": err if proc.returncode else None,
            "exit_code": proc.returncode,
            "cmd": cmd,
            "truncated": len(out) >= EXEC_OUTPUT_LIMIT,
        }
    except subprocess.TimeoutExpired:
        entry["exit_code"] = -1
        _append_exec_history(entry)
        _security_log("exec", f"TIMEOUT ({timeout}s): {cmd}")
        return {"output": "", "error": f"tempo esgotado ({timeout}s)", "exit_code": -1, "cmd": cmd}
    except Exception as exc:  # noqa: BLE001
        _security_log("exec", f"falha: {exc}")
        return {"output": "", "error": str(exc), "exit_code": -1, "cmd": cmd}


# ── 2. /read-file ───────────────────────────────────────────────────────
# arquivos que NUNCA podem ser lidos (credenciais, chaves, hashes de senha)
_READ_DENY_NAMES = {
    ".env", ".netrc", "_netrc", ".git-credentials", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    "shadow", "passwd", "gshadow", "sam", "security", "unattend.xml", "config.json",
}
_READ_DENY_SUFFIXES = {".key", ".pem", ".pfx", ".p12", ".kdbx", ".jks", ".keystore", ".ppk", ".asc", ".ovpn"}
_READ_DENY_PARTS = (
    '/windows/system32/config', '/windows/system32/sam', '/windows/system32/security',
    '/windows/system32/drivers/etc', '/appdata/roaming/microsoft/credentials',
    '/appdata/local/microsoft/credentials', '/etc/shadow', '/etc/passwd', '/etc/sudoers',
    '/.ssh/', '/root/', '/.git/config', '/id_rsa', '/id_ed25519',
)


def _allowed_read_roots() -> list[Path]:
    """Pastas que podem ser lidas: Documents, Downloads, Desktop, a pasta do app e a de dados.
    Amplie com a variável de ambiente JARVIS_READ_ROOTS (separadas por ';')."""
    roots: list[Path] = []
    env = os.environ.get("JARVIS_READ_ROOTS")
    if env:
        roots += [Path(p).expanduser() for p in env.split(os.pathsep) if p.strip()]
    home = Path.home()
    for name in ("Documents", "Downloads", "Desktop", "Documentos", "Documentos"):
        cand = home / name
        if cand.is_dir():
            roots.append(cand)
    roots += [PROJECT_ROOT, APP_DIR, _data_dir()]
    out: list[Path] = []
    for r in roots:
        try:
            out.append(r.resolve())
        except Exception:  # noqa: BLE001
            continue
    return out


@app.post("/read-file")
def read_file(body: ReadFileIn):
    raw = (body.path or "").strip()
    if not raw:
        return JSONResponse({"error": "informe o caminho do arquivo"}, status_code=400)
    try:
        p = Path(raw).expanduser()
        try:
            p = p.resolve()
        except Exception:  # noqa: BLE001
            pass
        low = str(p).lower().replace("\\", "/")

        # 1) arquivos sensíveis (chaves, credenciais, hashes de senha)
        if (
            p.name.lower() in _READ_DENY_NAMES
            or p.suffix.lower() in _READ_DENY_SUFFIXES
            or any(part in low for part in _READ_DENY_PARTS)
        ):
            _security_log("read-file", f"bloqueado (arquivo sensível): {p}", blocked=True)
            return JSONResponse({"error": "🔒 leitura bloqueada: arquivo sensível"}, status_code=403)

        # 2) só dentro das pastas permitidas
        roots = _allowed_read_roots()
        if not any(str(p).startswith(str(r)) for r in roots):
            _security_log("read-file", f"fora das pastas permitidas: {p}", blocked=True)
            return JSONResponse(
                {"error": "🔒 leitura restrita a Documents, Downloads, Desktop e à pasta do JARVIS"},
                status_code=403,
            )

        if not p.is_file():
            return JSONResponse({"error": f"arquivo não encontrado: {p}"}, status_code=404)

        # 3) limite de tamanho (máximo 1 MB)
        size = p.stat().st_size
        limit = max(1, min(int(body.max_bytes or READ_MAX_BYTES), READ_MAX_BYTES))
        data = p.read_bytes()[:limit]
        try:
            content = data.decode("utf-8")
        except UnicodeDecodeError:
            content = data.decode("latin-1", errors="replace")
        _security_log("read-file", f"{p} ({min(size, limit)} bytes)")
        return {"path": str(p), "content": content, "size": size, "truncated": size > limit, "error": None}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=400)


# ── 3. /sysinfo ─────────────────────────────────────────────────────────
@app.get("/sysinfo")
def sysinfo():
    cpu = psutil.cpu_percent(interval=0.4)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage(str(PROJECT_ROOT.anchor or "C:\\"))
    boot = psutil.boot_time()
    try:
        host = socket.gethostname()
    except Exception:  # noqa: BLE001
        host = "desconhecido"
    return {
        "cpu": {"percent": round(cpu, 1), "cores": psutil.cpu_count(logical=True)},
        "ram": {
            "percent": round(mem.percent, 1),
            "used_gb": round(mem.used / 1024**3, 2),
            "total_gb": round(mem.total / 1024**3, 2),
        },
        "disk": {
            "percent": round(disk.percent, 1),
            "used_gb": round(disk.used / 1024**3, 2),
            "total_gb": round(disk.total / 1024**3, 2),
        },
        "uptime_hours": round((time.time() - boot) / 3600, 1),
        "boot_time": time.strftime("%d/%m %H:%M", time.localtime(boot)),
        "hostname": host,
        "os": f"Windows {sys.getwindowsversion().major}.{sys.getwindowsversion().build}"
        if sys.platform == "win32"
        else sys.platform,
        "python": sys.version.split()[0],
        "platform": f"{sys.platform}",
    }


# ── 4. /tts (Piper) ────────────────────────────────────────────────────
_tts_cache: dict[str, bytes] = {}
_voices: dict[str, Any] = {}
_voice_errors: dict[str, str] = {}


def resolve_voice(name: str | None) -> Path | None:
    """Resolve o modelo pedido pelo nome; sem nome, usa o padrão."""
    if name:
        for v in list_voices():
            if v.name == name or v.stem == name:
                return v
    return MODEL_PATH


def _load_voice(path: Path | None):
    """Carrega (e cacheia) um PiperVoice."""
    if path is None:
        return None
    key = str(path)
    if key in _voices:
        return _voices[key]
    if key in _voice_errors:
        return None
    try:
        from piper import PiperVoice  # type: ignore

        cfg = path.with_suffix(".onnx.json")
        voice = PiperVoice.load(str(path), config_path=str(cfg) if cfg.is_file() else None)
        _voices[key] = voice
        return voice
    except Exception as exc:  # noqa: BLE001
        _voice_errors[key] = f"falha ao carregar {path.name}: {exc}"
        return None


# abreviações comuns em texto digital (o Piper lê melhor por extenso)
_ABBREV = {
    "vc": "você", "vcs": "vocês", "pq": "porque", "tá": "está", "tô": "estou",
    "msm": "mesmo", "tbm": "também", "hj": "hoje", "blz": "beleza", "vlw": "valeu",
    "obg": "obrigado", "qdo": "quando", "qq": "qualquer", "kd": "cadê", "cmg": "comigo",
    "ctg": "contigo", "msg": "mensagem", "sra": "senhora", "dra": "doutora",
    "etc": "etcétera", "vs": "versus", "td": "tudo", "to": "estou", "ta": "está",
    "tava": "estava", "vdd": "verdade", "ngm": "ninguém", "flw": "falou",
    "pft": "por favor", "pfv": "por favor",    "hrs": "horas", "min": "minutos", "h": "horas",
}

_UNITS = [
    "zero", "um", "dois", "três", "quatro", "cinco", "seis", "sete", "oito", "nove",
    "dez", "onze", "doze", "treze", "catorze", "quinze", "dezesseis", "dezessete", "dezoito", "dezenove",
]
_TENS = {2: "vinte", 3: "trinta", 4: "quarenta", 5: "cinquenta", 6: "sessenta", 7: "setenta", 8: "oitenta", 9: "noventa"}
_HUNDREDS = {1: "cento", 2: "duzentos", 3: "trezentos", 4: "quatrocentos", 5: "quinhentos", 6: "seiscentos", 7: "setecentos", 8: "oitocentos", 9: "novecentos"}


def _int_to_words(n: int) -> str:
    """Escreve um inteiro em português (até bilhões)."""
    if n < 0:
        return "menos " + _int_to_words(-n)
    if n < 20:
        return _UNITS[n]
    if n < 100:
        d, u = divmod(n, 10)
        return _TENS[d] + (" e " + _UNITS[u] if u else "")
    if n < 1000:
        c, r = divmod(n, 100)
        base = "cem" if n == 100 else _HUNDREDS[c]
        return base + (" e " + _int_to_words(r) if r else "")
    for scale, singular, plural in ((10**9, "bilhão", "bilhões"), (10**6, "milhão", "milhões")):
        if n >= scale:
            q, r = divmod(n, scale)
            base = f"{_int_to_words(q)} {singular if q == 1 else plural}"
            if not r:
                return base
            return base + (" e " if r < 100 else " ") + _int_to_words(r)
    mil, r = divmod(n, 1000)
    base = "mil" if mil == 1 else f"{_int_to_words(mil)} mil"
    if not r:
        return base
    return base + (" e " if r < 100 or r % 100 == 0 else " ") + _int_to_words(r)


def _hours_to_words(t: str) -> str:
    """10:00 → "dez horas", 10:30 → "dez e meia", 14:30 → "duas e meia da tarde" etc."""
    def _render(hh: int, mm: int) -> str:
        _UNTIL_20 = _UNITS  # 1..19 (index 0..19)
        ones = _UNTIL_20[hh] if 0 <= hh <= 19 else ""
        meridian = "da manhã" if 0 <= hh < 12 else "da tarde"
        if mm == 0:
            h = _int_to_words(hh).replace("um", "uma") if hh == 1 else _int_to_words(hh)
            if hh == 1:
                return f"{h} hora {meridian}"
            return f"{h} horas {meridian}"
        if mm == 15:
            return f"{ones} e um quarto {meridian}"
        if mm == 30:
            return f"{ones} e meia {meridian}"
        if mm == 45:
            nxt = _int_to_words(hh + 1) if hh + 1 <= 23 else _int_to_words(0)
            return f"{nxt} sem quarto {meridian}"
        h = _int_to_words(hh)
        mins = _int_to_words(mm)
        return f"{h} e {mins} {meridian}"

    def repl(m: re.Match) -> str:
        hh = int(m.group("hh") or 0)
        mm = int(m.group("mm") or 0)
        sec = m.group("sec") or ""
        s = _render(hh, mm)
        if sec:
            s += f" e {_int_to_words(int(sec))}"
        return s

    return re.sub(r"(?P<hh>\d{1,2}):(?P<mm>\d{2})(?::(?P<sec>\d{2}))?", repl, t)


def _money_words(whole: int, cents: int, main_s: str, main_p: str, sub_s: str, sub_p: str) -> str:
    parts: list[str] = []
    if whole or not cents:
        parts.append(f"{_int_to_words(whole)} {main_s if whole == 1 else main_p}")
    if cents:
        parts.append(f"{_int_to_words(cents)} {sub_s if cents == 1 else sub_p}")
    return " e ".join(parts)


def _expand_numbers(t: str) -> str:
    """Valores por extenso: "R$ 4,99" → "quatro reais e noventa e nove centavos"."""

    # "1.299,50" → "1299,50" (ponto como separador de milhar)
    t = re.sub(r"(?<=\d)\.(?=\d{3}(?:\D|$))", "", t)

    def money(match: re.Match) -> str:
        sym = (match.group("sym") or "").upper()
        whole = int(match.group("i") or 0)
        cents = int((match.group("c") or "0")[:2].ljust(2, "0"))
        if "US" in sym or "USD" in sym:
            return _money_words(whole, cents, "dólar", "dólares", "centavo", "centavos")
        return _money_words(whole, cents, "real", "reais", "centavo", "centavos")

    t = re.sub(r"(?P<sym>R\$|US\$|\$)\s*(?P<i>\d{1,9})(?:[.,](?P<c>\d{1,2}))?", money, t, flags=re.I)

    # sinais antes de números: "-0,52" → "menos 0,52" (evita "menos vírgula ...")
    t = re.sub(r"(?<![\w])-\s*(?=\d)", "menos ", t)
    t = re.sub(r"(?<![\w])\+\s*(?=\d)", "mais ", t)

    def pct(match: re.Match) -> str:
        whole = _int_to_words(int(match.group(1)))
        cents = match.group(2)
        return f"{whole} vírgula {_int_to_words(int(cents))}" if cents else whole

    t = re.sub(r"\b(\d{1,4})(?:,(\d{1,2}))?\s*%", lambda m: pct(m) + " por cento", t)
    return t


def _speech_text(text: str) -> str:
    """Deixa o texto natural para leitura em voz alta (símbolos, abreviações, números, pausas)."""
    t = str(text or "")
    t = re.sub(r"```[\s\S]*?```", " (código omitido) ", t)
    t = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", t)
    # URLs e sufixos de fonte de notícia ("... - G1", "... | UOL") nunca devem ser falados
    t = re.sub(r"https?://\S+|www\.\S+", " ", t)
    t = re.sub(
        r"[ \t]*[-–—|]\s*(?:g1|ge|uol|folha|estad[aã]o|reuters|cnn|bbc|exame|valor|infomoney|oglobo)\s*$",
        " ",
        t,
        flags=re.IGNORECASE,
    )
    # símbolos que o Piper lê errado
    t = t.replace("→", ", ").replace("->", ", ").replace("·", ", ").replace("&", " e ").replace("/", " ou ")
    t = re.sub(r"[*_`#>|~\[\]{}<>^=+\\\u2500-\u257F]", " ", t)
    t = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]", " ", t)
    # dinheiro e porcentagem por extenso
    t = _expand_numbers(t)
    # pontos/horários: "São 10:00 H" → "São dez horas", "14:30" → "duas e meia da tarde" etc.
    t = _hours_to_words(t)
    # dinheiro e porcentagem por extenso
    t = _expand_numbers(t)
    # palavras coladas depois de pontuação ("olá.Como" → "olá. Como")
    t = re.sub(r"([.,!?;:])(?=[A-Za-zÀ-ÿ])", r"\1 ", t)
    # décimos restantes: 4,99 → 4 vírgula 99
    t = re.sub(r"(\d)[.,](\d{1,2})\b", r"\1 vírgula \2", t)
    # abreviações comuns: "vc" → "você", "Vdd" → "verdade", etc.
    t = re.sub(r"\b[A-Za-zÀ-ÿ]{1,4}\b", lambda m: _ABBREV.get(m.group(0).lower(), m.group(0)), t)
    # "HH:" oligonucleicamente:"10:00" → "dez horas" (caso especial já tratado acima)
    t = re.sub(r"((?<=\s)|(?<=\A)|(?<=[A-Za-zÀ-ÿéüõ ]))\s*(?P<hh>\d{1,2}):(?P<mm>\d{2})\s*(?=\s|$|[.,!?;:])", lambda m: _hours_to_words(m.group(0)) if m.group(0).strip() else " ", t)
    # pontuação que engasga a voz ("..." vira uma pausa natural)
    t = re.sub(r"\.{2,}", ". ", t)
    t = re.sub(r"([!?])\1+", r"\1", t)
    t = re.sub(r"\s*([,;:])\s*", r"\1 ", t)
    t = re.sub(r"\s+([.!?])", r"\1", t)
    t = re.sub(r"(?<=[.!?])(?=[^\s])", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()[:1500]


def _split_chunks(text: str, size: int = 200) -> list[str]:
    """Divide em pedaços de ~size caracteres nas fronteiras de frase (evita "perder o fôlego")."""
    sentences = re.split(r"(?<=[.!?;:])\s+", text)
    chunks: list[str] = []
    cur = ""
    for s in sentences:
        if not s:
            continue
        if not cur:
            cur = s
        elif len(cur) + len(s) + 1 <= size:
            cur = f"{cur} {s}"
        else:
            chunks.append(cur)
            cur = s
        while len(cur) > size * 1.6:
            chunks.append(cur[:size].strip())
            cur = cur[size:].strip()
    if cur:
        chunks.append(cur)
    return [c for c in chunks if c] or [text]


def _resample_i16(wav_bytes: bytes, ratio: float) -> bytes:
    """Reamostra (interpolação linear). ratio > 1 = mais amostras = mais grave e mais longo."""
    if abs(ratio - 1.0) < 0.005:
        return wav_bytes
    try:
        import numpy as np
    except Exception:  # noqa: BLE001
        return wav_bytes
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        nch, sw, sr, n = w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()
        raw = w.readframes(n)
    if sw != 2 or n < 2:
        return wav_bytes
    audio = np.frombuffer(raw, dtype="<i2").reshape(-1, nch).astype(np.float32)
    n_out = max(1, int(round(audio.shape[0] * ratio)))
    src = np.linspace(0.0, audio.shape[0] - 1.0, n_out)
    i0 = np.floor(src).astype(np.int64)
    i1 = np.minimum(i0 + 1, audio.shape[0] - 1)
    frac = (src - i0).astype(np.float32).reshape(-1, 1)
    out = (audio[i0] * (1.0 - frac) + audio[i1] * frac).clip(-32768, 32767).astype("<i2")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as o:
        o.setnchannels(nch)
        o.setsampwidth(2)
        o.setframerate(sr)
        o.writeframes(out.tobytes())
    return buf.getvalue()


def _synthesize(chunks: list[str], path: Path | None, rate: float, pitch: float) -> bytes | None:
    """Sintetiza cada pedaço e concatena. Tom (pitch) é aplicado por reamostragem,
    compensando no length_scale para a duração final continuar sendo a de `rate`."""
    k = 2 ** (pitch / 12.0) if pitch else 1.0
    len_scale = rate * k if k != 1.0 else rate
    params = None
    frames: list[bytes] = []
    for chunk in chunks:
        raw = _synth_via_api(chunk, path, len_scale) or _synth_via_cli(chunk, path, len_scale)
        if not raw:
            continue
        if k != 1.0:
            raw = _resample_i16(raw, 1.0 / k)
        with wave.open(io.BytesIO(raw), "rb") as w:
            if params is None:
                params = w.getparams()
            frames.append(w.readframes(w.getnframes()))
    if not frames or params is None:
        return None
    buf = io.BytesIO()
    with wave.open(buf, "wb") as out:
        out.setparams(params)
        for fr in frames:
            out.writeframes(fr)
    return buf.getvalue()


def _synth_via_api(text: str, path: Path | None, rate: float) -> bytes | None:
    voice = _load_voice(path)
    if voice is None:
        return None
    syn_config = None
    try:
        from piper import SynthesisConfig  # type: ignore

        syn_config = SynthesisConfig(
            length_scale=max(0.3, rate),  # > 1 = fala mais lenta (mais clara)
            noise_scale=0.667,
            noise_w_scale=1.0,  # mais expressiva (o 0.8 soava "embolado")

            normalize_audio=True,
            volume=1.0,
        )
    except Exception:  # noqa: BLE001
        syn_config = None
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        if hasattr(voice, "synthesize_wav"):
            try:
                voice.synthesize_wav(text, wf, syn_config=syn_config)
            except TypeError:
                voice.synthesize_wav(text, wf)
        elif hasattr(voice, "synthesize"):  # piper-tts 1.2.x
            for chunk in voice.synthesize(text):
                wf.writeframes(chunk.audio_int16_bytes)
        else:
            return None
    return buf.getvalue()


def _synth_via_cli(text: str, path: Path | None, rate: float) -> bytes | None:
    """Último recurso: usa o executável `piper` (ou `python -m piper`)."""
    if path is None:
        return None
    exe = shutil.which("piper")
    base = [exe] if exe else [sys.executable, "-m", "piper"]
    with tempfile.TemporaryDirectory() as tmp:
        wav_path = Path(tmp) / "out.wav"
        cmd = base + ["-m", str(path), "-f", str(wav_path), "--length-scale", str(rate)]
        cfg = path.with_suffix(".onnx.json")
        if cfg.is_file():
            cmd += ["-c", str(cfg)]
        try:
            subprocess.run(cmd, input=text, text=True, capture_output=True, timeout=180)
        except Exception:  # noqa: BLE001
            return None
        if wav_path.is_file() and wav_path.stat().st_size > 44:
            return wav_path.read_bytes()
    return None


# ── 4b. vozes neurais do Edge TTS (geradas na nuvem da Microsoft) ──────
# O JARVIS fala com o **Piper local por padrão** (voz cadu, offline, mais grave —
# combina mais com a personalidade dele); o Edge TTS é a alternativa neural, mais
# natural porém genérica. O /tts cai de um para o outro nos dois sentidos, então
# o JARVIS nunca fica mudo.
EDGE_DEFAULT_VOICE = "pt-BR-AntonioNeural"
EDGE_FALLBACK_VOICES: list[dict[str, Any]] = [
    {"name": "pt-BR-AntonioNeural", "gender": "Masculino", "locale": "pt-BR", "note": "masculina madura"},
    {"name": "pt-BR-NicolauNeural", "gender": "Masculino", "locale": "pt-BR", "note": "masculina séria"},
    {"name": "pt-BR-FranciscaNeural", "gender": "Feminino", "locale": "pt-BR", "note": "feminina"},
    {"name": "pt-BR-ThalitaNeural", "gender": "Feminino", "locale": "pt-BR", "note": "feminina jovem"},
]
_edge_voices_cache: list[dict[str, Any]] = []
_edge_errors: dict[str, str] = {}


def edge_available() -> bool:
    """True quando a biblioteca edge-tts está instalada (não testa a internet)."""
    try:
        import edge_tts  # noqa: F401

        return True
    except Exception as exc:  # noqa: BLE001
        _edge_errors["import"] = str(exc)
        return False


def _edge_rate(rate: float) -> str:
    """Mesma direção do Piper: rate>1 (mais lento) → taxa negativa no Edge."""
    pct = int(round((1.0 - float(rate or 1.0)) * 100))
    return f"{max(-50, min(50, pct)):+d}%"


def _edge_pitch(pitch: float) -> str:
    """Semitons do Piper → Hz do Edge (1 semitom ≈ 10 Hz)."""
    hz = int(round(float(pitch or 0.0) * 10))
    return f"{max(-50, min(50, hz)):+d}Hz"


def _edge_voice(name: str | None) -> str:
    """Só nomes de voz pt-BR passam; qualquer outra coisa usa a padrão.
    (Se o nome não existir no serviço, o /tts cai para o Piper.)"""
    n = re.sub(r"[^A-Za-z0-9\-]", "", str(name or ""))
    return n if n.startswith("pt-BR-") else EDGE_DEFAULT_VOICE


async def _edge_stream(text: str, voice: str, rate: str, pitch: str) -> bytes:
    """Baixa o MP3 do Edge TTS (streaming de áudio)."""
    import edge_tts  # type: ignore

    out = bytearray()
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    async for chunk in comm.stream():
        if chunk.get("type") == "audio":
            out += chunk.get("data") or b""
    return bytes(out)


def tts_edge(text: str, voice: str | None, rate: float, pitch: float) -> bytes | None:
    """Sintetiza com o Edge TTS; None quando não há internet/biblioteca."""
    if not edge_available():
        return None
    import asyncio

    v = _edge_voice(voice)
    try:
        audio = asyncio.run(_edge_stream(text, v, _edge_rate(rate), _edge_pitch(pitch)))
    except Exception as exc:  # noqa: BLE001
        _edge_errors[v] = str(exc)[:200]
        return None
    if not audio:
        return None
    _edge_errors.pop(v, None)
    return audio


def list_edge_voices() -> tuple[list[dict[str, Any]], str]:
    """Vozes pt-BR do Edge (em cache). Devolve (lista, origem)."""
    global _edge_voices_cache
    if _edge_voices_cache:
        return _edge_voices_cache, "edge"
    if edge_available():
        import asyncio

        try:
            raw = asyncio.run(__import__("edge_tts").list_voices())
            pts = [v for v in raw if str(v.get("Locale", "")).startswith("pt-BR")]
            if pts:
                live = [
                    {
                        "name": str(v.get("ShortName") or ""),
                        "gender": str(v.get("Gender") or ""),
                        "locale": str(v.get("Locale") or ""),
                        "note": str(v.get("FriendlyName") or "")
                        .replace("Microsoft ", "")
                        .replace(" Online (Natural)", "")
                        .strip(),
                    }
                    for v in pts
                ]
                # o serviço varia por região: as vozes conhecidas entram sempre na lista
                have = {v["name"] for v in live}
                _edge_voices_cache = live + [v for v in EDGE_FALLBACK_VOICES if v["name"] not in have]
                return _edge_voices_cache, "edge"
        except Exception as exc:  # noqa: BLE001
            _edge_errors["list"] = str(exc)[:200]
    return list(EDGE_FALLBACK_VOICES), "fallback"


@app.get("/voices-edge")
def voices_edge():
    """Vozes pt-BR disponíveis no Edge TTS (lista local em reserva)."""
    items, source = list_edge_voices()
    return {
        "engine": "edge",
        "default": EDGE_DEFAULT_VOICE,
        "source": source,
        "available": items,
        "ready": edge_available(),
    }


def _sanitize_tts(text: str) -> str:
    """Limpa o texto que vai ao sintetizador: sem caracteres de controle nem tags/SSML,
    e com tamanho máximo (evita texto gigante e injeção no sintetizador)."""
    t = str(text or "")
    t = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", t)
    t = re.sub(r"<[^>]*>", " ", t)
    return t[:TTS_MAX_CHARS]


def _tts_piper_response(text: str, path: Path | None, rate: float, pitch: float) -> tuple[Response | None, str]:
    """Sintetiza com o Piper local. Devolve (resposta WAV, motivo da falha).

    Em caso de sucesso o motivo vem vazio; em caso de falha a resposta é None.
    """
    key = f"{path}|{rate:.2f}|{pitch:.1f}|{text}"
    if key in _tts_cache:
        return Response(
            content=_tts_cache[key],
            media_type="audio/wav",
            headers={"X-Engine": "piper", "X-Voice": path.name if path else "none"},
        ), ""

    # textos longos são fatiados: o Piper "perde o fôlego" em blocos grandes
    chunks = _split_chunks(text, 200) if len(text) > 500 else [text]
    audio = _synthesize(chunks, path, rate, pitch)
    if not audio:
        detail = (
            (_voice_errors.get(str(path)) if path else None)
            or ("modelo Piper não encontrado" if not path else "síntese indisponível")
        )
        return None, str(detail)

    if len(_tts_cache) > 24:
        _tts_cache.clear()
    _tts_cache[key] = audio
    return Response(
        content=audio,
        media_type="audio/wav",
        headers={"X-Engine": "piper", "X-Voice": path.name if path else "none", "X-Chunks": str(len(chunks))},
    ), ""


def _tts_edge_response(text: str, voice: str | None, rate: float, pitch: float) -> tuple[Response | None, str]:
    """Sintetiza com o Edge TTS (MP3). Devolve (resposta, motivo da falha)."""
    ev = _edge_voice(voice)
    ekey = f"edge|{ev}|{rate:.2f}|{pitch:.1f}|{text}"
    if ekey in _tts_cache:
        return Response(
            content=_tts_cache[ekey], media_type="audio/mpeg", headers={"X-Engine": "edge", "X-Voice": ev}
        ), ""
    audio = tts_edge(text, ev, rate, pitch)
    if not audio:
        return None, str(_edge_errors.get(ev) or _edge_errors.get("import") or "sem internet")
    if len(_tts_cache) > 24:
        _tts_cache.clear()
    _tts_cache[ekey] = audio
    return Response(
        content=audio, media_type="audio/mpeg", headers={"X-Engine": "edge", "X-Voice": ev}
    ), ""


@app.post("/tts")
def tts(body: TTSIn):
    if len(str(body.text or "")) > TTS_MAX_CHARS:
        _security_log("tts", f"texto truncado para {TTS_MAX_CHARS} chars", blocked=True)
    text = _speech_text(_sanitize_tts(body.text))
    if not text:
        return JSONResponse({"error": "texto vazio"}, status_code=400)

    # rate = length_scale do Piper (1.0 padrão do modelo; 1.35 = mais lento/claro)
    rate = max(0.7, min(2.2, float(body.rate or 1.0)))
    pitch = max(-8.0, min(8.0, float(body.pitch or 0.0)))  # semitons (negativo = mais grave)
    path = resolve_voice(body.voice)
    engine = (str(body.engine or "piper")).strip().lower()
    if engine not in ("piper", "edge"):
        _security_log("tts", f"engine desconhecido '{engine}' — usando piper", blocked=True)
        engine = "piper"

    # 1) motor pedido: Piper (padrão, local/offline) tenta primeiro — a voz do JARVIS é a cadu
    piper_detail = ""
    tried_piper = False
    if engine == "piper":
        tried_piper = True
        resp, piper_detail = _tts_piper_response(text, path, rate, pitch)
        if resp is not None:
            return resp
        # voz ausente/corrompida: cai para o Edge TTS (nunca fica mudo)
        _security_log("tts", f"piper indisponível ({piper_detail}) — usando edge")

    # 2) Edge TTS (vozes neurais da Microsoft): MP3 direto — o navegador toca sem conversão.
    #    É a reserva do Piper e também a escolha explícita de quem preferir a voz neural.
    resp, edge_detail = _tts_edge_response(text, body.voice, rate, pitch)
    if resp is not None:
        return resp
    _security_log("tts", f"edge indisponível ({edge_detail}) — usando piper")

    # 3) último recurso: o Piper (só quando o pedido veio do Edge — evita sintetizar duas vezes)
    if not tried_piper:
        resp, piper_detail = _tts_piper_response(text, path, rate, pitch)
        if resp is not None:
            return resp
    return JSONResponse(
        {"error": f"edge indisponível ({edge_detail}); piper indisponível ({piper_detail})"},
        status_code=503,
    )


@app.get("/voices")
def voices_list():
    """Vozes disponíveis localmente + o que dá para baixar."""
    return {
        "default": MODEL_PATH.name if MODEL_PATH else None,
        "available": [
            {
                "name": v.name,
                "path": str(v),
                "size_mb": round(v.stat().st_size / 1024**2, 1),
            }
            for v in list_voices()
        ],
        "downloadable": [
            {"name": f"{name}.onnx", "downloaded": resolve_voice(f"{name}.onnx") is not None}
            for name in DOWNLOADABLE_VOICES
        ],
    }


@app.post("/voices/download")
def voices_download(body: VoiceIn):
    """Baixa uma voz pt-BR melhor (faber/cadu) para a pasta voices/."""
    raw = (body.name or "").strip()
    key = raw[:-5] if raw.endswith(".onnx") else raw
    if key not in DOWNLOADABLE_VOICES:
        return JSONResponse(
            {"error": f"voz desconhecida: {raw}. Disponíveis: {', '.join(DOWNLOADABLE_VOICES)}"},
            status_code=400,
        )

    dest_dir = _voices_download_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    url = DOWNLOADABLE_VOICES[key]
    dest = dest_dir / f"{key}.onnx"
    cfg_dest = dest_dir / f"{key}.onnx.json"

    try:
        if not cfg_dest.is_file():
            r = requests.get(url + ".json", headers=UA, timeout=60)
            r.raise_for_status()
            cfg_dest.write_bytes(r.content)
        if not dest.is_file() or dest.stat().st_size < 1_000_000:
            r = requests.get(url, headers=UA, timeout=600, stream=True)
            r.raise_for_status()
            with open(dest, "wb") as fh:
                for chunk in r.iter_content(1024 * 512):
                    fh.write(chunk)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"falha ao baixar: {exc}"}, status_code=502)

    return {
        "ok": True,
        "name": dest.name,
        "path": str(dest),
        "size_mb": round(dest.stat().st_size / 1024**2, 1),
        "message": "Baixada. Selecione a voz nas configurações do JARVIS.",
    }


# ── 5. /stocks ──────────────────────────────────────────────────────────
BR_TICKER = re.compile(r"^[A-Z]{4}\d{1,2}$")


def _is_br(symbol: str) -> bool:
    return bool(BR_TICKER.match(symbol.upper().replace(".SA", "")))


def _brapi(symbols: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    url = "https://brapi.dev/api/quote/" + ",".join(symbols)
    try:
        r = requests.get(url, headers=UA, timeout=15)
        r.raise_for_status()
        for it in r.json().get("results", []):
            price = it.get("regularMarketPrice")
            out.append(
                {
                    "symbol": it.get("symbol"),
                    "name": it.get("longName") or it.get("shortName") or it.get("symbol"),
                    "price": price,
                    "change_percent": round(it.get("regularMarketChangePercent") or 0, 2),
                    "currency": it.get("currency", "BRL"),
                    "source": "brapi.dev",
                }
            )
    except Exception as exc:  # noqa: BLE001
        out.append({"symbol": ",".join(symbols), "error": f"brapi: {exc}", "source": "brapi.dev"})
    return out


def _yahoo(symbol: str) -> dict[str, Any]:
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?range=1d&interval=1d"
    try:
        r = requests.get(url, headers=UA, timeout=15)
        r.raise_for_status()
        meta = (r.json().get("chart", {}).get("result") or [{}])[0].get("meta", {})
        price = meta.get("regularMarketPrice")
        prev = meta.get("chartPreviousClose") or meta.get("previousClose") or price
        change = ((price - prev) / prev * 100) if price and prev else 0.0
        return {
            "symbol": meta.get("symbol", symbol),
            "name": meta.get("shortName") or meta.get("symbol", symbol),
            "price": price,
            "change_percent": round(change, 2),
            "currency": meta.get("currency", "USD"),
            "source": "yahoo",
        }
    except Exception as exc:  # noqa: BLE001
        return {"symbol": symbol, "error": f"yahoo: {exc}", "source": "yahoo"}


@app.get("/stocks")
def stocks(symbols: str = Query(..., description="Ex.: PETR4,VALE3,AAPL")):
    raw = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not raw:
        return JSONResponse({"error": "informe ?symbols=PETR4,VALE3"}, status_code=400)

    br = [s.replace(".SA", "") for s in raw if _is_br(s)]
    us = [s for s in raw if not _is_br(s)]

    results: list[dict[str, Any]] = []
    if br:
        results += _brapi(br)
    for sym in us:
        # tenta com sufixo .SA primeiro? não: símbolos sem padrão BR vão direto ao Yahoo.
        results.append(_yahoo(sym))

    # se um BR falhou no brapi, tenta no Yahoo com .SA
    fixed: list[dict[str, Any]] = []
    for item in results:
        if item.get("error") and _is_br(item.get("symbol", "")):
            alt = _yahoo(item["symbol"] + ".SA")
            fixed.append(alt if not alt.get("error") else item)
        else:
            fixed.append(item)

    return {"results": fixed, "updated_at": __import__("time").time()}


# ── 6. /currencies ──────────────────────────────────────────────────────
@app.get("/currencies")
def currencies():
    url = "https://economia.awesomeapi.com.br/last/USD-BRL,EUR-BRL,USD-EUR"
    try:
        r = requests.get(url, headers=UA, timeout=15)
        r.raise_for_status()
        data = r.json()
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"awesomeapi: {exc}"}, status_code=502)

    wanted = [("USDBRL", "USD/BRL"), ("EURBRL", "EUR/BRL"), ("USDEUR", "USD/EUR")]
    out = []
    for key, label in wanted:
        if key not in data:
            continue
        d = data[key]
        out.append(
            {
                "pair": label,
                "bid": float(d.get("bid") or 0),
                "ask": float(d.get("ask") or 0),
                "change_percent": round(float(d.get("pctChange") or 0), 3),
                "updated": d.get("create_date"),
                "source": "awesomeapi",
            }
        )
    return {"rates": out}


# ── 7. energia (/power) ─────────────────────────────────────────────────
class PowerIn(BaseModel):
    action: str = "shutdown"  # shutdown | restart | hibernate | sleep
    delay: int = 30           # segundos de carência (padrão 30)
    dry_run: bool = False     # só devolve o comando, sem executar (teste/segurança)


@app.post("/power")
def power(body: PowerIn, _exec_token: str = Depends(require_exec_token)):
    action = (body.action or "shutdown").strip().lower()
    delay = max(5, min(int(body.delay if body.delay is not None else 30), 3600))

    if action in ("shutdown", "desligar", "desligamento", "poweroff"):
        cmd, wait = f"shutdown /s /t {delay}", delay
    elif action in ("restart", "reiniciar", "reboot"):
        cmd, wait = f"shutdown /r /t {delay}", delay
    elif action in ("hibernate", "hibernar"):
        cmd, wait = "shutdown /h", 0
    elif action in ("sleep", "suspender", "dormir"):
        cmd, wait = "rundll32.exe powrprof.dll,SetSuspendState 0,1,0", 0
    else:
        return JSONResponse(
            {"error": f"a\u00e7\u00e3o desconhecida: {body.action} (use shutdown, restart, hibernate ou sleep)"},
            status_code=400,
        )

    if body.dry_run:
        _security_log("power", f"dry-run: {action} (delay {wait}s) — nada foi executado")
        return {"ok": True, "dry_run": True, "action": action, "delay": wait, "cmd": cmd, "executed": False}

    _security_log("power", f"EXECUTANDO {action} (delay {wait}s) — confirmado pelo Comandante")
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, timeout=30)
    except Exception as exc:  # noqa: BLE001
        _security_log("power", f"falha ao executar {action}: {exc}")
        return JSONResponse({"error": str(exc)}, status_code=500)

    err = _decode_output(proc.stderr)
    return {
        "ok": proc.returncode == 0 and not err,
        "action": action,
        "delay": wait,
        "cmd": cmd,
        "output": _decode_output(proc.stdout),
        "error": err or None,
    }


@app.post("/power/cancel")
def power_cancel():
    _security_log("power", "cancelamento de desligamento pedido (shutdown /a)")
    try:
        proc = subprocess.run("shutdown /a", shell=True, capture_output=True, timeout=20)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)
    out = _decode_output(proc.stdout)
    err = _decode_output(proc.stderr)
    ok = proc.returncode == 0
    return {"ok": ok, "output": out or err, "error": None if ok else (err or out)}


# ── 8. processos (/kill, /processes) ────────────────────────────────────
class KillIn(BaseModel):
    name: str
    force: bool = False


@app.post("/kill")
def kill_process(body: KillIn):
    raw = (body.name or "").strip()
    if not raw:
        return JSONResponse({"error": "informe o nome do programa"}, status_code=400)
    exe = raw if raw.lower().endswith(".exe") else f"{raw}.exe"
    if not re.fullmatch(r"[A-Za-z0-9_.\- ]{1,60}\.exe", exe):
        return JSONResponse({"error": f"nome inv\u00e1lido: {raw}"}, status_code=400)
    cmd = f'taskkill /IM "{exe}"' + (" /F" if body.force else "")
    try:
        proc = subprocess.run(cmd, shell=True, capture_output=True, timeout=40)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": str(exc)}, status_code=500)
    out = (_decode_output(proc.stdout) + " " + _decode_output(proc.stderr)).strip()
    return {
        "ok": proc.returncode == 0,
        "name": exe,
        "force": bool(body.force),
        "cmd": cmd,
        "output": out[:400],
    }


@app.get("/processes")
def list_processes(limit: int = Query(10, ge=1, le=50)):
    rows: list[dict[str, Any]] = []
    for p in psutil.process_iter(["pid", "name", "memory_info"]):
        try:
            mi = p.info.get("memory_info")
            rss = getattr(mi, "rss", 0) if mi is not None else 0
            rows.append(
                {"pid": p.info.get("pid"), "name": p.info.get("name") or "?", "ram_mb": round(rss / 1024**2, 1)}
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    rows.sort(key=lambda x: x["ram_mb"], reverse=True)
    return {"processes": rows[:limit], "count": len(rows)}


# ── 9. notícias (/news) ─────────────────────────────────────────────────
NEWS_FEEDS = {
    "geral": "https://g1.globo.com/rss/g1/",
    "brasil": "https://g1.globo.com/rss/g1/brasil/",
    "tecnologia": "https://g1.globo.com/rss/g1/tecnologia/",
    "esporte": "https://g1.globo.com/rss/g1/esporte/",
    "esportes": "https://g1.globo.com/rss/g1/esporte/",
    "economia": "https://g1.globo.com/rss/g1/economia/",
    "mundo": "https://g1.globo.com/rss/g1/mundo/",
    "politica": "https://g1.globo.com/rss/g1/politica/",
    "ciencia": "https://g1.globo.com/rss/g1/ciencia-e-saude/",
}
NEWS_TOPICS = ["geral", "tecnologia", "esportes", "economia", "mundo", "brasil", "politica", "ciencia"]


NEWS_SOURCE_SUFFIX = re.compile(
    r"\s*[-–—|]\s*(?:g1|ge|uol|folha|estad[aã]o|reuters|cnn(?:\s+brasil)?|bbc|exame|valor|infomoney|oglobo|o\s+globo)\s*$",
    re.IGNORECASE,
)


def _clean_news_text(text: str, limit: int = 100) -> str:
    """Limpa um texto de notícia para ser FALADO: sem HTML, URLs, emojis, hashtags e
    sem o sufixo de fonte (" - G1", " | UOL"). Corta em `limit` caracteres na
    fronteira de palavra (título muito longo é ruim para o TTS)."""
    t = str(text or "")
    t = re.sub(r"<[^>]+>", " ", t)              # tags HTML
    t = html.unescape(t)                          # &amp; &#8220; …
    t = re.sub(r"https?://\S+|www\.\S+", " ", t)
    t = re.sub(r"#\w+", " ", t)                  # hashtags
    t = re.sub(r"[\U0001F300-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F]", " ", t)  # emojis
    t = t.replace("\u2026", ". ")
    t = NEWS_SOURCE_SUFFIX.sub("", t)
    t = re.sub(r"\.{2,}", ".", t)
    t = re.sub(r"\s+", " ", t).strip(" -–—|·•\t")
    if limit and len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0].rstrip(" -–—|·•,;:")
    return t.strip()


def _parse_rss(xml: str, limit: int) -> list[dict[str, Any]]:
    """Extrai notícias prontas para TTS: só título, fonte e um resumo curto (sem link)."""
    out: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml)
    except Exception:  # noqa: BLE001
        return out
    for item in root.iter("item"):
        title = _clean_news_text(item.findtext("title") or "", limit=100)
        if not title:
            continue
        link = (item.findtext("link") or "").strip()
        source = ""
        src = item.find("source")
        if src is not None and (src.text or "").strip():
            source = (src.text or "").strip()
        if not source and link:
            try:
                source = urlparse(link).netloc.replace("www.", "")
            except Exception:  # noqa: BLE001
                source = ""
        source = _clean_news_text(source, limit=40)
        resumo = _clean_news_text(item.findtext("description") or "", limit=220)
        out.append({"titulo": title, "fonte": source, "resumo": resumo})
        if len(out) >= limit:
            break
    return out


@app.get("/news")
def news(topic: str = Query("geral"), limit: int = Query(5, ge=1, le=20)):
    key = (topic or "geral").strip().lower()
    url = NEWS_FEEDS.get(key)
    if not url:
        # tópico livre → busca no Google News
        url = f"https://news.google.com/rss/search?q={quote(key)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    try:
        r = requests.get(url, headers=UA, timeout=20)
        r.raise_for_status()
        xml = r.text
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"error": f"falha ao buscar not\u00edcias: {exc}"}, status_code=502)
    items = _parse_rss(xml, limit)
    return {"topic": key, "source": url, "items": items, "count": len(items)}


# ── 9a-notícias BR (/news/brasil) — G1 + The News (RSS) ─────────────────
# Fontes e tópicos em WHITELIST: nada de URL vinda do cliente.
BR_NEWS_FEEDS: dict[str, dict[str, str]] = {
    "g1": {
        "geral": "https://g1.globo.com/rss/g1/",
        "tecnologia": "https://g1.globo.com/rss/g1/tecnologia/",
        "economia": "https://g1.globo.com/rss/g1/economia/",
        "esportes": "https://g1.globo.com/rss/g1/esporte/",
        "mundo": "https://g1.globo.com/rss/g1/mundo/",
        "politica": "https://g1.globo.com/rss/g1/politica/",
        "ciencia": "https://g1.globo.com/rss/g1/ciencia-e-saude/",
    },
    # O The News publica tudo num feed único (Beehiiv): o tópico vira filtro por palavra.
    # O RSS de verdade está em rss.beehiiv.com/feeds/<id>.xml — o /feed devolve HTML.
    "thenews": {
        "geral": "https://rss.beehiiv.com/feeds/j9teVW9Qmi.xml",
        "mercado": "https://rss.beehiiv.com/feeds/j9teVW9Qmi.xml",
        "tecnologia": "https://rss.beehiiv.com/feeds/j9teVW9Qmi.xml",
        "mundo": "https://rss.beehiiv.com/feeds/j9teVW9Qmi.xml",
    },
}
# reservas: se o id do feed mudar, tentamos estes endereços e, por fim, procuramos
# o link rss.beehiiv.com/feeds/*.xml dentro da página do Beehiiv.
THENEWS_FALLBACK_FEEDS = (
    "https://thenewscc.beehiiv.com/feed",
    "https://thenews.com.br/feed",
)
THENEWS_DISCOVER_PAGES = ("https://thenewscc.beehiiv.com/", "https://thenewscc.com.br/")
THENEWS_RSS_IN_HTML = re.compile(r"https://rss\.beehiiv\.com/feeds/[A-Za-z0-9]+\.xml")
BR_NEWS_TOPIC_HINTS: dict[str, tuple[str, ...]] = {
    "mercado": (
        "mercado", "ibovespa", "d[óo]lar", "juros", "infla[çc][ãa]o", "a[çc][õo]es", "b3", "economia",
        "empresa", "banco", "bitcoin", "petr", "vale",
    ),
    "tecnologia": (
        "tecnolog", "intelig[êe]ncia artificial", "chip", "software", "startup", "apple", "google",
        "microsoft", "nvidia", "openai", "internet", "semi", "rob[óo]",
    ),
    "mundo": (
        "mundo", "eua", "estados unidos", "china", "europa", "guerra", "ucr[âa]nia", "israel",
        "oriente m[ée]dio", "trump", "onu", "rus",
    ),
}
BR_NEWS_RATE_WINDOW = 60
BR_NEWS_RATE_MAX = 30          # chamadas por minuto (janela deslizante)
_br_news_hits: list[float] = []


def _br_news_rate_limited() -> bool:
    """True quando passou de 30 chamadas em 60 s."""
    now = time.time()
    _br_news_hits[:] = [t for t in _br_news_hits if now - t <= BR_NEWS_RATE_WINDOW]
    if len(_br_news_hits) >= BR_NEWS_RATE_MAX:
        return True
    _br_news_hits.append(now)
    return False


def _news_link(raw: str) -> str:
    """Só link http(s) — descarta javascript:/file:/data: vindos do feed."""
    link = str(raw or "").strip()[:400]
    try:
        parts = urlparse(link)
    except Exception:  # noqa: BLE001
        return ""
    return link if parts.scheme in ("http", "https") and parts.netloc else ""


def _parse_rss_full(xml: str, limit: int) -> list[dict[str, Any]]:
    """Itens completos (título, link, data, resumo, fonte) já limpos pelo _clean_news_text."""
    out: list[dict[str, Any]] = []
    try:
        root = ET.fromstring(xml)
    except Exception:  # noqa: BLE001
        return out
    for entry in list(root.iter("item")) + list(root.iter("entry")):   # RSS e Atom
        title = _clean_news_text(entry.findtext("title") or "", limit=140)
        if not title:
            continue
        link = _news_link(entry.findtext("link") or "")
        if not link:
            for el in entry.findall("link"):
                link = _news_link(el.get("href") or "")
                if link:
                    break
        data = _clean_news_text(entry.findtext("pubDate") or entry.findtext("updated") or "", limit=40)
        resumo = _clean_news_text(entry.findtext("description") or entry.findtext("summary") or "", limit=200)
        fonte = ""
        src = entry.find("source")
        if src is not None and (src.text or "").strip():
            fonte = _clean_news_text(src.text or "", limit=40)
        out.append({"titulo": title, "link": link, "data": data, "resumo": resumo, "fonte": fonte})
        if len(out) >= max(1, min(int(limit), 40)):
            break
    return out


def _fetch_rss(url: str) -> str | None:
    """Baixa o XML do feed (15 s) — descarta resposta que não for XML de verdade."""
    try:
        r = requests.get(url, headers=UA, timeout=15)
        r.raise_for_status()
        body = r.text
        if re.search(r"<(rss|feed)[\s>]", body[:2000], re.IGNORECASE):
            return body
        raise ValueError("resposta não é RSS/Atom (HTML?)")
    except Exception as exc:  # noqa: BLE001
        _security_log("news-brasil", f"feed falhou: {url} ({exc})")
        return None


def _thenews_discover_feed() -> str | None:
    """Último recurso: acha o link rss.beehiiv.com/feeds/*.xml dentro do portal."""
    for page in THENEWS_DISCOVER_PAGES:
        try:
            r = requests.get(page, headers=UA, timeout=15)
            m = THENEWS_RSS_IN_HTML.search(r.text or "")
            if m:
                _security_log("news-brasil", f"feed do The News descoberto na página: {page}")
                return m.group(0)
        except Exception:  # noqa: BLE001
            continue
    return None


@app.get("/news/brasil")
def news_brasil(
    source: str = Query("g1"),
    topic: str = Query("geral"),
    limit: int = Query(5, ge=1, le=20),
):
    """Notícias reais do G1 e do The News (RSS) — fonte e tópico com whitelist."""
    if _br_news_rate_limited():
        _security_log("news-brasil", "rate limit (30/min) atingido", blocked=True)
        return JSONResponse(
            {"ok": False, "error": "muitas requisições — tente novamente em um minuto"}, status_code=429
        )

    src = (source or "g1").strip().lower()
    if src not in BR_NEWS_FEEDS:
        _security_log("news-brasil", f"fonte não permitida: {source}", blocked=True)
        return JSONResponse(
            {"ok": False, "error": f"fonte desconhecida: {source} (use g1 ou thenews)"}, status_code=400
        )

    tpc = (topic or "geral").strip().lower()
    feeds = BR_NEWS_FEEDS[src]
    if tpc not in feeds:
        _security_log("news-brasil", f"tópico '{tpc}' não existe em {src} — usando geral")
        tpc = "geral"
    url = feeds[tpc]

    xml = _fetch_rss(url)
    if not xml and src == "thenews":
        for alt in THENEWS_FALLBACK_FEEDS:      # o endereço do Beehiiv muda de tempo em tempo
            if alt == url:
                continue
            xml = _fetch_rss(alt)
            if xml:
                url = alt
                break
        if not xml:
            discovered = _thenews_discover_feed()
            if discovered and discovered != url:
                xml = _fetch_rss(discovered)
                if xml:
                    url = discovered
    if not xml:
        _security_log("news-brasil", f"nenhum feed respondeu ({src}/{tpc})", blocked=True)
        return JSONResponse(
            {
                "ok": False,
                "source": src,
                "topic": tpc,
                "error": f"não consegui baixar o feed do {src} agora",
            },
            status_code=502,
        )

    wide = max(limit, min(40, limit * 4)) if (src == "thenews" and tpc != "geral") else limit
    items = _parse_rss_full(xml, wide)
    if src == "thenews" and tpc != "geral":
        hints = BR_NEWS_TOPIC_HINTS.get(tpc, ())
        picked = [
            it for it in items if any(re.search(h, f"{it['titulo']} {it['resumo']}", re.IGNORECASE) for h in hints)
        ]
        rest = [it for it in items if it not in picked]
        items = (picked + rest)[:limit]
    items = items[:limit]

    _security_log("news-brasil", f"{src}/{tpc}: {len(items)} item(ns) de {url}")
    return {"ok": True, "source": src, "topic": tpc, "count": len(items), "feed": url, "items": items}


# ── 9a. clima (/weather) — São João do Paraíso - MG ─────────────────────
WEATHER_CITY = "São João do Paraíso"
WEATHER_LAT = -15.377
WEATHER_LON = -42.006
WEATHER_WTTR_URL = "https://wttr.in/Sao+Joao+do+Paraiso?format=j1&lang=pt"
WEATHER_OPEN_METEO_URL = (
    "https://api.open-meteo.com/v1/forecast"
    f"?latitude={WEATHER_LAT}&longitude={WEATHER_LON}"
    "&current=temperature_2m,relative_humidity_2m,weather_code,apparent_temperature,wind_speed_10m,wind_direction_10m"
    "&daily=temperature_2m_max,temperature_2m_min&timezone=America/Sao_Paulo"
)
# códigos WMO (open-meteo) → descrição em português
WEATHER_WMO = {
    0: "Céu limpo", 1: "Principalmente limpo", 2: "Parcialmente nublado", 3: "Nublado",
    45: "Neblina", 48: "Neblina com geada",
    51: "Garoa leve", 53: "Garoa", 55: "Garoa forte",
    56: "Garoa congelante", 57: "Garoa congelante forte",
    61: "Chuva fraca", 63: "Chuva", 65: "Chuva forte",
    66: "Chuva congelante", 67: "Chuva congelante forte",
    71: "Neve fraca", 73: "Neve", 75: "Neve forte", 77: "Grãos de neve",
    80: "Pancadas de chuva", 81: "Pancadas de chuva moderadas", 82: "Pancadas de chuva violentas",
    85: "Pancadas de neve", 86: "Pancadas de neve fortes",
    95: "Tempestade", 96: "Tempestade com granizo", 99: "Tempestade com granizo forte",
}
_CARDINAL_PT = ["N", "NNE", "NE", "ENE", "L", "ESE", "SE", "SSE", "S", "SSO", "SO", "OSO", "O", "ONO", "NO", "NNO"]


def _weather_int(value: Any) -> int | None:
    """Converte '22', 22.4 ou None em int (None quando não dá)."""
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _wind_dir_pt(degrees: Any) -> str:
    """Graus → ponto cardeal em português (16 pontas)."""
    try:
        deg = float(degrees)
    except (TypeError, ValueError):
        return ""
    return _CARDINAL_PT[int((deg % 360) / 22.5 + 0.5) % 16]


def _weather_from_wttr() -> dict[str, Any] | None:
    """Reserva: wttr.in (grátis, sem chave). Atrasa 1-3 h (World Weather Online),
    por isso só entra quando o open-meteo falha."""
    try:
        r = requests.get(WEATHER_WTTR_URL, headers={**UA, "Accept-Language": "pt-BR,pt"}, timeout=15)
        r.raise_for_status()
        data = r.json()
        cur = (data.get("current_condition") or [{}])[0]
        today = (data.get("weather") or [{}])[0]
        desc = ""
        # com &lang=pt o wttr devolve lang_pt ("Limpo", "Parcialmente nublado"...)
        descs = cur.get("lang_pt") or cur.get("weatherDesc") or []
        if descs:
            desc = str(descs[0].get("value") or "").strip()
        return {
            "ok": True,
            "cidade": WEATHER_CITY,
            "temp": _weather_int(cur.get("temp_C")),
            "sensacao": _weather_int(cur.get("FeelsLikeC")),
            "descricao": desc,
            "umidade": _weather_int(cur.get("humidity")),
            "vento": f"{cur.get('winddir16Point') or ''} {_weather_int(cur.get('windspeedKmph')) or 0}km/h".strip(),
            "max": _weather_int(today.get("maxtempC")),
            "min": _weather_int(today.get("mintempC")),
            "medido_em": str(cur.get("observation_time") or "").strip(),   # ex.: "12:32 PM"
            "fonte": "wttr.in",
        }
    except Exception:  # noqa: BLE001
        return None


def _weather_from_open_meteo() -> dict[str, Any] | None:
    """Clima real do open-meteo (grátis, sem chave). É a fonte PRIMÁRIA: atualiza
    a cada ~10-15 min, contra 1-3 h do wttr.in."""
    try:
        r = requests.get(WEATHER_OPEN_METEO_URL, headers=UA, timeout=15)
        r.raise_for_status()
        data = r.json()
        cur = data.get("current") or {}
        daily = data.get("daily") or {}
        code = int(cur.get("weather_code") or 0)
        daily_max = (daily.get("temperature_2m_max") or [None])[0]
        daily_min = (daily.get("temperature_2m_min") or [None])[0]
        speed = cur.get("wind_speed_10m")
        try:
            speed = int(round(float(speed)))
        except (TypeError, ValueError):
            speed = 0
        return {
            "ok": True,
            "cidade": WEATHER_CITY,
            "temp": _weather_int(cur.get("temperature_2m")),
            "sensacao": _weather_int(cur.get("apparent_temperature")),
            "descricao": WEATHER_WMO.get(code, f"Código {code}"),
            "umidade": _weather_int(cur.get("relative_humidity_2m")),
            "vento": f"{_wind_dir_pt(cur.get('wind_direction_10m'))} {speed}km/h".strip(),
            "max": _weather_int(daily_max),
            "min": _weather_int(daily_min),
            "medido_em": str(cur.get("time") or "").strip(),   # ex.: "2026-10-11T09:30"
            "fonte": "open-meteo",
        }
    except Exception:  # noqa: BLE001
        return None


@app.get("/weather")
def weather():
    # PRIMÁRIO: open-meteo (medição de ~15 min). RESERVA: wttr.in (mede de 1 a 3 h atrás).
    out = _weather_from_open_meteo() or _weather_from_wttr()
    if not out:
        return JSONResponse({"ok": False, "error": "não consegui obter os dados do clima"}, status_code=502)
    return out


# ── 9b. visualizador 3D on-demand (/visualize-3d) ───────────────────────
VIS3D_MAX_PROMPT = 200          # caracteres do pedido
VIS3D_MAX_HTML = 500 * 1024     # 500 KB de HTML gerado
VIS3D_TTL_SECONDS = 600         # limpeza automática após 10 minutos
VIS3D_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
VIS3D_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
VIS3D_CSP = (
    "default-src 'self' data: blob:; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "connect-src 'self' http://127.0.0.1:8000 http://localhost:8000; "
    "font-src 'self' data:; worker-src blob:"
)
VIS3D_PROMPT = (
    "Gere um arquivo HTML COMPLETO e AUTOCONTIDO com Three.js (via CDN) que "
    "renderiza um modelo 3D de: {prompt}\n\n"
    "REQUISITOS OBRIGATÓRIOS:\n"
    "- Carregue o Three.js de https://unpkg.com/three@0.128.0/build/three.min.js (NUNCA falhe em carregar).\n"
    "- Use OrbitControls de https://unpkg.com/three@0.128.0/examples/js/controls/OrbitControls.js\n"
    "- Se por algum motivo o Three.js não carregar em 5 segundos, MOSTRE uma mensagem visível na tela (não deixe tela preta) dizendo: 'Erro ao carregar Three.js. Verifique sua conexão.'\n"
    "- O objeto deve ser feito de PARTÍCULAS usando THREE.Points + BufferGeometry.\n"
    "- Mínimo 300.000 (trezentos mil) partículas — há de haver muitas partículas (300.000)\n"
    "- Use PointsMaterial com vertexColors true, sizeAttenuation true, blending AdditiveBlending.\n"
    "- Cada partícula é uma pequena esfera brilhante (use THREE.Points com textura circular e PointsMaterial com size>0.08, sizeAttenuation true, emissive/brilho forte)\n"
    "- Cor padrão: ciano (#3fd0ff) com brilho intenso\n"
    "- Fundo preto ou muito escuro\n"
    "- Rotação automática lenta (o objeto gira sozinho)\n"
    "- Interação: mouse gira o objeto, scroll dá zoom\n"
    "- Texto discreto no canto: \"JARVIS · Visualização 3D\"\n"
    "- Botão de fechar que envia beacon pra http://127.0.0.1:8000/visualize-3d/close/{id}\n"
    "- No beforeunload, envie navigator.sendBeacon pra mesma URL\n"
    "- Use geometrias primitivas do Three.js combinadas (caixas, cilindros, "
    "esferas, cones) e DISTRIBUA partículas na superfície delas\n"
    "- ESCALA: o objeto deve ocupar boa parte da tela (não pequeno no canto). Centralize e ajuste camera.position para vê-lo grande\n"
    "- Iluminação mínima: adicione uma luz direcional/fraca OU apenas use o material emissivo das partículas (garanta visibilidade total)\n"
    "- Adicione console.log('JARVIS 3D: cena iniciando') logo no início do script inline e console.log('JARVIS 3D: primeira renderização OK') logo após a primeira chamada a renderer.render (ou no frame inicial).\n"
    "- Tenha tratamento de erros com try/catch e não deixe lançar exceção não tratada.\n"
    "\n"
    "INSTRUÇÕES DO SCRIPT (leia com atenção):\n"
    "1. Use a versão 0.128.0 do Three.js (a última que tem THREE.OrbitControls como script global):\n"
    "\n"
    "   <script src=\"https://unpkg.com/three@0.128.0/build/three.min.js\"></script>\n"
    "   <script src=\"https://unpkg.com/three@0.128.0/examples/js/controls/OrbitControls.js\"></script>\n"
    "\n"
    "2. NÃO use onload=\"...\" no <script src>. Em vez disso, use POLLING com setInterval pra esperar tanto o THREE quanto a função init() estarem prontos. Use EXATAMENTE este bloco:\n"
    "\n"
    "   <script>\n"
    "   console.log('JARVIS 3D: cena iniciando');\n"
    "   let threeLoaded = false;\n"
    "   function showError(){ document.getElementById('errorMsg').style.display='flex'; }\n"
    "   let tries = 0;\n"
    "   const loadTimer = setTimeout(function(){ if(!threeLoaded) showError(); }, 5000);\n"
    "   const checkReady = setInterval(function(){ if (typeof THREE !== 'undefined' && typeof init === 'function') { clearInterval(checkReady); threeLoaded = true; clearTimeout(loadTimer); init(); } else if (++tries > 100) { clearInterval(checkReady); showError(); } }, 50);\n"
    "   </script>\n"
    "\n"
    "3. A função init() DEVE estar definida num <script> DEPOIS do polling acima. Ela cria a cena, a câmera, o renderer, as partículas (THREE.Points com BufferGeometry, 300000 partículas, PointsMaterial com sizeAttenuation, vertexColors, map de textura circular, AdditiveBlending, depthWrite false), os OrbitControls, o loop de animação com requestAnimationFrame.\n"
    "4. Adicione no início do init(): console.log('JARVIS 3D: cena inicializando');\n"
    "5. Dentro do animate(), depois do primeiro render: console.log('JARVIS 3D: primeira renderização OK');\n"
    "6. Use try/catch no corpo do init() e, no catch, chame console.error(e) e showError().\n"
    "\n"
    "INSTRUÇÕES PARA GERAÇÃO DE PARTÍCULAS:\n"
    "1. Escala do objeto: as partículas DEVEM ocupar uma esfera/cubo de raio 2.5 (não 1). Multiplique todas as coordenadas dos samplers por 5.\n"
    "   Ex: se sampleBox retorna [0.5, y, z], retorne [2.5, y*5, z*5].\n"
    "2. Câmera: coloque em z = 8 (não 5), com fov = 60.\n"
    "3. PARTICLE_COUNT: 150000 (não 300000). Menos partículas = menos saturação.\n"
    "4. PointsMaterial com:\n"
    "   - size: 0.02 (não 0.08 — partículas menores evitam saturação)\n"
    "   - sizeAttenuation: true\n"
    "   - vertexColors: true\n"
    "   - map: textura circular (radial gradient branco)\n"
    "   - transparent: true\n"
    "   - blending: THREE.NormalBlending  ← NÃO use AdditiveBlending (satura pra branco)\n"
    "   - depthWrite: false\n"
    "5. Cores: cada partícula recebe uma cor variando entre ciano (#3fd0ff) e azul mais escuro (#1a6bb5). Use THREE.Color().lerpColors() ou similar. NÃO use branco puro na cor de todas as partículas.\n"
    "6. Após criar as partículas, adicione um leve brilho com:\n"
    "   - Um segundo THREE.Points com 10% das partículas, size 0.05, AdditiveBlending, cor ciano pura (#3fd0ff) — isso dá o \"glow\".\n"
    "   - Mantenha o primeiro Points com NormalBlending.\n"
    "7. Rotação: rotacione o grupo lentamente (0.0005 por frame).\n"
    "\n"
    "Retorne APENAS o código HTML, sem explicação, sem markdown, sem ```html."
)


_VIS3D: dict[str, dict[str, Any]] = {}
_VIS3D_LOCK = threading.Lock()
_VIS3D_THREAD_STARTED = False


class Visualize3DIn(BaseModel):
    prompt: str


def _vis3d_key() -> str:
    """Chave da Groq: lida do config.json (mesmo arquivo que o app.py usa)."""
    try:
        data = json.loads((_data_dir() / "config.json").read_text(encoding="utf-8"))
        return str(data.get("groqKey") or "").strip()
    except Exception:  # noqa: BLE001
        return ""



def _vis3d_sanitize(text: str) -> str:
    """Prompt curto e limpo: sem tags, sem comandos, sem scripts e sem caracteres de controle."""
    t = str(text or "")
    t = re.sub(r"[\x00-\x1f\x7f]", " ", t)
    t = re.sub(r"<[^>]*>", " ", t)
    # tokens de script/JS e metacaracteres de shell/URL
    t = re.sub(
        r"(?i)\b(?:javascript|vbscript|script|onerror|onload|eval|document|window|fetch|import|require|"
        r"rm|del|format|shutdown|mkfs|diskpart|reg|curl|wget|powershell|cmd)\b",
        " ",
        t,
    )
    t = re.sub(r"[{}`$;\\|>&<]|https?://|file://", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:VIS3D_MAX_PROMPT]





def _vis3d_extract_html(text: str) -> str | None:
    """Tira cercas markdown e devolve só o HTML (a partir do doctype/html)."""
    t = str(text or "").strip()
    t = re.sub(r"^```(?:html)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t)
    m = re.search(r"<!DOCTYPE\s+html", t, re.IGNORECASE) or re.search(r"<html\b", t, re.IGNORECASE)
    if not m:
        return None

    start = m.start()
    t = t[start:].strip()

    # HTML incompleto (resposta cortada pela API) não serve: a página ficaria preta.
    # Exige o fechamento do documento e ao menos um frame de render.
    if not re.search(r"</html\s*>", t, re.IGNORECASE):
        return None
    if not ("renderer.render" in t or "requestAnimationFrame" in t):
        return None

    # Densidade mínima de partículas: exige que o HTML mencione ~300000 partículas ou
    # que tenha THREE.Points / BufferGeometry com estrutura de grande quantidade.
    lower = t.lower()

    # 1) mencao numerica explicita de 300.000 partículas (ambos formatos aceitos)
    has_300k_str = bool(
        re.search(
            r"\b300[,. ]?000\b|\b300\.000\b|\b300000\b|\b3[,. ]?0[,. ]?0[,. ]?000\b|\b3e5\b",
            t,
            re.IGNORECASE,
        )
    )

    # 2) estrutura de pontos em grande escala (usamos o codigo original tambem para
    #    compatibilidade; o regex original estava em lowercase, mantemos)
    has_buffer_points = bool(
        re.search(
            r"buffergeometry\b|position\.(length|\[)|new\s+float32array|points\b|pcount\b",
            lower,
        )
    )

    # 3) mencao de THREE.Points associada a uma quantidade grande (>= 100.000 é suficiente
    #    como indireto de que será 300.000 no código final)
    has_points_high_count = bool(
        re.search(
            r"THREE\.Points|new\s+THREE\.Points",
            t,
            re.IGNORECASE,
        )
    )

    ok = has_300k_str or has_buffer_points or has_points_high_count
    if not ok:
        return None

    return t




def _vis3d_inject_csp(html: str) -> str:
    """Insere o meta de CSP restritivo no começo do documento."""
    meta = f'<meta http-equiv="Content-Security-Policy" content="{VIS3D_CSP}">'
    if re.search(r"<head[^>]*>", html, re.IGNORECASE):
        return re.sub(
            r"(<head[^>]*>)",
            lambda m: m.group(1) + meta,
            html,
            count=1,
            flags=re.IGNORECASE,
        )
    if re.search(r"<html[^>]*>", html, re.IGNORECASE):
        return re.sub(
            r"(<html[^>]*>)",
            lambda m: m.group(1) + meta,
            html,
            count=1,
            flags=re.IGNORECASE,
        )
    return meta + html

    t = re.sub(r"[\x00-\x1f\x7f]", " ", t)
    t = re.sub(r"<[^>]*>", " ", t)
    # tokens de script/JS e metacaracteres de shell/URL
    t = re.sub(
        r"(?i)\b(?:javascript|vbscript|script|onerror|onload|eval|document|window|fetch|import|require|"
        r"rm|del|format|shutdown|mkfs|diskpart|reg|curl|wget|powershell|cmd)\b",
        " ",
        t,
    )
    t = re.sub(r"[{}`$;\\|>&<]|https?://|file://", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:VIS3D_MAX_PROMPT]




def _vis3d_extract_html(text: str) -> str | None:
    """Tira cercas markdown e devolve só o HTML (a partir do doctype/html)."""
    t = str(text or "").strip()
    t = re.sub(r"^```(?:html)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t)
    m = re.search(r"<!DOCTYPE\s+html", t, re.IGNORECASE) or re.search(r"<html\b", t, re.IGNORECASE)
    if not m:
        return None
    t = t[m.start():].strip()

    # HTML incompleto (resposta cortada pela API) não serve: a página ficaria preta.
    # Exige o fechamento do documento e ao menos um frame de render.
    if not re.search(r"</html\s*>", t, re.IGNORECASE):
        return None
    if not ("renderer.render" in t or "requestAnimationFrame" in t):
        return None
    # Densidade mínima de partículas: exige que o HTML mencione ~300000 partículas ou
    # que terce o THREE.Points / vertsCount indique uma alta quantidade.
    lower = t.lower()
    var_300k = re.search(r"\b300[,. ]?000\b|\b300k\b|\b3[,. ]?0[,. ]?0[,. ]?000\b", t, re.IGNORECASE)
    has_buf_points = bool(
        re.search(r"buffergeometry\b|position\.length|new\s+float32array|points\b|pcount\b", lower)
    )
    if not (var_300k or has_buf_points):
        return None
    return t


def _vis3d_inject_csp(html: str) -> str:
    """Insere o meta de CSP restritivo no começo do documento."""
    meta = f'<meta http-equiv="Content-Security-Policy" content="{VIS3D_CSP}">'
    if re.search(r"<head[^>]*>", html, re.IGNORECASE):
        return re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + meta, html, count=1, flags=re.IGNORECASE)
    if re.search(r"<html[^>]*>", html, re.IGNORECASE):
        return re.sub(r"(<html[^>]*>)", lambda m: m.group(1) + meta, html, count=1, flags=re.IGNORECASE)
    return meta + html


def _vis3d_generate(prompt: str) -> str | None:
    """Pede o HTML à Groq (tenta os modelos em ordem). Devolve None se nada válido veio."""
    key = _vis3d_key()
    if not key:
        return None
    body: dict[str, Any] = {
        "messages": [{"role": "user", "content": VIS3D_PROMPT.replace("{prompt}", prompt)}],
        "temperature": 0.4,
        # sem isto o gpt-oss corta a resposta no meio e devolve HTML pela metade
        "max_tokens": 16384,
    }
    for model in VIS3D_MODELS:
        body["model"] = model
        try:
            r = requests.post(
                VIS3D_GROQ_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=body,
                timeout=90,
            )
            if r.status_code != 200:
                continue
            content = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            html = _vis3d_extract_html(content)
            if html and len(html.encode("utf-8")) >= 200:
                return html
        except Exception:  # noqa: BLE001
            continue
    return None


def _vis3d_cleanup_loop() -> None:
    """Apaga (a cada 60 s) os arquivos 3D com mais de 10 minutos."""
    while True:
        time.sleep(60)
        now = time.time()
        with _VIS3D_LOCK:
            expired = [k for k, v in _VIS3D.items() if now - float(v.get("created_at") or 0) > VIS3D_TTL_SECONDS]
            for k in expired:
                item = _VIS3D.pop(k, None)
                if not item:
                    continue
                try:
                    Path(item["path"]).unlink(missing_ok=True)
                    _security_log("visualize-3d", f"limpeza automática: {k}")
                except Exception:  # noqa: BLE001
                    pass


def _vis3d_ensure_cleanup() -> None:
    global _VIS3D_THREAD_STARTED
    if _VIS3D_THREAD_STARTED:
        return
    _VIS3D_THREAD_STARTED = True
    threading.Thread(target=_vis3d_cleanup_loop, daemon=True, name="jarvis-3d-cleanup").start()


@app.post("/visualize-3d")
def visualize_3d(body: Visualize3DIn):
    """Gera (via Groq) um HTML de partículas 3D, salva em %TEMP% e abre no navegador."""
    _vis3d_ensure_cleanup()
    prompt = _vis3d_sanitize(body.prompt)
    if not prompt:
        _security_log("visualize-3d", "prompt vazio ou inválido", blocked=True)
        return JSONResponse({"error": "diga o que visualizar (ex.: 'um carro vermelho')"}, status_code=400)

    html = None
    for _attempt in range(2):          # máximo 2 tentativas de geração
        candidate = _vis3d_generate(prompt)
        if candidate:
            html = candidate
            break
    if not html:
        _security_log("visualize-3d", f"falha ao gerar HTML: {prompt}", blocked=True)
        return JSONResponse(
            {"error": "não consegui gerar a visualização 3D (confira a chave da Groq nas configurações)"},
            status_code=502,
        )

    html = _vis3d_inject_csp(html)
    if len(html.encode("utf-8")) > VIS3D_MAX_HTML:
        _security_log("visualize-3d", "HTML acima de 500 KB — truncado", blocked=True)
        html = html.encode("utf-8")[:VIS3D_MAX_HTML].decode("utf-8", errors="ignore")

    viz_id = uuid.uuid4().hex
    # o modelo não conhece o id real deste arquivo — ele escreve {id}/$\{id\}/crypto.randomUUID()
    # no beacon. Reescrevemos a URL inteira pro id verdadeiro, senão o close apagaria nada.
    html = re.sub(
        r"visualize-3d/close/[^\"'`\s<]*",
        f"visualize-3d/close/{viz_id}",
        html,
    )
    path = Path(tempfile.gettempdir()) / f"jarvis-3d-{viz_id}.html"
    try:
        path.write_text(html, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        _security_log("visualize-3d", f"não consegui gravar o arquivo: {exc}", blocked=True)
        return JSONResponse({"error": f"não consegui salvar o arquivo: {exc}"}, status_code=500)

    with _VIS3D_LOCK:
        _VIS3D[viz_id] = {"path": str(path), "created_at": time.time(), "prompt": prompt}
    _security_log("visualize-3d", f"{prompt} ({len(html)} bytes) -> {path.name}")
    try:
        webbrowser.open(path.as_uri())
    except Exception:  # noqa: BLE001
        pass
    # frase natural: evita "Abrindo o um carro"
    article = "" if re.match(r"^(o|a|os|as|um|uma|uns|umas|meu|minha)\b", prompt, re.IGNORECASE) else "o "
    return {
        "ok": True,
        "id": viz_id,
        "path": str(path),
        "size": len(html),
        "message": f"Abrindo {article}{prompt} no navegador, Comandante.",
    }


@app.post("/visualize-3d/close/{viz_id}")
def visualize_3d_close(viz_id: str):
    """Recebe o beacon da aba e apaga o HTML gerado."""
    vid = re.sub(r"[^0-9a-fA-F]", "", str(viz_id or ""))[:64]
    with _VIS3D_LOCK:
        item = _VIS3D.pop(vid, None)
    if not item:
        return {"ok": True, "removed": False}
    try:
        Path(item["path"]).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass
    _security_log("visualize-3d", f"fechado pelo usuário e removido: {vid}")
    return {"ok": True, "removed": True}


# ── 10. agenda (/agenda) ────────────────────────────────────────────────
def _data_dir() -> Path:
    """Onde gravar dados do usuário (agenda). Fora do pacote quando empacotado."""
    if getattr(sys, "frozen", False):
        base = Path(os.environ.get("APPDATA") or Path.home()) / "JARVIS"
        base.mkdir(parents=True, exist_ok=True)
        return base
    return APP_DIR.parent  # jarvis/ (junto do config.json de desenvolvimento)


AGENDA_PATH = Path(os.environ.get("JARVIS_AGENDA") or (_data_dir() / "agenda.json"))


class AgendaIn(BaseModel):
    title: str
    datetime: str
    description: str = ""


def _load_agenda() -> list[dict[str, Any]]:
    if not AGENDA_PATH.is_file():
        return []
    try:
        data = json.loads(AGENDA_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:  # noqa: BLE001
        return []


def _save_agenda(items: list[dict[str, Any]]) -> None:
    AGENDA_PATH.parent.mkdir(parents=True, exist_ok=True)
    AGENDA_PATH.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_dt(raw: str) -> datetime | None:
    s = (raw or "").strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except Exception:  # noqa: BLE001
        pass
    fmts = (
        "%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y",
        "%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
        "%d-%m-%Y %H:%M", "%d/%m %H:%M", "%d/%m/%Y %Hh%M",
    )
    for fmt in fmts:
        try:
            dt = datetime.strptime(s, fmt)
        except Exception:  # noqa: BLE001
            continue
        if dt.year == 1900:
            dt = dt.replace(year=datetime.now().year)
        return dt
    return None


@app.post("/agenda/add")
def agenda_add(body: AgendaIn):
    title = (body.title or "").strip()
    if not title:
        return JSONResponse({"error": "informe o t\u00edtulo do lembrete"}, status_code=400)
    dt = _parse_dt(body.datetime)
    if dt is None:
        return JSONResponse(
            {"error": f"data/hora inv\u00e1lida: {body.datetime!r} (use AAAA-MM-DD HH:MM ou DD/MM/AAAA HH:MM)"},
            status_code=400,
        )
    items = _load_agenda()
    event = {
        "id": uuid.uuid4().hex[:8],
        "title": title,
        "datetime": dt.isoformat(timespec="minutes"),
        "description": (body.description or "").strip(),
        "created": datetime.now().isoformat(timespec="seconds"),
    }
    items.append(event)
    items.sort(key=lambda x: str(x.get("datetime", "")))
    _save_agenda(items)
    return {"ok": True, "event": event, "total": len(items)}


@app.get("/agenda/list")
def agenda_list(include_past: int = Query(0, ge=0, le=1)):
    now = datetime.now()
    items = _load_agenda()
    if not include_past:
        items = [e for e in items if (_parse_dt(str(e.get("datetime", ""))) or now) >= now]
    items.sort(key=lambda x: str(x.get("datetime", "")))
    return {"events": items, "count": len(items)}


@app.delete("/agenda/{event_id}")
def agenda_delete(event_id: str):
    key = (event_id or "").strip()
    items = _load_agenda()
    kept = [e for e in items if e.get("id") != key and str(e.get("title", "")).lower() != key.lower()]
    if len(kept) == len(items):
        return JSONResponse({"error": f"evento n\u00e3o encontrado: {key}"}, status_code=404)
    removed = len(items) - len(kept)
    _save_agenda(kept)
    return {"ok": True, "removed": removed, "remaining": len(kept)}


@app.post("/agenda/check")
def agenda_check(window: int = Query(5, ge=1, le=1440)):
    now = datetime.now()
    soon: list[dict[str, Any]] = []
    for e in _load_agenda():
        dt = _parse_dt(str(e.get("datetime", "")))
        if dt is None:
            continue
        secs = (dt - now).total_seconds()
        if 0 <= secs <= window * 60:
            soon.append({**e, "in_minutes": round(secs / 60, 1)})
    soon.sort(key=lambda x: str(x.get("datetime", "")))
    return {"window_min": window, "events": soon, "count": len(soon)}


# ── 12. /health ─────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "ok": True,
        "piper_model": str(MODEL_PATH) if MODEL_PATH else None,
        "piper_ready": bool(_load_voice(MODEL_PATH)) if MODEL_PATH else False,
        "piper_error": _voice_errors.get(str(MODEL_PATH)) if MODEL_PATH else "modelo não encontrado",
        "voices": [v.name for v in list_voices()],
        "edge_ready": edge_available(),
        "tts_engines": ["piper", "edge"],
        "edge_voices": [v["name"] for v in (_edge_voices_cache or EDGE_FALLBACK_VOICES)],
        "agenda_events": len(_load_agenda()),
        "python": sys.version.split()[0],
        "hostname": socket.gethostname(),
        "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 1),
    }


# ── 13. memória persistente (/memory) ───────────────────────────────────
# backend/memory.py é carregado ao lado deste arquivo (mesmo padrão do launcher),
# então funciona tanto em dev quanto dentro do .exe empacotado.
_MEMORY_MODULE: Any = None
_MEMORY_ERROR = ""


def _memory_module() -> Any:
    """Carrega backend/memory.py ao lado deste arquivo (importlib, igual ao launcher)."""
    global _MEMORY_MODULE, _MEMORY_ERROR
    if _MEMORY_MODULE is not None:
        return _MEMORY_MODULE
    if _MEMORY_ERROR:
        return None
    try:
        import importlib.util

        path = Path(__file__).resolve().parent / "memory.py"
        if not path.is_file():
            raise FileNotFoundError(f"memory.py não encontrado em {path.parent}")
        spec = importlib.util.spec_from_file_location("jarvis_memory", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # type: ignore[union-attr]
        _MEMORY_MODULE = module
    except Exception as exc:  # noqa: BLE001
        _MEMORY_ERROR = str(exc)
    return _MEMORY_MODULE


def _memory_error_response() -> JSONResponse:
    return JSONResponse({"ok": False, "error": _MEMORY_ERROR or "memória indisponível"}, status_code=503)


class MemoryIn(BaseModel):
    text: str = ""
    source: str = "manual"


@app.post("/memory/add")
def memory_add(body: MemoryIn):
    m = _memory_module()
    if m is None:
        return _memory_error_response()
    try:
        out = m.add_memory(body.text, body.source or "manual")
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"falha ao salvar memória: {exc}"}, status_code=500)
    if out.get("skipped"):
        _security_log("memory", f"memória ignorada: {out.get('reason')}")
        return {"ok": True, "skipped": True, "reason": out.get("reason"), "memory": None}
    _security_log(
        "memory",
        f"memória salva (source={out.get('source')}, categoria={out.get('category')})",
    )
    return {"ok": True, "skipped": False, "memory": out}


@app.get("/memory/search")
def memory_search(q: str = Query(""), n: int = Query(5, ge=1, le=50)):
    m = _memory_module()
    if m is None:
        return _memory_error_response()
    try:
        results = m.search_memory(q, n)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"falha na busca: {exc}"}, status_code=500)
    return {"ok": True, "query": q, "n": n, "results": results}


@app.get("/memory/list")
def memory_list(limit: int = Query(100, ge=1, le=500)):
    m = _memory_module()
    if m is None:
        return _memory_error_response()
    try:
        items = m.list_memories(limit)
        total = m.stats().get("total", len(items))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"falha ao listar: {exc}"}, status_code=500)
    return {"ok": True, "memories": items, "total": total}


@app.get("/memory/stats")
def memory_stats():
    m = _memory_module()
    if m is None:
        return _memory_error_response()
    try:
        return {"ok": True, **m.stats()}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"falha nas estatísticas: {exc}"}, status_code=500)


@app.post("/memory/archive")
def memory_archive(days: int = Query(90, ge=1, le=3650)):
    """Arquiva (sem apagar) memórias antigas que nunca entraram numa resposta."""
    m = _memory_module()
    if m is None:
        return _memory_error_response()
    try:
        n = int(m.archive_stale(days))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"falha ao arquivar: {exc}"}, status_code=500)
    _security_log("memory", f"arquivadas {n} memória(s) sem uso (> {days} dias)")
    return {"ok": True, "archived": n, "days": days}


@app.delete("/memory/all")
def memory_delete_all():
    m = _memory_module()
    if m is None:
        return _memory_error_response()
    try:
        removed = m.delete_all_memories()
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"falha ao apagar: {exc}"}, status_code=500)
    _security_log("memory", f"reset: {removed} memórias apagadas")
    return {"ok": True, "removed": removed}


@app.delete("/memory/{memory_id}")
def memory_delete(memory_id: str):
    m = _memory_module()
    if m is None:
        return _memory_error_response()
    try:
        removed = m.delete_memory(memory_id)
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "error": f"falha ao apagar: {exc}"}, status_code=500)
    if removed:
        _security_log("memory", "memória removida")
    return {"ok": True, "removed": removed}


def _memory_warmup() -> None:
    """Pré-carrega banco + embedder em segundo plano (não trava a subida)."""
    module = _memory_module()
    if module is not None:
        try:
            module.warmup()
        except Exception:  # noqa: BLE001
            pass


threading.Thread(target=_memory_warmup, daemon=True, name="jarvis-memory-warmup").start()


# ── 14. modo programador (/generate-code) ───────────────────────────────
# "Jarvis, cria um site de portfólio" → a Groq gera o código, o arquivo vai para
# %TEMP% e abre no navegador (HTML) ou no editor padrão (o resto). O arquivo é
# apagado quando a aba fecha (beacon) ou sozinho depois de 10 minutos.
GENCODE_MAX_PROMPT = 500            # caracteres do pedido
GENCODE_MAX_CODE = 200 * 1024       # 200 KB de código gerado
GENCODE_TTL_SECONDS = 600           # limpeza automática após 10 minutos
GENCODE_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GENCODE_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]
GENCODE_TOOLS_PORT = int(os.environ.get("JARVIS_TOOLS_PORT", "8000"))
GENCODE_ORIGIN = f"http://127.0.0.1:{GENCODE_TOOLS_PORT}"
# Somente código-fonte/texto. Nunca .exe, .bat, .cmd ou .ps1.
GENCODE_EXTENSIONS: dict[str, str] = {
    "html": "html",
    "css": "css",
    "js": "js",
    "py": "py",
    "md": "md",
    "txt": "txt",
    "json": "json",
    "sql": "sql",
}
GENCODE_LANG_ALIASES = {
    "python": "py",
    "javascript": "js",
    "typescript": "js",
    "markdown": "md",
    "texto": "txt",
    "text": "txt",
    "site": "html",
    "página": "html",
    "pagina": "html",
    "web": "html",
}
# Pistas usadas quando o Comandante não diz a linguagem (a mais citada ganha).
GENCODE_LANG_HINTS: dict[str, tuple[str, ...]] = {
    "md": ("markdown", "readme", "documenta", "artigo", "texto", "explica"),
    "sql": ("sql", "consulta", "banco de dados"),
    "json": ("json",),
    "css": ("css", "estilo", "folha de estilo"),
    "js": ("javascript", "node", "react", "typescript"),
    "py": ("python", "automa", "script", "bot", "scrap", "planilha", "dados", "analis", "algoritmo"),
    "html": (
        "site", "página", "pagina", "web", "html", "landing", "portfólio", "portfolio", "blog",
        "currículo", "curriculo", "dashboard", "formulário", "formulario", "app", "aplicativo",
        "jogo", "game", "tela", "loja", "cardápio", "cardapio",
    ),
}
GENCODE_PROMPT = (
    "Gere o código completo para: {prompt}\n\n"
    "REQUISITOS:\n"
    "- Código COMPLETO e FUNCIONAL (não deixe partes em branco)\n"
    "- Se for HTML, inclua CSS e JS inline (arquivo autocontido)\n"
    "- Comente as partes importantes (em português)\n"
    "- NÃO use bibliotecas externas que precisem instalação\n"
    "- Se for um site, faça responsivo e bonito\n\n"
    "Retorne APENAS o código, sem explicação, sem markdown, sem ```html.\n"
    "O arquivo final será .{ext} — gere somente esse tipo de conteúdo."
)
_GCODE: dict[str, dict[str, Any]] = {}
_GCODE_LOCK = threading.Lock()
_GCODE_THREAD_STARTED = False


class GenerateCodeIn(BaseModel):
    prompt: str = ""
    language: str = ""


def _gcode_sanitize(text: str) -> str:
    """Pedido curto e limpo: sem tags HTML, sem scripts, sem URLs e sem controle."""
    t = str(text or "")
    t = re.sub(r"[\x00-\x1f\x7f]", " ", t)
    t = re.sub(r"(?is)<script\b.*?</script\s*>", " ", t)
    t = re.sub(r"<[^>]*>", " ", t)
    t = re.sub(r"https?://|file://", " ", t)
    t = re.sub(r"[`{}$]", " ", t)
    return re.sub(r"\s+", " ", t).strip()[:GENCODE_MAX_PROMPT]


def _gcode_detect_language(text: str, explicit: str = "") -> str:
    """Linguagem do arquivo: a pedida (quando permitida) ou a melhor pista no pedido."""
    want = str(explicit or "").strip().lower()
    want = GENCODE_LANG_ALIASES.get(want, want)
    if want in GENCODE_EXTENSIONS:
        return want
    low = f" {str(text or '').lower()} "
    scores = {lang: sum(1 for kw in keys if kw in low) for lang, keys in GENCODE_LANG_HINTS.items()}
    best = max(scores, key=lambda lang: (scores[lang], lang == "html"))
    return best if scores[best] else "html"


def _gcode_extract(text: str, lang: str) -> str | None:
    """Tira cercas markdown/explicações e devolve só o código (None se vier inútil)."""
    t = str(text or "").strip()
    blocks = re.findall(r"```[a-zA-Z0-9+#._-]*\s*\n?(.*?)```", t, flags=re.DOTALL)
    if blocks:
        t = max(blocks, key=len).strip()
    else:
        t = re.sub(r"^```[a-zA-Z0-9+#._-]*\s*", "", t)
        t = re.sub(r"\s*```$", "", t).strip()
    if lang == "html":
        start = re.search(r"<!DOCTYPE\s+html", t, re.IGNORECASE) or re.search(r"<html\b", t, re.IGNORECASE)
        if not start:
            return None
        t = t[start.start():]
        end = re.search(r"</html\s*>", t, re.IGNORECASE)
        if end:
            t = t[: end.end()]
    if len(t) < 100:                     # mínimo de 100 caracteres de código útil
        return None
    return t


def _gcode_key() -> str:
    """Chave da Groq: a mesma do config.json usada pelo visualizador 3D."""
    return _vis3d_key()


def _gcode_generate(prompt: str, lang: str) -> str | None:
    """Pede o código à Groq (tenta os modelos em ordem). None se nada válido veio."""
    key = _gcode_key()
    if not key:
        return None
    body: dict[str, Any] = {
        "messages": [{"role": "user", "content": GENCODE_PROMPT.format(prompt=prompt, ext=GENCODE_EXTENSIONS[lang])}],
        "temperature": 0.3,
        # sem isto o gpt-oss corta a resposta no meio e devolve código pela metade
        "max_tokens": 16384,
    }
    for model in GENCODE_MODELS:
        body["model"] = model
        try:
            r = requests.post(
                GENCODE_GROQ_URL,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=body,
                timeout=120,
            )
            if r.status_code != 200:
                continue
            content = ((r.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
            code = _gcode_extract(content, lang)
            if code:
                return code
        except Exception:  # noqa: BLE001
            continue
    return None


def _gcode_beacon_script(code_id: str) -> str:
    """Script que avisa o backend quando a aba fecha (o arquivo em %TEMP% é temporário)."""
    return (
        "\n<!-- JARVIS: arquivo temporário — avisa ao fechar a aba -->\n"
        "<script>\n"
        "(function () {\n"
        f"  var url = '{GENCODE_ORIGIN}/generate-code/close/{code_id}';\n"
        "  function bye() { try { navigator.sendBeacon(url); } catch (e) {} }\n"
        "  window.addEventListener('beforeunload', bye);\n"
        "  window.addEventListener('pagehide', bye);\n"
        "})();\n"
        "</script>\n"
    )


def _gcode_inject_beacon(html: str, code_id: str) -> str:
    """Coloca o beacon no fim do documento (antes do </body> quando existe)."""
    script = _gcode_beacon_script(code_id)
    if re.search(r"</body\s*>", html, re.IGNORECASE):
        return re.sub(
            r"(</body\s*>)",
            lambda m: script + m.group(1),
            html,
            count=1,
            flags=re.IGNORECASE,
        )
    return html + script


def _gcode_cleanup_once() -> int:
    """Apaga os arquivos de código com mais de 10 minutos. Devolve quantos removeu."""
    now = time.time()
    removed = 0
    with _GCODE_LOCK:
        expired = [k for k, v in _GCODE.items() if now - float(v.get("created_at") or 0) > GENCODE_TTL_SECONDS]
        for k in expired:
            item = _GCODE.pop(k, None)
            if not item:
                continue
            try:
                Path(item["path"]).unlink(missing_ok=True)
                removed += 1
                _security_log("generate-code", f"limpeza automática: {k}")
            except Exception:  # noqa: BLE001
                pass
    return removed


def _gcode_cleanup_loop() -> None:
    """Roda a limpeza a cada 60 s enquanto o backend estiver de pé."""
    while True:
        time.sleep(60)
        _gcode_cleanup_once()


def _gcode_ensure_cleanup() -> None:
    global _GCODE_THREAD_STARTED
    if _GCODE_THREAD_STARTED:
        return
    _GCODE_THREAD_STARTED = True
    threading.Thread(target=_gcode_cleanup_loop, daemon=True, name="jarvis-code-cleanup").start()


@app.post("/generate-code")
def generate_code(body: GenerateCodeIn):
    """Gera código-fonte (via Groq), salva em %TEMP% e abre no navegador/editor padrão."""
    _gcode_ensure_cleanup()

    requested = str(body.language or "").strip().lower()
    requested = GENCODE_LANG_ALIASES.get(requested, requested)
    if requested and requested not in GENCODE_EXTENSIONS:
        _security_log("generate-code", f"linguagem não permitida: {requested}", blocked=True)
        return JSONResponse({"error": f"linguagem não permitida: {requested}"}, status_code=400)

    prompt = _gcode_sanitize(body.prompt)
    if not prompt:
        _security_log("generate-code", "prompt vazio ou inválido", blocked=True)
        return JSONResponse({"error": "diga o que programar (ex.: 'um site de portfólio')"}, status_code=400)

    lang = _gcode_detect_language(prompt, requested)
    code = None
    for _attempt in range(2):            # máximo 2 tentativas de geração
        candidate = _gcode_generate(prompt, lang)
        if candidate:
            code = candidate
            break
    if not code:
        _security_log("generate-code", f"falha ao gerar código: {prompt}", blocked=True)
        return JSONResponse(
            {"error": "não consegui gerar o código (confira a chave da Groq nas configurações)"},
            status_code=502,
        )

    code_id = uuid.uuid4().hex
    # no HTML o beacon entra no arquivo, então o corte reserva o espaço dele:
    # o limite de 200 KB vale para o arquivo final, beacon incluído
    budget = GENCODE_MAX_CODE
    if lang == "html":
        budget = max(1000, GENCODE_MAX_CODE - len(_gcode_beacon_script(code_id).encode("utf-8")))
    truncated = False
    if len(code.encode("utf-8")) > budget:
        _security_log("generate-code", "código acima de 200 KB — truncado", blocked=True)
        code = code.encode("utf-8")[:budget].decode("utf-8", errors="ignore")
        truncated = True
    if lang == "html":
        code = _gcode_inject_beacon(code, code_id)
    path = Path(tempfile.gettempdir()) / f"jarvis-code-{code_id}.{GENCODE_EXTENSIONS[lang]}"
    try:
        # newline="\n": no Windows o modo texto duplicaria cada \n em \r\n e o arquivo
        # passaria do limite de 200 KB por causa disso
        path.write_text(code, encoding="utf-8", newline="\n")
    except Exception as exc:  # noqa: BLE001
        _security_log("generate-code", f"não consegui gravar o arquivo: {exc}", blocked=True)
        return JSONResponse({"error": f"não consegui salvar o arquivo: {exc}"}, status_code=500)

    size = len(code.encode("utf-8"))
    with _GCODE_LOCK:
        _GCODE[code_id] = {"path": str(path), "created_at": time.time(), "prompt": prompt, "language": lang}
    _security_log("generate-code", f"{prompt} ({size} bytes) -> {path.name}")

    # HTML no navegador; .py/.js/.md e afins no editor padrão do Windows
    try:
        if lang == "html" or not hasattr(os, "startfile"):
            webbrowser.open(path.as_uri())
        else:
            os.startfile(str(path))  # type: ignore[attr-defined]  # noqa: S606
    except Exception:  # noqa: BLE001
        pass

    return {
        "ok": True,
        "id": code_id,
        "file": str(path),
        "path": str(path),
        "language": lang,
        "size": size,
        "truncated": truncated,
        "message": (
            "Pronto, Comandante. Gerei o código e abri no seu navegador."
            if lang == "html"
            else "Pronto, Comandante. Gerei o código e abri no seu editor."
        ),
    }


@app.post("/generate-code/close/{code_id}")
def generate_code_close(code_id: str):
    """Recebe o beacon da aba e apaga o arquivo gerado."""
    cid = re.sub(r"[^0-9a-fA-F]", "", str(code_id or ""))[:64]
    with _GCODE_LOCK:
        item = _GCODE.pop(cid, None)
    if not item:
        return {"ok": True, "removed": False}
    try:
        Path(item["path"]).unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass
    _security_log("generate-code", f"fechado pelo usuário e removido: {cid}")
    return {"ok": True, "removed": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
