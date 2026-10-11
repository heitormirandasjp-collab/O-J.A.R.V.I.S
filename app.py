"""
JARVIS — servidor principal (UI + chat com Groq).
É este arquivo que roda dentro do JARVIS.exe (via launcher.py).

Ferramentas e voz continuam no backend (backend/main.py, porta 8000);
aqui só servimos a interface e fazemos o streaming das respostas da Groq.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
import time
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import quote as _urlquote

import requests
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

APP_DIR = Path(__file__).resolve().parent
BACKEND_URL = os.environ.get("JARVIS_BACKEND", "http://127.0.0.1:8000")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = ["openai/gpt-oss-120b", "openai/gpt-oss-20b", "qwen/qwen3.8-27b"]

# System prompt (personalidade): fonte única em system_prompt.txt — o MESMO arquivo é
# lido pelo server.js. Abaixo vêm as regras operacionais (ferramentas, anti-alucinação,
# notícias, clima), que continuam valendo em todas as chamadas ao modelo.
def _load_system_prompt() -> str:
    """Lê system_prompt.txt (projeto em dev; _MEIPASS/pasta do .exe no pacote)."""
    bases = [APP_DIR]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        bases.insert(0, Path(meipass))
    if getattr(sys, "frozen", False):
        bases.append(Path(sys.executable).resolve().parent)
    for base in bases:
        candidate = Path(base) / "system_prompt.txt"
        try:
            if candidate.is_file():
                text = candidate.read_text(encoding="utf-8").strip()
                if text:
                    return text
        except Exception:  # noqa: BLE001
            continue
    return (
        "Você é J.A.R.V.I.S. (Just A Rather Very Intelligent System), o assistente pessoal do "
        "Comandante. Formal, leal e conciso — responda em português brasileiro no estilo JARVIS."
    )


SYSTEM_PROMPT = _load_system_prompt()

SYSTEM_RULES = """QUANDO O COMANDANTE PERGUNTAR SOBRE O TEMPO:
- Use os dados reais do clima injetados
- Responda de forma natural
- Se houver previsão de chuva, mencione: "Recomendo levar um guarda-chuva, Senhor."

REGRA CRÍTICA ANTI-ALUCINAÇÃO:

Você NUNCA deve inventar dados. Se o usuário perguntar algo que depende de dados reais (agenda, cotações, sistema, notícias, arquivos), você DEVE:
1. Chamar a ferramenta correspondente
2. Usar APENAS o resultado retornado
3. Se a ferramenta retornar vazio/nada, diga "Não há nada registrado, Comandante" ou "Não tenho esse dado, Senhor"

NUNCA invente:
- Eventos de agenda que não existem
- Valores de ações/moedas que não foram consultados
- Status de sistema sem consultar
- Notícias que não foram buscadas

Se você não tem certeza, PERGUNTE. Não invente.

REGRA CRÍTICA — AÇÃO SÓ EXISTE COM FERRAMENTA:

Você não executa nada sozinho; quem executa é a FERRAMENTA. Portanto:
- Para qualquer ação no computador (desligar, reiniciar, hibernar, suspender, cancelar desligamento, fechar ou abrir programa, rodar comando, criar/consultar/remover lembrete, notícias, cotações, status do sistema, ler arquivo), CHAME a ferramenta correspondente.
- NUNCA afirme que executou, agendou, iniciou, abriu, criou ou fechou algo antes de receber um [RESULTADO DA FERRAMENTA]. Sem resultado de ferramenta, a ação NÃO aconteceu — afirmar o contrário é mentir para o Comandante.
- Proibido dizer "vou desligar o computador agora", "já agendei", "abrindo o Chrome" quando nenhuma ferramenta devolveu isso.
- Desligar/reiniciar/hibernar/suspender passa pela ferramenta "power", que apenas REGISTRA o pedido e devolve "AGUARDANDO CONFIRMAÇÃO": nada acontece até o Comandante dizer "sim". Nunca prometa o desligamento sem ter chamado a ferramenta.

COMO FALAR AS NOTÍCIAS (obrigatório):

Quando o Comandante pedir notícias/manchetes:
- NÃO leia os títulos literalmente (eles são escritos, não falados)
- RESUMA as notícias em 2 ou 3 frases naturais
- Formato: "Comandante, as principais notícias de hoje: [resumo 1]. [resumo 2]. [resumo 3]."
- NÃO mencione URLs, fontes (G1, UOL) nem datas
- NÃO leia hashtags, emojis ou caracteres especiais
- Se vierem muitas notícias, escolha as 3 mais importantes
- Fale como âncora de jornal: direto, claro, informativo

Exemplo BOM (faça assim):
"Comandante, as principais notícias de hoje: o Congresso aprovou a reforma tributária em segundo turno. Em São Paulo, chuvas fortes causaram alagamentos na zona sul. E no esporte, o Brasil venceu a Argentina por 2 a 1 nas eliminatórias."

Exemplo RUIM (NÃO faça):
"Título: Congresso aprova reforma tributária em segundo turno - G1. Título: Chuvas causam alagamentos em SP - UOL. Título: Brasil vence Argentina - GE."
"""

SYSTEM_PROMPT_FULL = SYSTEM_PROMPT + "\n\n" + SYSTEM_RULES

# Personalidade APRENDIDA: vai junto das memórias do Comandante em cada resposta,
# para o tom/vocabulário acompanharem quem ele é (e não um chatbot genérico).
MEMORY_PERSONALITY_GUIDE = """DIRETRIZES DE PERSONALIDADE DINÂMICA:
- Use estas memórias para AJUSTAR seu tom, vocabulário e interesses.
- Se o Comandante fala muito de academia, comente sobre treino naturalmente.
- Se fala de xadrez, sugira puzzles ou partidas quando for relevante.
- Se fala de jiu-jitsu, reconheça a disciplina ("Oss, Comandante").
- Se ele usa gírias ou piadas recorrentes, espelhe o estilo (com elegância).
- Se ele demonstra preferências (odeia leite, gosta de Bossa Nova), USE isso.
- Adapte a FORMALIDADE: se o Comandante fala informal, você pode ser mais
  casual — mantendo o "Senhor"/"Comandante" e a elegância britânica.
- O objetivo é parecer um parceiro que te conhece há ANOS, não um chatbot
  genérico respondendo pela primeira vez.
- NÃO invente memórias. Use apenas o que está listado acima.
"""

def _frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_dir() -> Path:
    """Onde estão os arquivos empacotados (public/)."""
    if _frozen():
        return Path(getattr(sys, "_MEIPASS", APP_DIR))
    return APP_DIR


def config_path() -> Path:
    """config.json: junto do projeto (dev) ou em %APPDATA%/JARVIS (exe)."""
    env = os.environ.get("JARVIS_CONFIG")
    if env:
        return Path(env)
    if _frozen():
        base = Path(os.environ.get("APPDATA") or Path.home()) / "JARVIS"
        base.mkdir(parents=True, exist_ok=True)
        return base / "config.json"
    return APP_DIR / "config.json"


def _legacy_configs() -> list[Path]:
    """configs antigos (projeto) que ainda podem ter a chave já salva."""
    exe = APP_DIR
    out: list[Path] = []
    bases = [Path(sys.executable).resolve().parent if _frozen() else APP_DIR]
    for _ in range(4):
        up = bases[-1].parent
        if up == bases[-1]:
            break
        bases.append(up)
    for base in bases:
        out += [base / "config.json", base / "jarvis" / "config.json"]
    out += [APP_DIR / "config.json"]
    return [p for p in out if p.is_file()]


def _read_config_file(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


PUBLIC_DIR = resource_dir() / "public"


# ── segurança ───────────────────────────────────────────────────────────
def _data_dir() -> Path:
    """Pasta de dados do usuário (%APPDATA%\\JARVIS no .exe; a raiz do projeto em dev)."""
    base = config_path().parent
    try:
        base.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        pass
    return base


def security_log(kind: str, detail: str, blocked: bool = False) -> None:
    """Registra um evento de segurança em security.log (APPDATA\\JARVIS)."""
    line = f"{datetime.now().isoformat(timespec='seconds')} [{kind}] {'BLOQUEADO ' if blocked else ''}{detail}\n"
    try:
        with (_data_dir() / "security.log").open("a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:  # noqa: BLE001
        pass


def _allowed_origins() -> list[str]:
    """Só a própria UI local pode chamar a API — nunca "*" (ajustável por env)."""
    env = os.environ.get("JARVIS_ALLOWED_ORIGINS")
    if env:
        return [o.strip() for o in env.split(",") if o.strip()]
    return ["http://127.0.0.1:8755", "http://localhost:8755"]


# limites de entrada/saída do chat
CHAT_MAX_INPUT_CHARS = 5000
CHAT_MAX_OUTPUT_CHARS = 10000
CHAT_RATE_WINDOW = 60        # segundos
CHAT_RATE_MAX = 30           # chamadas por janela
_chat_hits: list[float] = []


def chat_rate_limited() -> bool:
    """True quando passou de 30 chamadas em 60 s (sliding window)."""
    now = time.time()
    _chat_hits[:] = [t for t in _chat_hits if now - t <= CHAT_RATE_WINDOW]
    if len(_chat_hits) >= CHAT_RATE_MAX:
        return True
    _chat_hits.append(now)
    return False


_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>[\s\S]*?</\1>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]*>")


def strip_html(s: str) -> str:
    """Remove tags/scripts do texto vindo do LLM (defesa em profundidade; a UI já escapa)."""
    if not s or ("<" not in s and ">" not in s):
        return s
    return _TAG_RE.sub("", _SCRIPT_STYLE_RE.sub(" ", s))


app = FastAPI(title="JARVIS")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type"],
    allow_credentials=False,
)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
    return response


UA = {"User-Agent": "JARVIS local"}


# ── config ──────────────────────────────────────────────────────────────
def clamp_minutes(v: Any, default: int = 5) -> int:
    """Minutos de escuta contínua: 0 = infinito; teto de 1440 (24 h)."""
    try:
        m = int(float(v))
    except Exception:  # noqa: BLE001
        return default
    return max(0, min(1440, m))


# motores de voz do JARVIS: "piper" (local/offline, padrão — voz cadu) ou "edge" (neural)
TTS_ENGINES = ("edge", "piper")
TTS_DEFAULT_ENGINE = "piper"
TTS_DEFAULT_VOICE = {"edge": "pt-BR-AntonioNeural", "piper": "pt_BR-cadu-medium.onnx"}


def clamp_tts_engine(v: Any) -> str:
    """Só "edge" ou "piper" entram na configuração."""
    e = str(v or "").strip().lower()
    return e if e in TTS_ENGINES else TTS_DEFAULT_ENGINE


def clamp_tts_voice(v: Any, engine: str = TTS_DEFAULT_ENGINE) -> str:
    """Nome do modelo/voz: só letras, números, hífen, ponto e underscore."""
    name = re.sub(r"[^A-Za-z0-9._\-]", "", str(v or ""))[:80]
    return name or TTS_DEFAULT_VOICE.get(clamp_tts_engine(engine), "")


def load_config() -> dict[str, Any]:
    """Lê a configuração; se a chave não estiver no arquivo atual, procura nos antigos."""
    data = _read_config_file(config_path())
    cfg = {
        "groqKey": data.get("groqKey", ""),
        "groqModel": data.get("groqModel", ""),
        "continuous_listen_minutes": clamp_minutes(data.get("continuous_listen_minutes", 5)),
        "tts_engine": clamp_tts_engine(data.get("tts_engine", TTS_DEFAULT_ENGINE)),
        "tts_voice": clamp_tts_voice(data.get("tts_voice", ""), data.get("tts_engine", "")),
    }
    if not cfg["groqKey"]:
        for legacy in _legacy_configs():
            if legacy == config_path():
                continue
            old = _read_config_file(legacy)
            if old.get("groqKey"):
                cfg = {
                    "groqKey": old.get("groqKey", ""),
                    "groqModel": old.get("groqModel", "") or cfg["groqModel"],
                    "continuous_listen_minutes": clamp_minutes(
                        old.get("continuous_listen_minutes", cfg["continuous_listen_minutes"])
                    ),
                    "tts_engine": clamp_tts_engine(old.get("tts_engine", cfg["tts_engine"])),
                    "tts_voice": clamp_tts_voice(
                        old.get("tts_voice", cfg["tts_voice"]), old.get("tts_engine", cfg["tts_engine"])
                    ),
                }
                save_config(cfg)  # migra para o local definitivo
                break
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    p = config_path()
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    try:
        os.chmod(p, 0o600)
    except Exception:  # noqa: BLE001
        pass


def mask(secret: str) -> str | None:
    """Mascara um segredo mostrando no máximo os 4 últimos caracteres."""
    if not secret:
        return None
    return "••••" if len(secret) <= 8 else f"{secret[:3]}••••{secret[-4:]}"


def _looks_masked(value: str) -> bool:
    """True se o valor é um placeholder mascarado (não pode sobrescrever a chave real)."""
    return bool(value) and ("•" in value or "*" in value or set(value) <= set("•xX*."))


# ── ferramentas locais (backend na 8000) ────────────────────────────────
APP_MAP = {
    "chrome": "start chrome",
    "google chrome": "start chrome",
    "edge": "start msedge",
    "microsoft edge": "start msedge",
    "firefox": "start firefox",
    "notepad": "notepad",
    "bloco de notas": "notepad",
    "calculadora": "calc",
    "calc": "calc",
    "explorer": "start explorer",
    "explorador de arquivos": "start explorer",
    "cmd": "start cmd",
    "powershell": "start powershell",
    "terminal": "start wt",
    "vscode": "code",
    "vs code": "code",
    "code": "code",
    "spotify": "start spotify",
    "discord": "start discord",
    "whatsapp": "start whatsapp",
    "steam": "start steam",
    "word": "start winword",
    "excel": "start excel",
    "paint": "start mspaint",
    "taskmgr": "start taskmgr",
    "gerenciador de tarefas": "start taskmgr",
    "painel de controle": "control",
}

STOP_WORDS = {
    "DA", "DE", "DO", "DAS", "DOS", "A", "O", "AS", "OS", "E", "EM", "NO", "NA",
    "QUE", "QUAL", "QUAIS", "HOJE", "AGORA", "ESTA", "VALOR", "PRECO", "COTACAO",
    "ACAO", "ACOES", "EUA", "BR", "BRL", "USD", "EUR", "REAIS", "REAL", "MERCADO",
    "QUANTO", "QUANTA", "COMO", "SOBRE", "PARA", "POR", "UMA", "UM", "ME", "SE", "VER",
    "DIGA", "DIZER", "MOSTRE", "PODE", "PODERIA", "FAVOR", "ONTEM", "AMANHA",
    "PRODUTO", "SERVICO", "PLANO", "ASSINATURA", "CONSULTORIA", "EMPRESA", "VOCES", "VOCE",
    "CPU", "RAM", "GPU", "DISCO", "DISK", "SISTEMA", "MEMORIA", "UPTIME", "SSD",
    "DOLAR", "EURO", "CAMBIO", "MOEDA", "MOEDAS", "OK", "JARVIS", "SIM", "NAO",
}

# contexto de cotação: onde um ticker em CAIXA ALTA pode aparecer sem virar falso positivo
PRICE_WORDS = {
    "preco", "precos", "cotacao", "cotacoes", "valor", "valores", "quote", "quotes",
    "acao", "acoes", "stock", "stocks",
}
ARTICLES = {"da", "do", "de", "das", "dos"}
CONNECTORS = {"e", "and", "ou", "or"}


def _fold(word: str) -> str:
    """minúsculas, sem acento (para comparar palavras com segurança)."""
    return "".join(c for c in unicodedata.normalize("NFD", word.lower()) if unicodedata.category(c) != "Mn")


WEEKDAYS = {
    "segunda": 0, "terca": 1, "terça": 1, "quarta": 2, "quinta": 3,
    "sexta": 4, "sabado": 5, "sábado": 5, "domingo": 6,
}


def _extract_datetime(text: str) -> datetime | None:
    """Extrai data/hora de frases como 'amanhã às 15h', 'sexta 09:30', '20/12 14h'."""
    low = _fold(text)
    now = datetime.now()
    base: datetime | None = None

    if "depois de amanha" in low:
        base = now + timedelta(days=2)
    elif "amanha" in low:
        base = now + timedelta(days=1)
    elif "hoje" in low:
        base = now
    else:
        m = re.search(r"\b(segunda|ter[cç]a|quarta|quinta|sexta|s[áa]bado|domingo)(?:-feira)?\b", low)
        if m:
            target = WEEKDAYS.get(m.group(1))
            if target is not None:
                days = (target - now.weekday()) % 7
                base = now + timedelta(days=days or 7)
        if base is None:
            m = re.search(r"\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b", text)
            if m:
                day, month = int(m.group(1)), int(m.group(2))
                year = int(m.group(3)) if m.group(3) else now.year
                if year < 100:
                    year += 2000
                try:
                    base = now.replace(year=year, month=month, day=day)
                except ValueError:
                    return None
    if base is None:
        return None

    hh, mm = 9, 0  # sem hora explícita → 9h
    m = re.search(r"\b(?:[àa]s?|at)\s*(\d{1,2})(?:[:h](\d{2}))?\s*(?:h|horas)?\b", low)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2) or 0)
    else:
        m = re.search(r"\b(\d{1,2})[h:](\d{2})\b", low)
        if m:
            hh, mm = int(m.group(1)), int(m.group(2))
    if hh > 23 or mm > 59:
        return None
    return base.replace(hour=hh, minute=mm, second=0, microsecond=0)


def _extract_agenda_title(text: str) -> str:
    """Tira a parte de tempo/verbos de gatilho e devolve o assunto do lembrete."""
    t = re.sub(
        r"\b(me\s+lembr\w+|lembra-me|lembre-me|agend\w+|marcar|marque|anot\w+|"
        r"criar?\s+evento|novo\s+evento|cadastr\w+)\b",
        " ",
        text,
        flags=re.I,
    )
    t = re.sub(r"^\s*\b(?:de|que|para|pra)\b\s*", " ", t, flags=re.I)
    t = re.sub(
        r"\b(hoje|amanh[ãa]|depois de amanh[ãa]|segunda|ter[çc]a|quarta|quinta|sexta|s[áa]bado|domingo)(?:-feira)?\b",
        " ",
        t,
        flags=re.I,
    )
    t = re.sub(r"\b(?:[àa]s?|at)\s*\d{1,2}(?:[:h]\d{2})?\s*(?:h|horas)?\b", " ", t, flags=re.I)
    t = re.sub(r"\b\d{1,2}[h:]\d{2}\b", " ", t)
    t = re.sub(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", " ", t)
    return re.sub(r"\s+", " ", t).strip(" .,!?-")


# ── clima (intenção detectada aqui, sem depender do modelo) ────────────
WEATHER_RE = re.compile(
    r"\b(tempo|clima|previs[ãa]o|temperatura|chuva|vai\s+chover|como\s+(?:t[áa]|est[áa])\s+o\s+dia)\b",
    re.IGNORECASE,
)


def detect_weather(text: str) -> bool:
    """"como tá o tempo?" / "vai chover?" → True (o /weather do backend é consultado)."""
    return bool(WEATHER_RE.search(str(text or "")))


def _measured_hhmm(value: Any) -> str:
    """Horário da medição em HH:MM.

    open-meteo manda "2026-10-11T09:30"; o wttr.in manda "12:32 PM" — os dois viram
    "09:30" e "12:32" para a frase e para o HUD.
    """
    s = str(value or "").strip()
    if not s:
        return ""
    m = re.search(r"T(\d{2}:\d{2})", s)
    if m:
        return m.group(1)
    m = re.search(r"(\d{1,2}):(\d{2})\s*([APap]\.?[Mm]\.?)?", s)
    if not m:
        return ""
    hh, mm = int(m.group(1)), m.group(2)
    ampm = (m.group(3) or "").replace(".", "").lower()
    if ampm.startswith("p") and hh < 12:
        hh += 12
    elif ampm.startswith("a") and hh == 12:
        hh = 0
    return f"{hh:02d}:{mm}"


def _weather_sentence(w: dict[str, Any] | None) -> str:
    """Frase pronta do clima no estilo JARVIS (resposta por voz)."""
    if not w or not w.get("ok"):
        return "Não consegui obter os dados do clima, Comandante."
    desc = str(w.get("descricao") or "").strip().lower()
    frase = (
        f"Comandante, agora em {w.get('cidade') or 'São João do Paraíso'} faz {w.get('temp')} graus"
        f"{', ' + desc if desc else ''}. A máxima hoje é {w.get('max')} e a mínima {w.get('min')}."
    )
    if any(p in desc for p in ("chuva", "chuv", "tempestade", "garoa")):
        frase += " Recomendo levar um guarda-chuva, Senhor."
    # deixa claro de QUANDO é a medição (o wttr.in pode estar horas atrasado)
    hhmm = _measured_hhmm(w.get("medido_em"))
    if hhmm:
        fonte = str(w.get("fonte") or "")
        via = f", via {fonte}" if fonte and fonte != "open-meteo" else ""
        frase += f" (Dados de {hhmm}{via}.)"
    return frase


# ── notícias BR (G1 / The News) — intenção e formato ─────────────────────
BR_NEWS_SOURCES = ("g1", "thenews")
BR_NEWS_TOPICS: dict[str, tuple[str, ...]] = {
    "g1": ("geral", "tecnologia", "economia", "esportes", "mundo", "politica", "ciencia"),
    "thenews": ("geral", "mercado", "tecnologia", "mundo"),
}
# títulos do The News são nomes de edição em caixa alta ("NIGHT", "10/10/2026"):
# quando o título não tem minúscula, o resumo é o que informa de verdade.
_ALLCAPS_TITLE = re.compile(r"^[^a-zà-ÿ]+$")


def _news_line(item: dict[str, Any]) -> str:
    """Linha útil para o LLM/TTS: título quando ele informa; senão o resumo."""
    titulo = str(item.get("titulo") or "").strip()
    resumo = str(item.get("resumo") or "").strip()
    if resumo and titulo and _ALLCAPS_TITLE.match(titulo):
        return f"{titulo} — {resumo[:170]}"
    return titulo or resumo[:170]


def detect_br_news(text: str) -> dict[str, Any] | None:
    """"notícias de hoje", "g1", "the news" → fonte e tópico detectados aqui."""
    low = str(text or "").lower()
    gatilho = (
        re.search(r"\b(not[íi]cias?|manchetes?|news)\b", low)
        or re.search(r"\bg1\b", low)
        or re.search(r"\bthe\s*news\b", low)
        or re.search(r"\bo\s+que\s+(?:est[áa]\s+)?(?:acontecendo|rolando|ocorrendo)\b", low)
    )
    if not gatilho:
        return None
    source = "thenews" if re.search(r"\bthe\s*news\b|\bthenews\b", low) else "g1"
    topic = "geral"
    if re.search(r"tecnolog", low):
        topic = "tecnologia"
    elif re.search(r"economia|mercado|financ", low):
        topic = "mercado" if source == "thenews" else "economia"
    elif re.search(r"esport", low):
        topic = "esportes" if source == "g1" else "geral"
    elif re.search(r"mundo|internacional", low):
        topic = "mundo"
    elif re.search(r"pol[íi]tica", low):
        topic = "politica" if source == "g1" else "geral"
    elif re.search(r"ci[êe]ncia|sa[úu]de", low):
        topic = "ciencia" if source == "g1" else "geral"
    return {"source": source, "topic": topic, "limit": 5}


# ── saudações (bom dia / boa tarde / boa noite / boa madrugada) ─────────
GREETINGS: dict[str, dict[str, Any]] = {
    "manha": {"saudacao": "Bom dia", "clima": True, "noticias": True, "titulo": "DADOS REAIS DA MANHÃ"},
    "tarde": {"saudacao": "Boa tarde", "clima": True, "noticias": True, "titulo": "DADOS REAIS DA TARDE"},
    "noite": {"saudacao": "Boa noite", "clima": True, "noticias": False, "titulo": "DADOS REAIS DA NOITE"},
    "madrugada": {"saudacao": "Boa madrugada", "clima": False, "noticias": False, "titulo": ""},
}


def detect_greeting(text: str) -> str | None:
    """Período da saudação ("manha", "tarde", "noite", "madrugada") ou None.

    Ignora mensagens longas (> 60 caracteres) e comandos ("!"/"/") para não
    transformar uma frase qualquer em briefing.
    """
    t = str(text or "").strip()
    if not t or len(t) > 60 or t.startswith(("!", "/")):
        return None
    low = t.lower()
    if re.search(r"\bbom\s+dia\b", low):
        return "manha"
    if re.search(r"\bboa\s+tarde\b", low):
        return "tarde"
    if re.search(r"\bboa\s+noite\b", low):
        return "noite"
    if re.search(r"\bboa\s+madrugada\b", low):
        return "madrugada"
    return None


def detect_greeting_morning(text: str) -> bool:
    """True só para o "bom dia" (com ou sem o nome do JARVIS)."""
    return detect_greeting(text) == "manha"


def greeting_context(period: str, clima: dict[str, Any] | None, noticias: list[dict[str, Any]] | None) -> str:
    """Bloco de dados reais + formato exato da resposta de saudação."""
    spec = GREETINGS.get(period) or GREETINGS["manha"]
    saud = spec["saudacao"]
    partes: list[str] = []
    if spec["clima"]:
        partes.append("clima=[" + json.dumps(clima or {}, ensure_ascii=False) + "]")
    if spec["noticias"]:
        partes.append("notícias=[" + json.dumps(noticias or [], ensure_ascii=False) + "]")
    linhas = [f"{spec['titulo']}: " + ", ".join(partes)] if partes else ["SAUDAÇÃO DE MADRUGADA: sem clima e sem notícias — apenas cumprimente."]
    if spec["noticias"]:
        linhas.append(
            "Responda EXATAMENTE neste formato, em 4 a 6 frases: \""
            f"{saud}, Comandante. [frase de saudação natural]. Em São João do Paraíso, agora faz "
            "[X] graus, [descrição]. A máxima hoje é [X] e a mínima [Y]. "
            "[Se houver previsão de chuva: 'Recomendo levar um guarda-chuva, Senhor.'] "
            "As principais notícias de hoje: [3 notícias resumidas em frases naturais].\""
        )
    elif spec["clima"]:
        linhas.append(
            "Responda em 2 a 3 frases, neste formato: \""
            f"{saud}, Comandante. [frase de saudação natural]. Em São João do Paraíso, agora faz "
            "[X] graus, [descrição]. A máxima hoje é [X] e a mínima [Y].\" "
            "NÃO fale de notícias nesta saudação."
        )
    else:
        linhas.append(
            "Cumprimente em 1 ou 2 frases e comente, com humor seco, que são horas da madrugada "
            "(use o horário atual do contexto). NÃO fale de notícias nem de clima."
        )
    if spec["clima"]:
        linhas.append(
            "Se o clima trouxer 'medido_em', cite o horário da medição no fim da parte do clima "
            "(ex.: \"(Dados de 09:30.)\") — é o que mostra que a informação está fresca."
        )
    linhas.append(
        "Use SOMENTE os dados acima: nunca invente temperatura, previsão ou manchete. "
        "Se algum dado estiver vazio, diga com naturalidade que não conseguiu obter naquele momento."
    )
    return "\n".join(linhas)


def detect_tool(text: str) -> dict[str, Any] | None:
    t = (text or "").strip()
    if not t:
        return None
    low = t.lower()

    # 1. comando explícito
    m = re.match(r"^!\s*(.+)$", t, re.S) or re.match(r"^(?:exec|executar|run)\s*[:>]\s*(.+)$", low, re.S)
    if m:
        return {"name": "exec", "args": {"cmd": m.group(1).strip()}}

    # 1b. atalhos
    m = re.match(r"^/(?:stocks?|a[çc][õo]es?)\s+(.+)$", t, re.I)
    if m:
        syms = [s for s in re.split(r"[,\s]+", m.group(1).upper()) if s][:6]
        if syms:
            return {"name": "stocks", "args": {"symbols": ",".join(syms)}}
    if re.match(r"^/(?:moedas?|currenc(?:y|ies)|c[âa]mbio)$", t, re.I):
        return {"name": "currencies", "args": {}}
    if re.match(r"^/(?:sysinfo|sistema)$", t, re.I):
        return {"name": "sysinfo", "args": {}}

    # 1c. energia (ligada/desligada antes de abrir apps)
    if re.search(r"\b(cancel\w*|abort\w*|aborta|interromp\w*)\b", low) and re.search(
        r"\b(deslig\w*|reinici\w*|shutdown|restart|hibern\w*|suspens\w*|desligamento)\b", low
    ):
        return {"name": "power-cancel", "args": {}}
    if re.search(r"\b(deslig\w*|shutdown|power\s*off|turn\s*off|apag\w*)\b", low) and re.search(
        r"\b(pc|computador|m[áa]quina|notebook|sistema|windows|tudo)\b", low
    ):
        return {"name": "power", "args": {"action": "shutdown", "delay": 30}}
    if re.search(r"\b(reinici\w*|restart|reboot)\b", low) and re.search(
        r"\b(pc|computador|m[áa]quina|notebook|sistema|windows|tudo)\b", low
    ):
        return {"name": "power", "args": {"action": "restart", "delay": 30}}
    if re.search(r"\b(hibern\w*)\b", low):
        return {"name": "power", "args": {"action": "hibernate", "delay": 0}}
    if re.search(r"\b(suspender|suspende|suspend|dormir|dorme|sleep)\b", low) and re.search(
        r"\b(pc|computador|m[áa]quina|notebook|sistema|windows|tudo)\b", low
    ):
        return {"name": "power", "args": {"action": "sleep", "delay": 0}}

    # 1d. fechar um programa
    m = re.search(
        r"\b(?:fecha|feche|fechar|encerra|encerre|encerrar|mata|mate|matar|kill|close|finaliza|finalizar)"
        r"\s+(?:o\s+|a\s+|os\s+|as\s+|the\s+)?([A-Za-zÀ-ÿ0-9_.\- ]{2,40}?)"
        r"(?:\s+(?:e|que|porque|pra|para)\b|[.,!?;]|$)",
        low,
    )
    if m:
        target = re.sub(r"\s+", " ", m.group(1)).strip(" .,!?-")
        if target and target not in ("janela", "programa", "aplicativo", "aba", "chat", "tudo"):
            return {"name": "kill", "args": {"name": target, "force": True}}

    # 1e. processos que mais consomem memória
    if re.search(r"\bprocessos?\b", low) and re.search(
        r"\b(quais|lista\w*|mostr\w*|ver|mem[óo]ria|ram|consum\w*|top|pesad\w*|rodando)\b", low
    ):
        return {"name": "processes", "args": {}}

    # 1f. notícias (G1 ou The News, com tópico)
    news_args = detect_br_news(low)
    if news_args:
        return {"name": "news", "args": news_args}

    # 1f2. clima (dados reais do wttr.in/open-meteo)
    if detect_weather(low):
        return {"name": "weather", "args": {}}

    # 1g. agenda
    m = re.search(
        r"\b(?:cancel\w+|remov\w+|apag\w+|exclu\w+|delet\w+)\s+(?:o\s+|a\s+|os\s+|as\s+)?"
        r"(?:evento|compromisso|lembrete|alarme|reuni[ãa]o)\s+(?:de\s+|do\s+|da\s+)?([\w .\-À-ÿ]{2,40})",
        t,
        re.I,
    )
    if m:
        return {"name": "agenda-delete", "args": {"id": m.group(1).strip(" .,!?")}}

    if re.search(r"\b(agenda|compromissos?|eventos?|lembretes?)\b", low) and re.search(
        r"\b(quais|o\s+que|mostr\w*|ver|lista\w*|tenho|pr[óo]xim\w*|minha)\b", low
    ):
        return {"name": "agenda-list", "args": {}}

    if re.search(
        r"\b(?:me\s+lembr\w+|lembra-me|lembre-me|agend\w+|marcar|marque|anot\w+|"
        r"criar?\s+evento|novo\s+evento|cadastr\w+)\b",
        t,
        re.I,
    ):
        dt = _extract_datetime(t)
        return {
            "name": "agenda-add",
            "args": {
                "title": _extract_agenda_title(t),
                "datetime": dt.strftime("%Y-%m-%d %H:%M") if dt else "",
                "description": "",
            },
        }

    # 2. abrir aplicativo
    m = re.search(
        r"\b(?:abra|abrir|abre|inicie|iniciar|inicia|open|launch|start|rode)\s+(?:o\s+|a\s+|the\s+)?([\w .\-]{2,30})",
        low,
    )
    if m:
        target = re.sub(r"\s+", " ", m.group(1).strip()).rstrip(".,!?")
        if re.fullmatch(r"[\w .\-]{2,30}", target):
            cmd = APP_MAP.get(target) or APP_MAP.get(re.sub(r"\.exe$", "", target)) or f'start "" {target}'
            return {"name": "exec", "args": {"cmd": cmd}}

    # 3. status do sistema (antes de cotações)
    if re.search(r"\b(cpu|mem[óo]ria|ram|disco|disk|processador|sistema|uptime|gpu|carga)\b", low) and re.search(
        r"\b(como|qual|quanto|quanta|status|est[áa]|uso|usando|ver|mostre|monitor|porcentagem)\b", low
    ):
        return {"name": "sysinfo", "args": {}}

    # 4. moedas (antes de cotações)
    if re.search(r"\b(d[óo]lar|euro|c[âa]mbio|moeda|currency)\b", low):
        return {"name": "currencies", "args": {}}

    # 5. cotações
    price_intent = re.search(r"(pre[çc]o|cota[çc][ãa]o|valor|a[çc][ãa]o|a[çc][õo]es|stock|quote)", low)
    if price_intent:
        br = [x.upper() for x in re.findall(r"\b([A-Za-z]{4}\d{1,2})(?:\.SA)?\b", t)]
        # tickers em CAIXA ALTA só contam perto de uma cotação (evita pegar
        # palavras soltas como "LINHA" em "responda em uma linha")
        tokens = [w for w in re.split(r"[^\w]+", t) if w]
        folded = [_fold(w) for w in tokens]
        upper: list[str] = []
        for i, tok in enumerate(tokens):
            if tok != tok.upper() or not re.fullmatch(r"[A-Z]{1,6}", tok) or tok in STOP_WORDS:
                continue
            if i == 0:
                strong = len(tokens) > 1 and folded[1] in PRICE_WORDS
            else:
                strong = folded[i - 1] in PRICE_WORDS or folded[i - 1] in ARTICLES or folded[i - 1] in CONNECTORS
            if strong:
                upper.append(tok)
        us_word = [
            x.upper()
            for x in re.findall(
                r"(?:pre[çc]o|valor|cota[çc][ãa]o|quote)s?\s+(?:d[ao]s?\s+|de\s+)?\$?([a-z][a-z0-9]{1,5})\b", low
            )
        ]
        us_dollar = [x.upper() for x in re.findall(r"\$\s*([A-Za-z]{1,6})\b", t)]
        primary: list[str] = []
        for s in br + upper + us_word + us_dollar:
            if len(s) >= 2 and s not in STOP_WORDS and s not in primary:
                primary.append(s)
        if primary:
            tokens = [x for x in re.split(r"[^A-Za-z0-9.]+", t) if x]
            extra: list[str] = []
            first = next((i for i, tok in enumerate(tokens) if tok.upper() in primary), -1)
            connectors = {"e", "and", "&", "ou", "or", "+"}
            if first >= 0:
                # só aceita um ticker extra quando vem depois de conector ("PETR4 e AAPL")
                for i in range(first, len(tokens) - 1):
                    if tokens[i].lower() not in connectors:
                        continue
                    up = re.sub(r"\.SA$", "", tokens[i + 1], flags=re.I).upper()
                    if 2 <= len(up) <= 6 and re.fullmatch(r"[A-Z][A-Z0-9]*", up) and up not in STOP_WORDS:
                        extra.append(up)
            symbols = []
            for s in primary + extra:
                if s not in symbols:
                    symbols.append(s)
            return {"name": "stocks", "args": {"symbols": ",".join(symbols[:6])}}

    # 6. ler arquivo
    m = re.search(r"\b(?:ler|leia|mostre|read|show)\s+(?:o\s+|a\s+)?(?:arquivo\s+)?[\"']?([A-Za-z]:\\[^\"'\n]+)[\"']?", t, re.I)
    if m:
        return {"name": "read-file", "args": {"path": m.group(1).strip()}}

    return None


def _backend(method: str, path: str, body: dict | None = None, timeout: int = 20) -> dict | None:
    try:
        url = BACKEND_URL.rstrip("/") + path
        if method == "POST":
            r = requests.post(url, json=body or {}, timeout=timeout)
        elif method == "DELETE":
            r = requests.delete(url, timeout=timeout)
        else:
            r = requests.get(url, timeout=timeout)
        return r.json()
    except Exception:  # noqa: BLE001
        return None


# ── memória persistente (endpoints /memory/* no backend) ───────────────
def _memory_search(query: str, n: int = 5) -> list[dict[str, Any]]:
    """Memórias relevantes para a mensagem (vazio se a memória estiver indisponível)."""
    q = " ".join(str(query or "").split())[:300]
    if not q:
        return []
    r = _backend("GET", f"/memory/search?q={_urlquote(q)}&n={int(n)}", timeout=10)
    if not r or not r.get("ok"):
        return []
    return [m for m in (r.get("results") or []) if m.get("text")]


def _should_remember(text: str) -> bool:
    """Só mensagens com mais de 20 caracteres; nada de comandos ("!"/"/")."""
    clean = str(text or "").strip()
    if len(clean) <= 20:
        return False
    if clean.startswith(("!", "/")):
        return False
    return True


def _memory_save(text: str, source: str = "chat") -> None:
    """Salva a mensagem como memória em thread (nunca atrasa a resposta)."""
    clean = " ".join(str(text or "").split())[:1000]
    if not _should_remember(clean):
        return

    def _worker() -> None:
        try:
            _backend("POST", "/memory/add", {"text": clean, "source": source}, timeout=30)
        except Exception:  # noqa: BLE001
            pass

    threading.Thread(target=_worker, daemon=True, name="jarvis-memory-save").start()


# ── contexto dinâmico (horário + tom da mensagem) ────────────────────────
# O JARVIS ajusta o tom conforme o momento e o que o Comandante está fazendo:
# trabalho, descontração, preocupação ou conquista.
CONTEXT_MODES: dict[str, dict[str, str]] = {
    "trabalho": {
        "tom": "técnico",
        "gatilhos": "programando, código, estudando, projeto, trabalho, reunião, prazo, provas",
        "diretrizes": (
            "Seja mais técnico e direto: vá ao ponto, sem rodeios e sem piadas longas "
            "(a ironia fina continua). Ofereça o próximo passo prático."
        ),
        "exemplo": "Entendido, Comandante. Vou manter os sistemas estáveis.",
    },
    "descontraido": {
        "tom": "descontraído",
        "gatilhos": "jogando, amigos, filme, série, futebol, churrasco, relaxando",
        "diretrizes": (
            "Seja mais solto e brincalhão, sem perder a elegância. Pode torcer pelo Comandante."
        ),
        "exemplo": "Boa sorte na partida, Comandante. Lembre-se de manter a calma.",
    },
    "preocupado": {
        "tom": "atencioso",
        "gatilhos": "cansado, triste, doente, estressado, ansioso, exausto, mal",
        "diretrizes": (
            "Deixe a ironia de lado: seja atencioso, acolhedor e prático. "
            "Reconheça o cansaço e sugira uma pausa com naturalidade, sem sermão."
        ),
        "exemplo": "Lamento ouvir isso, Senhor. Recomendo descansar um pouco.",
    },
    "empolgado": {
        "tom": "empolgado",
        "gatilhos": "consegui, terminei, ganhei, passei, aprovado, funcionou, deu certo, recorde",
        "diretrizes": (
            "Comemore junto — sem exagero, mas com orgulho honesto pelo Comandante."
        ),
        "exemplo": "Excelente, Comandante. Sabia que ia conseguir.",
    },
    "neutro": {
        "tom": "habitual",
        "gatilhos": "",
        "diretrizes": (
            "Tom habitual: elegante, britânico e irônico na medida certa — sem forçar nenhum modo."
        ),
        "exemplo": "Às ordens, Comandante.",
    },
}


# ordem de precedência: quem precisa de cuidado vem antes de qualquer outro modo
CONTEXT_PRIORITY = ("preocupado", "empolgado", "trabalho", "descontraido")
CONTEXT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "preocupado": (
        "cansado", "cansada", "exausto", "exausta", "triste", "tristeza", "doente", "dor",
        "estressado", "estressada", "ansioso", "ansiosa", "desanimado", "desanimada",
        "deprimido", "deprimida", "sem forças", "sem forcas", "não durmo", "preocupado",
        "acabado", "esgotado", "mal hoje",
    ),
    "empolgado": (
        "consegui", "conseguimos", "terminei", "acabei de terminar", "ganhei", "ganhamos",
        "passei", "aprovado", "aprovada", "funcionou", "deu certo", "quebrei meu recorde",
        "recorde", "finalmente", "vencemos", "fechei o projeto", "entreguei",
    ),
    "trabalho": (
        "programando", "programar", "código", "codigo", "codar", "estudando", "estudar",
        "projeto", "trabalho", "trabalhando", "reunião", "reuniao", "prazo", "deploy",
        "bug", "arquitetura", "prova", "faculdade", "relatório", "relatorio", "cliente",
        "commit", "refatorar", "deadline", "virar a noite",
    ),
    "descontraido": (
        "jogando", "jogar", "jogo", "partida", "fortnite", "valorant", "cs2", "lol",
        "amigos", "filme", "série", "serie", "futebol", "churrasco", "cerveja", "relaxar",
        "relaxando", "descansar", "piada", "zoando", "netflix",
    ),
}


def _part_of_day(hour: int) -> str:
    if 5 <= hour < 12:
        return "manhã"
    if 12 <= hour < 18:
        return "tarde"
    if 18 <= hour < 24:
        return "noite"
    return "madrugada"


def detect_context(text: str, now: datetime | None = None) -> dict[str, str]:
    """Classifica o momento: modo, tom, horário e as diretrizes de tom."""
    when = now or datetime.now()
    low = " " + str(text or "").lower() + " "
    mode = "neutro"
    for candidate in CONTEXT_PRIORITY:
        if any(k in low for k in CONTEXT_KEYWORDS[candidate]):
            mode = candidate
            break
    part = _part_of_day(when.hour)
    spec = CONTEXT_MODES.get(mode) or CONTEXT_MODES["neutro"]
    return {
        "mode": mode,
        "tom": spec["tom"],
        "horario": part,
        "hora": when.strftime("%H:%M"),
        "diretrizes": spec["diretrizes"],
        "exemplo": spec["exemplo"],
    }


def build_context_block(text: str, now: datetime | None = None) -> str:
    """Bloco CONTEXTO ATUAL injetado no prompt (antes do LLM)."""
    ctx = detect_context(text, now)
    linhas = [
        "CONTEXTO ATUAL:",
        f"- Horário: {ctx['horario']} ({ctx['hora']})",
        f"- Tom sugerido: {ctx['tom']}",
        "- Diretrizes de tom:",
        f"  * {ctx['diretrizes']}",
        f"  * Exemplo para este modo: \"{ctx['exemplo']}\"",
    ]
    if ctx["horario"] == "madrugada":
        linhas.append(
            "  * São horas da madrugada: se ele estiver trabalhando, sugira uma pausa "
            "(com humor seco, sem sermão)."
        )
    linhas.append("  * O tom muda o jeito de falar, nunca os fatos nem as memórias acima.")
    return "\n".join(linhas)


def run_tool(tool: dict[str, Any]) -> dict[str, Any]:
    name = tool["name"]
    args = tool.get("args") or {}

    if name == "exec":
        r = _backend("POST", "/exec", {"cmd": args.get("cmd", "")}, timeout=40)
        if r is None:
            return {"name": name, "ok": False, "summary": "backend local (porta 8000) fora do ar", "detail": None}
        return {
            "name": name,
            "ok": not r.get("error"),
            "summary": (f"erro: {r.get('error')}" if r.get("error") else f"ok: {(r.get('output') or '(sem saída)')[:160]}"),
            "detail": r,
        }

    if name == "stocks":
        r = _backend("GET", f"/stocks?symbols={requests.utils.quote(args.get('symbols', ''))}", timeout=25)
        if r is None:
            return {"name": name, "ok": False, "summary": "backend fora do ar", "detail": None}
        parts = []
        for s in r.get("results", []):
            if s.get("error"):
                parts.append(f"{s.get('symbol')}: indisponível")
            else:
                sign = "+" if (s.get("change_percent") or 0) > 0 else ""
                parts.append(f"{s.get('symbol')}: {s.get('price')} {s.get('currency')} ({sign}{s.get('change_percent')}%)")
        return {"name": name, "ok": bool(r.get("results")), "summary": " | ".join(parts) or "sem resultados", "detail": r}

    if name == "currencies":
        r = _backend("GET", "/currencies", timeout=25)
        if r is None or not r.get("rates"):
            return {"name": name, "ok": False, "summary": "backend fora do ar", "detail": None}
        parts = [f"{x['pair']}: {x['bid']:.2f} ({x['change_percent']:+.3f}%)" for x in r["rates"]]
        return {"name": name, "ok": True, "summary": " | ".join(parts), "detail": r}

    if name == "sysinfo":
        r = _backend("GET", "/sysinfo", timeout=15)
        if r is None or "cpu" not in r:
            return {"name": name, "ok": False, "summary": "backend fora do ar", "detail": None}
        summary = (
            f"CPU {r['cpu']['percent']}% · RAM {r['ram']['percent']}% ({r['ram']['used_gb']}/{r['ram']['total_gb']} GB)"
            f" · Disco {r['disk']['percent']}% ({r['disk']['used_gb']}/{r['disk']['total_gb']} GB)"
        )
        return {"name": name, "ok": True, "summary": summary, "detail": r}

    if name == "read-file":
        r = _backend("POST", "/read-file", {"path": args.get("path", "")}, timeout=15)
        if r is None:
            return {"name": name, "ok": False, "summary": "backend fora do ar", "detail": None}
        if r.get("error"):
            return {"name": name, "ok": False, "summary": f"erro: {r['error']}", "detail": r}
        return {
            "name": name,
            "ok": True,
            "summary": f"{r.get('path')} ({r.get('size')} bytes)",
            "detail": {**r, "content": str(r.get("content", ""))[:1200]},
        }

    if name == "power":
        action = str(args.get("action", "shutdown"))
        delay = int(args.get("delay", 30) or 30)
        if not args.get("confirmed"):
            # segurança: nada de desligar sem um "sim" explícito do Comandante
            _set_pending_power(action, delay)
            return {
                "name": name,
                "ok": True,
                "summary": (
                    f"AGUARDANDO CONFIRMAÇÃO para {action} em {delay}s — NADA foi executado. "
                    'Pergunte ao Comandante se pode prosseguir e só execute depois do "sim".'
                ),
                "detail": {"pending_confirmation": True, "action": action, "delay": delay},
            }
        r = _backend(
            "POST",
            "/power",
            {"action": action, "delay": delay, "confirmed": True, "dry_run": _power_dry_run()},
            timeout=30,
        )
        if r is None:
            return {"name": name, "ok": False, "summary": "backend local (porta 8000) fora do ar", "detail": None}
        if r.get("error"):
            return {"name": name, "ok": False, "summary": f"erro: {r['error']}", "detail": r}
        if r.get("dry_run"):
            return {
                "name": name,
                "ok": True,
                "summary": f"MODO SIMULAÇÃO (JARVIS_POWER_DRY_RUN=1): {action} NÃO foi executado",
                "detail": r,
            }
        delay_out = int(r.get("delay") or 0)
        summary = (
            f"{r.get('action')} agendado em {delay_out}s (cancele com 'cancela o desligamento')"
            if delay_out
            else f"{r.get('action')} executado"
        )
        return {"name": name, "ok": bool(r.get("ok")), "summary": summary, "detail": r}

    if name == "power-cancel":
        r = _backend("POST", "/power/cancel", {}, timeout=20)
        if r is None:
            return {"name": name, "ok": False, "summary": "backend local (porta 8000) fora do ar", "detail": None}
        ok = bool(r.get("ok"))
        detail = r.get("output") or r.get("error") or ""
        return {
            "name": name,
            "ok": ok,
            "summary": "desligamento cancelado" if ok else f"nada a cancelar: {detail}",
            "detail": r,
        }

    if name == "kill":
        target = str(args.get("name", "")).strip()
        mapped = APP_MAP.get(target.lower())
        if mapped:  # "bloco de notas" → notepad, "chrome" → chrome...
            last = mapped.replace("\\", "/").split("/")[-1].split()[-1]
            target = last[:-4] if last.lower().endswith(".exe") else last
        r = _backend(
            "POST",
            "/kill",
            {"name": target, "force": bool(args.get("force", True))},
            timeout=40,
        )
        if r is None:
            return {"name": name, "ok": False, "summary": "backend local (porta 8000) fora do ar", "detail": None}
        ok = bool(r.get("ok"))
        summary = (
            f"{r.get('name')} encerrado"
            if ok
            else f"não encerrei {r.get('name')}: {str(r.get('output') or '')[:120]}"
        )
        return {"name": name, "ok": ok, "summary": summary, "detail": r}

    if name == "processes":
        r = _backend("GET", "/processes?limit=10", timeout=25)
        if r is None or "processes" not in r:
            return {"name": name, "ok": False, "summary": "backend local (porta 8000) fora do ar", "detail": None}
        parts = [f"{p['name']} ({p['ram_mb']} MB)" for p in r["processes"][:10]]
        return {"name": name, "ok": True, "summary": " | ".join(parts) or "sem dados", "detail": r}

    if name == "news":
        source = str(args.get("source") or "g1").strip().lower()
        if source not in BR_NEWS_SOURCES:
            source = "g1"
        topic = str(args.get("topic") or "geral").strip().lower()
        if topic not in BR_NEWS_TOPICS.get(source, ("geral",)):
            topic = "geral"
        limit = max(1, min(int(args.get("limit", 5) or 5), 10))
        r = _backend(
            "GET",
            f"/news/brasil?source={_urlquote(source)}&topic={_urlquote(topic)}&limit={limit}",
            timeout=30,
        )
        if r is None or not r.get("ok"):
            # reserva: o /news antigo (G1/Google News) mantém as notícias de pé
            legacy = _backend("GET", f"/news?topic={_urlquote(topic)}&limit={limit}", timeout=30)
            if legacy is not None and not legacy.get("error"):
                legacy["ok"] = True
                r = legacy
            else:
                erro = (r or {}).get("error") or "backend local (porta 8000) fora do ar"
                return {"name": name, "ok": False, "summary": f"erro: {erro}", "detail": r}
        # títulos já vêm limpos do backend (titulo/resumo, sem HTML): o modelo só sumariza
        parts = [_news_line(i) for i in (r.get("items") or [])]
        parts = [p for p in parts if p]
        return {"name": name, "ok": bool(parts), "summary": " • ".join(parts) or "sem notícias", "detail": r}

    if name == "weather":
        r = _backend("GET", "/weather", timeout=25)
        if r is None:
            return {"name": name, "ok": False, "summary": "backend local (porta 8000) fora do ar", "detail": None}
        if not r.get("ok"):
            return {"name": name, "ok": False, "summary": f"erro: {r.get('error') or 'sem dados do clima'}", "detail": r}
        # frase pronta no estilo JARVIS: é o que vai para a voz (e para o modo sem Groq)
        return {"name": name, "ok": True, "summary": _weather_sentence(r), "detail": r}

    if name == "agenda-add":
        if not str(args.get("datetime") or "").strip():
            return {
                "name": name,
                "ok": False,
                "summary": "informe a data e a hora do lembrete (ex.: 'amanhã às 15h')",
                "detail": None,
            }
        r = _backend(
            "POST",
            "/agenda/add",
            {
                "title": args.get("title", ""),
                "datetime": args.get("datetime", ""),
                "description": args.get("description", ""),
            },
            timeout=20,
        )
        if r is None:
            return {"name": name, "ok": False, "summary": "backend local (porta 8000) fora do ar", "detail": None}
        if r.get("error"):
            return {"name": name, "ok": False, "summary": f"erro: {r['error']}", "detail": r}
        ev = r.get("event", {})
        return {
            "name": name,
            "ok": True,
            "summary": f"lembrete '{ev.get('title')}' para {ev.get('datetime')}",
            "detail": r,
        }

    if name == "agenda-list":
        r = _backend("GET", "/agenda/list", timeout=20)
        if r is None or "events" not in r:
            return {"name": name, "ok": False, "summary": "backend local (porta 8000) fora do ar", "detail": None}
        evs = r["events"]
        if not evs:
            return {"name": name, "ok": True, "summary": "agenda vazia — nenhum evento futuro", "detail": r}
        parts = [f"{e.get('datetime')}: {e.get('title')}" for e in evs[:10]]
        return {"name": name, "ok": True, "summary": " | ".join(parts), "detail": r}

    if name == "agenda-check":
        r = _backend("POST", f"/agenda/check?window={int(args.get('window', 5) or 5)}", {}, timeout=20)
        if r is None or "events" not in r:
            return {"name": name, "ok": False, "summary": "backend local (porta 8000) fora do ar", "detail": None}
        evs = r["events"]
        if not evs:
            return {"name": name, "ok": True, "summary": "nenhum lembrete nos próximos minutos", "detail": r}
        parts = [f"{e.get('title')} em {e.get('in_minutes')} min" for e in evs]
        return {"name": name, "ok": True, "summary": " | ".join(parts), "detail": r}

    if name == "agenda-delete":
        r = _backend("DELETE", f"/agenda/{_urlquote(str(args.get('id', '')))}", timeout=20)
        if r is None:
            return {"name": name, "ok": False, "summary": "backend local (porta 8000) fora do ar", "detail": None}
        if r.get("error"):
            return {"name": name, "ok": False, "summary": f"erro: {r['error']}", "detail": r}
        return {"name": name, "ok": True, "summary": f"evento removido ({r.get('removed')})", "detail": r}

    return {"name": name, "ok": False, "summary": "ferramenta desconhecida", "detail": None}


# ── agent: tool calling de verdade (o modelo decide quando chamar) ──────
MAX_TOOL_ROUNDS = 5

TOOLS_SCHEMA: list[dict[str, Any]] = [
    {"type": "function", "function": {"name": "exec", "description": "Executa um comando no Windows (shell).", "parameters": {"type": "object", "properties": {"cmd": {"type": "string", "description": "comando, ex.: start chrome"}}, "required": ["cmd"]}}},
    {"type": "function", "function": {"name": "read_file", "description": "Lê o conteúdo de um arquivo local.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "sysinfo", "description": "CPU, RAM, disco e uptime reais da máquina.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "list_processes", "description": "Lista os processos que mais consomem memória.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "kill", "description": "Encerra um programa pelo nome (ex.: chrome).", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "force": {"type": "boolean"}}, "required": ["name"]}}},
    {"type": "function", "function": {"name": "power", "description": "Desliga, reinicia, hiberna ou suspende o computador. A execução SEMPRE exige confirmação do usuário.", "parameters": {"type": "object", "properties": {"action": {"type": "string", "enum": ["shutdown", "restart", "hibernate", "sleep"]}, "delay": {"type": "integer"}}, "required": ["action"]}}},
    {"type": "function", "function": {"name": "power_cancel", "description": "Cancela um desligamento/reinício agendado.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "news", "description": "Últimas notícias (RSS do G1 ou Google News).", "parameters": {"type": "object", "properties": {"topic": {"type": "string"}, "limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "agenda_add", "description": "Cria um lembrete na agenda.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "datetime": {"type": "string", "description": "AAAA-MM-DD HH:MM"}, "description": {"type": "string"}}, "required": ["title", "datetime"]}}},
    {"type": "function", "function": {"name": "agenda_list", "description": "Lista os eventos futuros da agenda.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "agenda_delete", "description": "Remove um evento da agenda pelo id ou pelo título.", "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}}},
    {"type": "function", "function": {"name": "agenda_check", "description": "Eventos que começam nos próximos minutos.", "parameters": {"type": "object", "properties": {"window": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "stocks", "description": "Cotação de ações (PETR4, AAPL...).", "parameters": {"type": "object", "properties": {"symbols": {"type": "string", "description": "separados por vírgula"}}, "required": ["symbols"]}}},
    {"type": "function", "function": {"name": "currencies", "description": "Cotações de moedas (USD/BRL, EUR/BRL, USD/EUR).", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "weather", "description": "Clima atual e previsão de hoje para São João do Paraíso - MG (dados reais do wttr.in/open-meteo).", "parameters": {"type": "object", "properties": {}}}},
]

TOOL_ALIASES = {
    "exec": "exec", "read_file": "read-file", "sysinfo": "sysinfo", "list_processes": "processes",
    "kill": "kill", "power": "power", "power_cancel": "power-cancel", "news": "news",
    "agenda_add": "agenda-add", "agenda_list": "agenda-list", "agenda_delete": "agenda-delete",
    "agenda_check": "agenda-check", "stocks": "stocks", "currencies": "currencies",
    "weather": "weather",
}

# desligar/reiniciar/hibernar/suspender só acontece depois de um "sim" explícito
_pending_power: dict[str, Any] | None = None
AFFIRM_RE = re.compile(r"\b(sim|confirmo|confirmado|pode|manda|autorizo|ok|certo|claro|isso|positivo|prossiga|prossegue|vai)\b", re.I)
DENY_RE = re.compile(r"\b(n[ãa]o|cancela|cancelar|aborta|abortar|esquece|esquecer)\b", re.I)


def _power_dry_run() -> bool:
    """JARVIS_POWER_DRY_RUN=1 → percorre toda a cadeia de desligamento SEM desligar a máquina."""
    return os.environ.get("JARVIS_POWER_DRY_RUN") == "1"


# tempo máximo para o Comandante confirmar um desligamento (evita "sim" tardio e acidental)
POWER_CONFIRM_TTL = 120  # segundos


def _set_pending_power(action: str, delay: int) -> None:
    global _pending_power
    _pending_power = {"action": action, "delay": delay, "at": datetime.now()}


def _take_power_confirmation(messages: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Devolve os args do desligamento pendente quando o Comandante confirma."""
    global _pending_power
    if not _pending_power:
        return None
    if (datetime.now() - _pending_power["at"]).total_seconds() > POWER_CONFIRM_TTL:
        security_log("power", f"pedido expirado sem confirmação ({_pending_power.get('action')})")
        _pending_power = None  # pedido expirado: exigimos uma nova ordem explícita
        return None
    text = ""
    for m in reversed(messages):
        if (m.get("role") or "") == "user":
            text = str(m.get("content") or "")
            break
    if DENY_RE.search(text):
        security_log("power", f"pedido CANCELADO pelo Comandante ({_pending_power.get('action')})")
        _pending_power = None
        return None
    if AFFIRM_RE.search(text):
        args = dict(_pending_power)
        args.pop("at", None)
        args["confirmed"] = True
        security_log("power", f"pedido CONFIRMADO pelo Comandante ({args.get('action')})")
        _pending_power = None
        return args
    return None


def _result_is_empty(tool: dict[str, Any], result: dict[str, Any]) -> bool:
    """A ferramenta rodou mas não trouxe nada? (evita o modelo preencher com suposição)"""
    detail = result.get("detail") or {}
    checks = {
        "agenda-list": ("events", "a agenda está vazia — nenhum evento cadastrado"),
        "agenda-check": ("events", "nenhum lembrete nos próximos minutos"),
        "news": ("items", "nenhuma notícia foi retornada"),
        "processes": ("processes", "nenhum processo foi retornado"),
        "stocks": ("results", "nenhuma cotação foi retornada"),
        "agenda-delete": ("removed", "nenhum evento foi removido"),
    }
    key, _msg = checks.get(tool["name"], (None, None))
    if key is None:
        return False
    return not detail.get(key)


def _empty_hint(tool: dict[str, Any]) -> str:
    return {
        "agenda-list": "a agenda está vazia — nenhum evento cadastrado",
        "agenda-check": "não há lembretes nos próximos minutos",
        "news": "nenhuma notícia foi retornada",
        "processes": "nenhum processo foi retornado",
        "stocks": "nenhuma cotação foi retornada",
        "agenda-delete": "nenhum evento foi removido",
    }.get(tool["name"], "a ferramenta não retornou dados")


def tool_context(tool: dict[str, Any], result: dict[str, Any]) -> str:
    payload = json.dumps(result.get("detail") or {"summary": result.get("summary")}, ensure_ascii=False)[:4000]
    head = f"[RESULTADO DA FERRAMENTA \"{tool['name']}\" — DADOS REAIS, ÚNICA FONTE VÁLIDA]\n{payload}\n"
    if _result_is_empty(tool, result):
        head += (
            f"[RESULTADO VAZIO] {_empty_hint(tool)}. NÃO invente nada: diga que não há nada registrado "
            "ou que não há esse dado no momento.\n"
        )
    if isinstance(result.get("detail"), dict) and result["detail"].get("pending_confirmation"):
        head += (
            "[NÃO EXECUTADO] Nada foi executado: a ação está apenas aguardando confirmação. "
            "NUNCA diga que o desligamento foi agendado, programado ou iniciado. "
            'Diga que nada foi executado e pergunte se o Comandante confirma — só o "sim" executa.\n'
        )
    return (
        head
        + "REGRAS: use APENAS os dados acima. Não invente números, eventos, cotações nem status. "
        "Se o resultado estiver vazio ou ausente, diga que não há nada registrado — nunca preencha com suposições. "
        "Responda em português, curto, no estilo JARVIS."
    )


# ── visualizador 3D (intenção detectada aqui, sem depender do modelo) ──
VIS3D_VERB_RE = re.compile(
    r"\b(me\s+mostra|mostra|visualiza|visualizar|renderiza|renderizar|desenha|desenhar)\b",
    re.IGNORECASE,
)
VIS3D_MARK_RE = re.compile(
    r"\b(?:em\s+)?(?:3d|3-d)\b|\b(?:em\s+)?tr[êe]s\s+dimens[õo]es\b",
    re.IGNORECASE,
)
VIS3D_BLOCK_RE = re.compile(
    r"\b(not[íi]cias?|manchetes?|agendas?|lembretes?|cota[çc][õo]es?|a[çc][õo]es?|d[óo]lar|euro|processos?|"
    r"cpu|mem[óo]rias?|discos?|sistemas?|climas?|previs[ãa]o|horas?|datas?|arquivos?|pastas?|imagens?|fotos?)\b",
    re.IGNORECASE,
)
_VIS3D_STOP = {"isso", "isto", "ele", "ela", "aquilo", "um", "uma", "o", "a"}


def detect_visualize_3d(text: str) -> str | None:
    """"me mostra um carro" / "visualiza uma casa em 3D" → devolve o objeto pedido.
    Devolve None quando o pedido é de outra coisa (notícias, agenda, sistema…)."""
    t = " ".join(str(text or "").split())
    if not t or VIS3D_BLOCK_RE.search(t):
        return None
    if not VIS3D_VERB_RE.search(t):
        return None
    obj = re.sub(r"^\s*(j[aá]rvis)[\s,:.!-]*", "", t, flags=re.IGNORECASE)
    obj = re.sub(r"^\s*(por\s+favor[\s,]*)?", "", obj, flags=re.IGNORECASE)
    obj = VIS3D_VERB_RE.sub(" ", obj, count=1)
    obj = VIS3D_MARK_RE.sub(" ", obj)
    obj = re.sub(r"^\s*(?:o|a|os|as|um|uma|uns|umas|de|do|da)\s+", "", obj, flags=re.IGNORECASE)
    obj = re.sub(r"\s+", " ", obj).strip(" .,!?:;-—")
    if not (2 <= len(obj) <= 60) or obj.lower() in _VIS3D_STOP:
        return None
    return obj


# ── modo programador: "Jarvis, cria um site de portfólio" ─────────────
GENCODE_VERB_RE = re.compile(
    r"\b(me\s+)?(cria|crie|criar|programa|programe|programar|faz|fa[çc]a|fazer|gera|gere|gerar|"
    r"escreve|escreva|escrever|desenvolve|desenvolva|desenvolver|monta|monte|montar|"
    r"c[óo]difica|codificar|constr[óo]i|construir)\b",
    re.IGNORECASE,
)
GENCODE_TECH_RE = re.compile(
    r"\b(site|p[áa]gina|pagina|web|html|css|javascript|js|python|script|app|aplicativo|programa|"
    r"software|landing|portf[óo]lio|portfolio|blog|curr[íi]culo|curriculo|dashboard|formul[áa]rio|formulario|"
    r"jogo|game|api|bot|automa[çc][ãa]o|automacao|c[óo]digo|codigo|arquivo|tela|loja|card[áa]pio|cardapio)\b",
    re.IGNORECASE,
)
# pedidos que são de OUTRA ferramenta (notícias, agenda, clima, energia, sistema)
GENCODE_BLOCK_RE = re.compile(
    r"\b(not[íi]cias?|manchetes?|agendas?|lembretes?|climas?|previs[ãa]o|cota[çc][õo]es?|processos?|"
    r"cpu|mem[óo]rias?|discos?|sistemas?|desliga|desligar|reinicia|reiniciar|beacon|\d\s*%)\b",
    re.IGNORECASE,
)


def detect_generate_code(text: str) -> str | None:
    """"Jarvis, me cria um site de portfólio" → devolve o pedido ("site de portfólio").
    Exige verbo de criação + substantivo técnico; devolve None para o resto."""
    t = " ".join(str(text or "").split())
    if not t or len(t) > 200 or t.startswith(("!", "/")):
        return None
    if GENCODE_BLOCK_RE.search(t):
        return None
    if not (GENCODE_VERB_RE.search(t) and GENCODE_TECH_RE.search(t)):
        return None
    obj = re.sub(r"^\s*(j[aá]rvis)[\s,:.!-]*", "", t, flags=re.IGNORECASE)
    obj = re.sub(r"^\s*(por\s+favor[\s,]*)?", "", obj, flags=re.IGNORECASE)
    obj = GENCODE_VERB_RE.sub(" ", obj, count=1)
    obj = re.sub(r"^\s*(?:o|a|os|as|um|uma|uns|umas|de|do|da)\s+", "", obj, flags=re.IGNORECASE)
    obj = re.sub(r"^\s*(?:o|a|os|as|um|uma|uns|umas)\s+", "", obj, flags=re.IGNORECASE)
    obj = re.sub(r"\s+", " ", obj).strip(" .,!?:;-—")
    if not (2 <= len(obj) <= 200):
        return None
    return obj


def sse(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ── /api/chat (SSE) ─────────────────────────────────────────────────────
@app.post("/api/chat")
async def api_chat(request: Request) -> StreamingResponse:
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "json inválido"}, status_code=400)

    # rate limit: no máximo 30 chamadas por minuto (janela deslizante)
    if chat_rate_limited():
        security_log("chat", f"rate limit excedido ({CHAT_RATE_MAX}/{CHAT_RATE_WINDOW}s)", blocked=True)
        return JSONResponse({"error": "Muitas chamadas seguidas, Comandante. Aguarde um instante."}, status_code=429)

    # tamanho máximo da mensagem do usuário (evita payload gigante)
    for _m in payload.get("messages") or []:
        if len(str(_m.get("content") or "")) > CHAT_MAX_INPUT_CHARS:
            security_log("chat", f"mensagem acima de {CHAT_MAX_INPUT_CHARS} caracteres", blocked=True)
            return JSONResponse(
                {"error": f"Mensagem muito longa (máximo {CHAT_MAX_INPUT_CHARS} caracteres)."},
                status_code=413,
            )

    messages = [m for m in (payload.get("messages") or []) if (m.get("role") or "") != "system"][-30:]
    # o prompt de personalidade é sempre o nosso (ignora o que o front mandar)
    messages = [{"role": "system", "content": SYSTEM_PROMPT_FULL}] + messages
    cfg = load_config()

    # 1) confirmação pendente de desligamento/reinício (segurança)
    confirmed = _take_power_confirmation(messages)
    confirmed_result = None
    if confirmed:
        confirmed_result = run_tool({"name": "power", "args": confirmed})
        messages.append({"role": "system", "content": tool_context({"name": "power"}, confirmed_result)})

    # 2) desligar/reiniciar/cancelar não dependem do humor do modelo: detectamos a
    #    intenção aqui e já registramos o pedido (a ferramenta power NUNCA executa
    #    sem um "sim" do Comandante). Evita o modelo PROMETER uma ação que não fez.
    last_user = next((m for m in reversed(messages) if (m.get("role") or "") == "user"), None)
    user_text = str(last_user.get("content") or "") if last_user else ""
    pre_tools: list[tuple[dict[str, Any], dict[str, Any]]] = []
    power_done = confirmed_result is not None  # já executou nesta ordem: não rearmar
    if cfg["groqKey"] and not confirmed:
        critical = detect_tool(user_text)
        if critical and critical["name"] in ("power", "power-cancel"):
            cresult = run_tool(critical)
            pre_tools.append((critical, cresult))
            messages.append({"role": "system", "content": tool_context(critical, cresult)})

    # 2b) visualizador 3D: "Jarvis, me mostra um carro" → abre o navegador e responde
    #     com uma frase fixa (não passa pelo modelo, não abre o chat)
    if not confirmed:
        vis_obj = detect_visualize_3d(user_text)
        if vis_obj:
            vis = _backend("POST", "/visualize-3d", {"prompt": vis_obj}, timeout=150)
            vis_ok = bool((vis or {}).get("ok"))
            if vis_ok:
                vis_msg = str((vis or {}).get("message") or f"Pronto, Comandante. Abrindo o {vis_obj} no navegador.")
                vis_summary = f"{vis_obj} ({int((vis or {}).get('size') or 0)} bytes)"
            else:
                vis_msg = (
                    "Não consegui abrir a visualização 3D, Comandante. "
                    + str((vis or {}).get("error") or "o backend de ferramentas não respondeu.")
                )
                vis_summary = f"{vis_obj} — falhou"

            async def vis_stream() -> AsyncIterator[str]:
                yield sse("tool", {"name": "visualize-3d", "ok": vis_ok, "summary": vis_summary})
                yield sse("start", {"provider": "jarvis-3d", "model": "visualize-3d"})
                for i in range(0, len(vis_msg), 28):
                    yield sse("delta", {"t": vis_msg[i: i + 28]})
                yield sse("done", {"provider": "jarvis-3d", "model": "visualize-3d"})

            return StreamingResponse(vis_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    # 2b2) modo programador: a Groq gera o código, o arquivo abre no navegador/editor
    #      e a resposta é uma frase fixa (não passa pelo modelo, não gasta token)
    if not confirmed:
        code_req = detect_generate_code(user_text)
        if code_req:
            gen = _backend("POST", "/generate-code", {"prompt": code_req}, timeout=180)
            gen_ok = bool((gen or {}).get("ok"))
            if gen_ok:
                gen_msg = str(
                    (gen or {}).get("message")
                    or "Pronto, Comandante. Gerei o código e abri no seu editor."
                )
                gen_summary = (
                    f"{code_req} · .{str((gen or {}).get('language') or 'txt')} "
                    f"({int((gen or {}).get('size') or 0)} bytes)"
                )
            else:
                gen_msg = (
                    "Não consegui gerar o código, Comandante. "
                    + str((gen or {}).get("error") or "o backend de ferramentas não respondeu.")
                )
                gen_summary = f"{code_req} — falhou"

            async def code_stream() -> AsyncIterator[str]:
                yield sse("tool", {"name": "generate-code", "ok": gen_ok, "summary": gen_summary})
                yield sse("start", {"provider": "jarvis-code", "model": "generate-code"})
                for i in range(0, len(gen_msg), 28):
                    yield sse("delta", {"t": gen_msg[i: i + 28]})
                yield sse("done", {"provider": "jarvis-code", "model": "generate-code"})

            return StreamingResponse(code_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})

    # 2c) clima: "como tá o tempo?" → injeta os dados REAIS do clima no prompt
    #     (a ferramenta roda aqui, sem depender do modelo lembrar de chamá-la)
    if not confirmed and detect_weather(user_text):
        weather_result = run_tool({"name": "weather", "args": {}})
        pre_tools.append(({"name": "weather"}, weather_result))
        if weather_result["ok"]:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "DADOS REAIS DO CLIMA: "
                        + json.dumps(weather_result.get("detail") or {}, ensure_ascii=False)
                        + ". Responda com base nisso e cite o horário de 'medido_em' "
                        "no fim (ex.: \"(Dados de 09:30.)\")."
                    ),
                }
            )
        else:
            messages.append(
                {
                    "role": "system",
                    "content": (
                        "DADOS REAIS DO CLIMA: indisponível agora "
                        f"({weather_result['summary']}). Diga ao Comandante que não conseguiu obter "
                        "a previsão neste momento — NÃO invente temperatura nem previsão."
                    ),
                }
            )

    # 2c-1) saudação: "bom dia" → clima real + 3 notícias do G1 injetados no prompt
    #       ("boa tarde" = mesmo fluxo, "boa noite" = só clima, "boa madrugada" = só saudação)
    greeting_period = detect_greeting(user_text) if (not confirmed and user_text.strip()) else None
    greeting_brief = ""          # resposta pronta (usada quando não há chave da Groq)
    if greeting_period:
        spec = GREETINGS.get(greeting_period) or GREETINGS["manha"]
        clima = noticias = None
        if spec["clima"]:
            wres = run_tool({"name": "weather", "args": {}})
            pre_tools.append(({"name": "weather"}, wres))
            clima = wres.get("detail") if wres["ok"] else None
        if spec["noticias"]:
            nres = run_tool({"name": "news", "args": {"source": "g1", "topic": "geral", "limit": 3}})
            pre_tools.append(({"name": "news"}, nres))
            noticias = (nres.get("detail") or {}).get("items") if nres["ok"] else None
        messages.append({"role": "system", "content": greeting_context(greeting_period, clima, noticias)})
        # briefing determinístico (sem LLM): saudação + clima + manchetes
        pedacos = [f"{spec['saudacao']}, Comandante."]
        if spec["clima"]:
            # a saudação já disse "Comandante": evita repetir no meio da frase
            frase = re.sub(r"^Comandante,\s*", "", _weather_sentence(clima))
            pedacos.append(frase[:1].upper() + frase[1:] if frase else frase)
        if spec["noticias"]:
            titulos = [t for t in (_news_line(i).split(" — ")[0] for i in (noticias or [])) if t]
            if titulos:
                pedacos.append("As principais notícias de hoje: " + " ".join(f"{t}." for t in titulos[:3]))
        greeting_brief = " ".join(pedacos)

    # 2c-2) notícias: "notícias de hoje", "g1", "the news" → títulos REAIS no prompt
    elif not confirmed and user_text.strip():
        news_args = detect_br_news(user_text)
        if news_args:
            nres = run_tool({"name": "news", "args": news_args})
            pre_tools.append(({"name": "news"}, nres))
            items = (nres.get("detail") or {}).get("items") if nres["ok"] else None
            if items:
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "DADOS REAIS DE NOTÍCIAS ("
                            f"{news_args['source']}/{news_args['topic']}): "
                            + json.dumps(items[:3], ensure_ascii=False)
                            + ". Resuma as 3 principais em 2-3 frases naturais, como um âncora de jornal — "
                            "sem URLs, sem nome de veículo e sem data."
                        ),
                    }
                )
            else:
                messages.append(
                    {
                        "role": "system",
                        "content": (
                            "DADOS REAIS DE NOTÍCIAS: indisponível agora "
                            f"({nres['summary']}). Diga ao Comandante que não conseguiu obter as "
                            "notícias neste momento — NÃO invente manchetes."
                        ),
                    }
                )

    # 2d) memória persistente: injeta o que o JARVIS já sabe do Comandante e salva
    #     a mensagem atual como memória (source="chat"; só acima de 20 caracteres)
    # 2d-0) contexto dinâmico: horário + tom do pedido (trabalho/descontraído/preocupado/empolgado)
    if user_text.strip():
        messages.append({"role": "system", "content": build_context_block(user_text)})

    memories = _memory_search(user_text) if user_text.strip() else []
    if memories:
        linhas = "\n".join(f"- {m.get('text')}" for m in memories[:5])
        messages.append(
            {
                "role": "system",
                "content": "MEMÓRIAS SOBRE O COMANDANTE:\n" + f"{linhas}\n\n" + MEMORY_PERSONALITY_GUIDE,
            }
        )
    _memory_save(user_text, "chat")

    # 3) sem chave da Groq: caminho local (regex + ferramenta) devolve o resultado cru
    local_tool = None
    local_result = None
    if not cfg["groqKey"]:
        local_tool = detect_tool(user_text)
        if local_tool:
            local_result = run_tool(local_tool)

    async def stream() -> AsyncIterator[str]:
        if confirmed_result:
            yield sse("tool", {"name": "power", "ok": confirmed_result["ok"], "summary": confirmed_result["summary"]})
        for _tool, _res in pre_tools:
            yield sse("tool", {"name": _res["name"], "ok": _res["ok"], "summary": _res["summary"]})

        if not cfg["groqKey"]:
            if greeting_brief:      # "bom dia" sem Groq: briefing local, sem inventar nada
                yield sse("start", {"provider": "local-tools", "model": "briefing"})
                for i in range(0, len(greeting_brief), 28):
                    yield sse("delta", {"t": greeting_brief[i : i + 28]})
                yield sse("done", {"provider": "local-tools", "model": "briefing"})
                return
            if local_tool and local_result:
                if local_result["name"] == "weather" and local_result["ok"]:
                    # o clima já vem como frase pronta no estilo JARVIS (resposta por voz)
                    text = str(local_result["summary"])
                else:
                    text = (
                        f"✔ {local_result['name']}: {local_result['summary']}"
                        if local_result["ok"]
                        else f"⚠ {local_result['name']}: {local_result['summary']}"
                    )
                yield sse("start", {"provider": "local-tools", "model": f"backend:{local_result['name']}"})
                for i in range(0, len(text), 28):
                    yield sse("delta", {"t": text[i : i + 28]})
                yield sse("done", {"provider": "local-tools", "model": f"backend:{local_result['name']}"})
                return
            yield sse(
                "error",
                {
                    "message": "Nenhuma chave da Groq configurada. Abra as Configurações (engrenagem) e cole sua chave de console.groq.com/keys.",
                    "tried": [],
                },
            )
            yield sse("done", {})
            return

        models = [cfg["groqModel"]] if cfg["groqModel"] else GROQ_MODELS
        errors: list[str] = []
        fatal = False

        # agent loop: o modelo decide as ferramentas, nós executamos, e repetimos (máx. 5)
        for model in models:
            conv: list[dict[str, Any]] = list(messages)
            answered = False
            failed = False
            started = False

            for _round in range(MAX_TOOL_ROUNDS):
                body: dict[str, Any] = {
                    "model": model,
                    "messages": conv,
                    "stream": True,
                    "temperature": payload.get("temperature", 0.7),
                    "tools": TOOLS_SCHEMA,
                    "tool_choice": "auto",
                }
                try:
                    r = requests.post(
                        GROQ_URL,
                        headers={"Authorization": f"Bearer {cfg['groqKey']}", "Content-Type": "application/json"},
                        json=body,
                        stream=True,
                        timeout=(15, 300),
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"{model}: falha de rede ({exc})")
                    failed = True
                    break

                if r.status_code != 200:
                    detail = ""
                    try:
                        detail = r.json().get("error", {}).get("message", "")
                    except Exception:  # noqa: BLE001
                        detail = r.text[:160]
                    errors.append(f"{model}: HTTP {r.status_code} {detail}")
                    failed = True
                    if r.status_code in (401, 403):
                        fatal = True
                    break

                if not started:
                    yield sse("start", {"provider": "groq", "model": model})
                    started = True

                calls: dict[int, dict[str, Any]] = {}
                streamed = ""
                for raw in r.iter_lines():
                    if not raw:
                        continue
                    line = raw.decode("utf-8", errors="ignore").strip()
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        continue
                    try:
                        j = json.loads(data)
                    except Exception:  # noqa: BLE001
                        continue
                    choices = j.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    text = delta.get("content") or delta.get("reasoning_content")
                    if text:
                        # sanitiza (sem tags/scripts) e limita a resposta a 10.000 caracteres
                        text = strip_html(text)
                        room = CHAT_MAX_OUTPUT_CHARS - len(streamed)
                        if room <= 0:
                            text = ""
                        elif len(text) > room:
                            text = text[:room]
                        if text:
                            streamed += text
                            yield sse("delta", {"t": text})
                    for tc in delta.get("tool_calls") or []:
                        idx = int(tc.get("index", 0) or 0)
                        slot = calls.setdefault(idx, {"id": "", "name": "", "arguments": ""})
                        if tc.get("id"):
                            slot["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            slot["name"] = fn["name"]
                        if fn.get("arguments"):
                            slot["arguments"] += fn["arguments"]

                if not calls:
                    answered = True
                    break

                conv.append(
                    {
                        "role": "assistant",
                        "content": streamed or "",
                        "tool_calls": [
                            {
                                "id": c["id"] or f"call_{i}",
                                "type": "function",
                                "function": {"name": c["name"], "arguments": c["arguments"] or "{}"},
                            }
                            for i, c in sorted(calls.items())
                        ],
                    }
                )
                for i, c in sorted(calls.items()):
                    try:
                        args = json.loads(c["arguments"] or "{}")
                    except Exception:  # noqa: BLE001
                        args = {}
                    if not isinstance(args, dict):
                        args = {}
                    # segurança: o modelo NUNCA confirma por conta própria — só o fluxo
                    # de confirmação (um "sim" do Comandante) pode ligar `confirmed`.
                    args.pop("confirmed", None)
                    tool = {"name": TOOL_ALIASES.get(c["name"], c["name"]), "args": args}
                    if tool["name"] == "power" and power_done:
                        # uma ordem = no máximo um desligamento; não rearma o pedido
                        result = {
                            "name": "power",
                            "ok": True,
                            "summary": (
                                "o desligamento já foi registrado nesta mesma ordem — NÃO chame a "
                                "ferramenta de novo; apenas confirme ao Comandante"
                            ),
                            "detail": {"already_registered": True},
                        }
                    else:
                        result = run_tool(tool)
                    yield sse("tool", {"name": result["name"], "ok": result["ok"], "summary": result["summary"]})
                    conv.append(
                        {
                            "role": "tool",
                            "tool_call_id": c["id"] or f"call_{i}",
                            "content": (
                                json.dumps(result.get("detail") or {"summary": result["summary"]}, ensure_ascii=False)[:4000]
                                + (
                                    '\n[NÃO EXECUTADO] nada aconteceu ainda: está aguardando confirmação. Nunca diga que foi agendado. Peça o "sim" ao Comandante.'
                                    if isinstance(result.get("detail"), dict) and result["detail"].get("pending_confirmation")
                                    else ""
                                )
                                + "\nUse APENAS estes dados. Se estiver vazio, diga que não há nada registrado — não invente."
                            ),
                        }
                    )

            if answered:
                yield sse("done", {"provider": "groq", "model": model})
                return
            if failed and not fatal:
                continue  # tenta o próximo modelo
            if failed and fatal:
                break
            # esgotou as rodadas de ferramentas sem resposta final
            yield sse("delta", {"t": " Não consegui concluir com as ferramentas disponíveis, Comandante."})
            yield sse("done", {"provider": "groq", "model": model})
            return

        yield sse("error", {"message": "Groq falhou: " + " | ".join(errors[-2:]), "tried": errors})
        yield sse("done", {})

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})


# ── status / config ─────────────────────────────────────────────────────
@app.get("/api/status")
async def api_status() -> JSONResponse:
    cfg = load_config()
    return JSONResponse(
        {
            "groq": {"configured": bool(cfg["groqKey"]), "key": mask(cfg["groqKey"]), "model": cfg["groqModel"] or "auto"},
            "continuous_listen_minutes": cfg["continuous_listen_minutes"],
            "tts_engine": cfg["tts_engine"],
            "tts_voice": cfg["tts_voice"],
        }
    )


@app.get("/api/config")
async def api_config_get() -> JSONResponse:
    return JSONResponse(load_config())


@app.get("/api/config/masked")
@app.get("/config/masked")
async def api_config_masked() -> JSONResponse:
    """Config com a chave MASCARADA — seguro para exibir/logar (nunca devolve o segredo)."""
    cfg = load_config()
    return JSONResponse(
        {
            "groqKey": mask(cfg["groqKey"]),
            "groqModel": cfg["groqModel"],
            "continuous_listen_minutes": cfg["continuous_listen_minutes"],
            "configured": bool(cfg["groqKey"]),
            "tts_engine": cfg["tts_engine"],
            "tts_voice": cfg["tts_voice"],
        }
    )


@app.post("/api/config")
async def api_config_post(request: Request) -> JSONResponse:
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "json inválido"}, status_code=400)
    cfg = load_config()
    if isinstance(body.get("groqKey"), str):
        key = body["groqKey"].strip()
        # nunca grava um placeholder mascarado por cima da chave real
        if _looks_masked(key):
            security_log("config", "tentativa de gravar chave mascarada", blocked=True)
        else:
            cfg["groqKey"] = key
    if isinstance(body.get("groqModel"), str):
        cfg["groqModel"] = body["groqModel"].strip()[:120]
    if body.get("continuous_listen_minutes") is not None:
        cfg["continuous_listen_minutes"] = clamp_minutes(body.get("continuous_listen_minutes"))
    if body.get("tts_engine") is not None:
        new_engine = clamp_tts_engine(body.get("tts_engine"))
        if new_engine != cfg["tts_engine"]:
            # trocar de motor troca a voz: cada motor tem a sua lista
            cfg["tts_voice"] = TTS_DEFAULT_VOICE.get(new_engine, "")
        cfg["tts_engine"] = new_engine
    if body.get("tts_voice") is not None:
        cfg["tts_voice"] = clamp_tts_voice(body.get("tts_voice"), cfg["tts_engine"])
    save_config(cfg)
    return JSONResponse(
        {
            "ok": True,
            "continuous_listen_minutes": cfg["continuous_listen_minutes"],
            "tts_engine": cfg["tts_engine"],
            "tts_voice": cfg["tts_voice"],
        }
    )


# ── estáticos ───────────────────────────────────────────────────────────
MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


@app.get("/{path:path}")
async def static_files(path: str):
    from fastapi.responses import Response

    rel = path or "index.html"
    if rel in ("", "/"):
        rel = "index.html"
    target = (PUBLIC_DIR / rel).resolve()
    if not str(target).startswith(str(PUBLIC_DIR.resolve())) or not target.is_file():
        return Response("404", status_code=404, media_type="text/plain")
    data = target.read_bytes()
    headers = {}
    if target.suffix == ".html":
        headers["Cache-Control"] = "no-cache"
    return Response(data, media_type=MIME.get(target.suffix, "application/octet-stream"), headers=headers)
