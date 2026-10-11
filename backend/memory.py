"""
JARVIS — memória persistente (ChromaDB + all-MiniLM-L6-v2).

Cada conversa enriquece a memória: o app.py salva a mensagem do usuário
(source="chat") e injeta as memórias relevantes no prompt antes de chamar o LLM.

- Banco: %APPDATA%\\JARVIS\\chroma_db (ajustável por JARVIS_MEMORY_DIR)
- Embeddings: sentence-transformers "all-MiniLM-L6-v2" quando disponível;
  reserva: ONNX MiniLM do próprio chromadb (MESMO modelo, sem PyTorch) —
  é o caminho usado no .exe empacotado.
- Limites: 1000 caracteres por memória, 10000 memórias (poda as mais antigas).
- Segurança: texto sanitizado (sem HTML/scripts) e bloqueio de chaves/senhas.
"""
from __future__ import annotations

import os
import re
import threading
import unicodedata
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

MAX_TEXT_CHARS = 1000
MAX_MEMORIES = 10000
COLLECTION = "jarvis_memory"
ARCHIVE_AFTER_DAYS = 90          # memórias antigas e nunca usadas viram "arquivadas"
MIN_RELEVANT_CHARS = 30          # abaixo disso, só entra se tiver verbo de afirmação

_lock = threading.Lock()
_client: Any = None
_collection: Any = None
_embedder: Any = None

_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>[\s\S]*?</\1>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]*>")
_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_WS_RE = re.compile(r"\s+")

# padrões de segredo: nada disso entra na memória
_SECRET_RE = re.compile(
    r"\b(?:gsk_|sk-|xox[abprs]-|ghp_|github_pat_|AIza|AKIA)[A-Za-z0-9_\-]{8,}"
    r"|\b(?:api[\s_-]?key|apikey|secret|client[_-]?secret|senha|password|passwd|credencial|token)\b",
    re.IGNORECASE,
)


# ── relevância e categorização ──────────────────────────────────────────
# Nem tudo merece virar memória: conversa fiada e perguntas passageiras não.
CATEGORIES = ("pessoal", "preferencias", "rotina", "projetos", "tecnico", "outros")
CATEGORY_PRIORITY = {name: i for i, name in enumerate(CATEGORIES)}   # 0 = mais importante

_GENERIC = {
    "oi", "ola", "olá", "eai", "e ai", "e aí", "tudobem", "tudo bem", "tudo bom", "td bem",
    "ok", "okay", "beleza", "blz", "valeu", "vlw", "obg", "obrigado", "obrigada", "de nada",
    "bom dia", "boa tarde", "boa noite", "sim", "nao", "não", "hmm", "hum", "aha", "teste",
    "testando", "ta bom", "tá bom", "certo", "entendi", "legal", "show", "boa",
}
_QUESTION_STARTS = (
    "que", "qual", "quais", "quanto", "quantos", "quantas", "como", "quando", "onde", "quem",
    "por que", "porque", "porquê", "pra que", "para que", "cade", "cadê", "sera", "será",
    "tem como", "voce pode", "você pode", "pode", "me diz",
)
_AFFIRM_RE = re.compile(
    r"\b(sou|é|eh|tenho|gosto|odeio|amo|detesto|adoro|prefiro|faço|faco|moro|estou|trabalho|"
    r"estudo|treino|acordo|durmo|chamo|uso|jogo|quero|nasci|curto|odeio|odeio|costumo|preciso|"
    r"meu|minha|meus|minhas|comecei|terminei|consegui|tô|to|estarei|vou)\b",
    re.IGNORECASE,
)
_CATEGORY_PATTERNS: dict[str, tuple[str, ...]] = {
    "pessoal": (
        r"\bmeu nome\b", r"\bme chamo\b", r"\btenho \d+ anos\b", r"\bmor[oa]\b", r"\bmor[oa] em\b",
        r"\bminha (família|familia|mãe|mae|esposa|namorada|filha|irmã|irma)\b",
        r"\bmeu (pai|irmão|irmao|filho|marido|namorado|apelido)\b",
        r"\bsou (de|do|da)\b", r"\bnasci\b", r"\bcasad[oa]\b", r"\bsolteir[oa]\b", r"\bminha idade\b",
    ),
    "preferencias": (
        r"\bgosto\b", r"\bodeio\b", r"\bamo\b", r"\bdetesto\b", r"\badoro\b", r"\bprefiro\b",
        r"\bfavorit[oa]\b", r"\bn[ãa]o gosto\b", r"\bcurto\b", r"\bnunca como\b", r"\bnunca bebo\b",
    ),
    "rotina": (
        r"\bacordo\b", r"\bacordar\b", r"\bdurmo\b", r"\bdormir\b", r"\btreino\b", r"\btreinar\b",
        r"\bacademia\b", r"\btodos os dias\b", r"\btoda semana\b", r"\brotina\b", r"\bmeu hor[áa]rio\b",
        r"\balmo[çc]o\b", r"\bjanto\b", r"\bcorro\b", r"\bcaminho\b",
    ),
    "projetos": (
        r"\bjarvis\b", r"\bprojeto\b", r"\bmeu app\b", r"\bminha startup\b", r"\btuy toad\b",
        r"\bestou (fazendo|criando|construindo|desenvolvendo)\b", r"\bminha ideia\b", r"\bmeu site\b",
        r"\bbot\b", r"\bagente\b",
    ),
    "tecnico": (
        r"\bpython\b", r"\bjavascript\b", r"\btypescript\b", r"\breact\b", r"\bc[óo]digo\b",
        r"\bprogram[oa]\b", r"\bapi\b", r"\bbanco de dados\b", r"\bdocker\b", r"\bgit\b", r"\blinux\b",
        r"\bsql\b", r"\bfastapi\b", r"\bc#\b", r"\bjava\b", r"\bhtml\b", r"\bcss\b", r"\blinux\b",
        r"\bterminal\b", r"\bdeploy\b", r"\bbug\b", r"\brefatorar\b", r"\bcompilador\b",
    ),
}
_CATEGORY_RES: dict[str, list[re.Pattern[str]]] = {
    name: [re.compile(p, re.IGNORECASE) for p in pats] for name, pats in _CATEGORY_PATTERNS.items()
}


def _fold(text: str) -> str:
    """Minúsculas sem acentos, para comparar "tudo bem" com o que o usuário digitou."""
    s = unicodedata.normalize("NFKD", str(text or "").lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9\s]", " ", s).strip()


def category_of(text: str) -> str:
    """Classifica a memória: pessoal, preferencias, rotina, projetos, tecnico ou outros."""
    s = str(text or "")
    # ordem: quem ele é, o que prefere, com o que trabalha, sua rotina e seus projetos
    for name in ("pessoal", "preferencias", "tecnico", "rotina", "projetos"):
        for rx in _CATEGORY_RES[name]:
            if rx.search(s):
                return name
    return "outros"


def is_worth_remembering(text: str) -> tuple[bool, str]:
    """Filtro de relevância: (vale a pena?, motivo quando não vale)."""
    clean = str(text or "").strip()
    folded = _fold(clean)
    if not clean:
        return False, "texto vazio"
    if folded in _GENERIC or len(folded) <= 3:
        return False, "conversa fiada (oi/ok/valeu...)"
    if folded.startswith(_QUESTION_STARTS):
        return False, "pergunta passageira (não é informação persistente)"
    if len(clean) < MIN_RELEVANT_CHARS and not _AFFIRM_RE.search(clean):
        return False, "curta demais e sem afirmação sobre o Comandante"
    return True, ""


def sanitize_text(text: str, limit: int = MAX_TEXT_CHARS) -> str:
    """Remove scripts/tags/caracteres de controle e limita o tamanho."""
    s = str(text or "")
    s = _SCRIPT_RE.sub(" ", s)
    s = _TAG_RE.sub(" ", s)
    s = _CTRL_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s[:limit]


def looks_sensitive(text: str) -> bool:
    """True para chaves de API, senhas e credenciais (não são memorizadas)."""
    return bool(_SECRET_RE.search(str(text or "")))


def memory_dir() -> Path:
    """Pasta do banco: %APPDATA%\\JARVIS\\chroma_db (ou JARVIS_MEMORY_DIR)."""
    env = os.environ.get("JARVIS_MEMORY_DIR")
    base = Path(env) if env else Path(os.environ.get("APPDATA") or Path.home()) / "JARVIS"
    path = base / "chroma_db"
    path.mkdir(parents=True, exist_ok=True)
    return path


class _Embedder:
    """all-MiniLM-L6-v2 via sentence-transformers; ONNX MiniLM como reserva."""

    def __init__(self) -> None:
        self.kind = ""
        self._st = None
        self._onnx = None
        try:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._st = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
            self.kind = "sentence-transformers"
            return
        except Exception:  # noqa: BLE001
            self._st = None
        try:
            from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

            self._onnx = DefaultEmbeddingFunction()
            self.kind = "onnx-minilm"
            return
        except Exception:  # noqa: BLE001
            self._onnx = None
        try:
            from chromadb.utils.embedding_functions import ONNXMiniLM_L6_V2  # type: ignore

            self._onnx = ONNXMiniLM_L6_V2()
            self.kind = "onnx-minilm"
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError(f"nenhum embedder disponível: {exc}") from exc

    def encode(self, texts: list[str]) -> list[list[float]]:
        if self._st is not None:
            vecs = self._st.encode(texts, normalize_embeddings=True, show_progress_bar=False)
            return [[float(x) for x in v] for v in vecs]
        out = self._onnx(texts)  # EmbeddingFunction do chromadb (posicional)
        return [[float(x) for x in v] for v in out]


def _embedder_instance() -> _Embedder:
    global _embedder
    if _embedder is None:
        with _lock:
            if _embedder is None:
                _embedder = _Embedder()
    return _embedder


def embed(texts: list[str]) -> list[list[float]]:
    return _embedder_instance().encode(texts)


def embedder_kind() -> str:
    return str(getattr(_embedder, "kind", "")) or "não carregado"


def _ensure_collection() -> Any:
    global _client, _collection
    if _collection is not None:
        return _collection
    with _lock:
        if _collection is not None:
            return _collection
        import chromadb

        try:
            from chromadb.config import Settings

            # telemetria desligada: nada sai do computador
            _client = chromadb.PersistentClient(
                path=str(memory_dir()), settings=Settings(anonymized_telemetry=False)
            )
        except Exception:  # noqa: BLE001  (versões antigas sem o kwarg)
            _client = chromadb.PersistentClient(path=str(memory_dir()))
        try:
            _collection = _client.get_or_create_collection(
                name=COLLECTION, metadata={"hnsw:space": "cosine"}
            )
        except Exception:  # noqa: BLE001  (versões novas mudaram a config)
            _collection = _client.get_or_create_collection(name=COLLECTION)
        return _collection


def _prune_locked() -> int:
    """Mantém no máximo MAX_MEMORIES — apaga as mais antigas."""
    col = _collection
    total = int(col.count())
    if total <= MAX_MEMORIES:
        return 0
    got = col.get(include=["metadatas"])
    ids = got.get("ids") or []
    metas = got.get("metadatas") or []
    pairs = sorted(
        zip(ids, metas), key=lambda p: str((p[1] or {}).get("timestamp") or "")
    )
    excess = total - MAX_MEMORIES
    kill = [str(i) for i, _m in pairs[:excess]]
    if kill:
        col.delete(ids=kill)
    return len(kill)


def add_memory(text: str, source: str = "manual") -> dict[str, Any]:
    """Salva uma memória (filtrada + sanitizada) e devolve {id, text, source, timestamp}.

    Devolve {"skipped": True, "reason": ...} para texto vazio, sensível, genérico
    ou que não diga nada persistente sobre o Comandante.
    """
    clean = sanitize_text(text)
    if not clean:
        return {"skipped": True, "reason": "texto vazio"}
    if looks_sensitive(clean):
        return {"skipped": True, "reason": "conteúdo sensível (chave/senha/credencial) — não salvo"}
    worth, why = is_worth_remembering(clean)
    if not worth:
        return {"skipped": True, "reason": why}
    src = sanitize_text(source, 60) or "manual"
    category = category_of(clean)
    now = datetime.now().isoformat(timespec="seconds")
    mid = str(uuid.uuid4())
    col = _ensure_collection()
    vec = embed([clean])[0]
    with _lock:
        col.add(
            ids=[mid],
            documents=[clean],
            metadatas=[{"source": src, "timestamp": now, "category": category}],
            embeddings=[vec],
        )
        _prune_locked()
    return {"id": mid, "text": clean, "source": src, "timestamp": now, "category": category}


def category_counts() -> dict[str, int]:
    """Quantas memórias em cada categoria (inclui as arquivadas)."""
    col = _ensure_collection()
    got = col.get(include=["metadatas"])
    out = {name: 0 for name in CATEGORIES}
    for meta in got.get("metadatas") or []:
        name = str((meta or {}).get("category") or "outros")
        out[name] = out.get(name, 0) + 1
    return out


def archive_stale(days: int = ARCHIVE_AFTER_DAYS) -> int:
    """Arquiva (sem apagar) memórias com mais de `days` dias que nunca foram usadas."""
    col = _ensure_collection()
    got = col.get(include=["metadatas"])
    ids = got.get("ids") or []
    metas = got.get("metadatas") or []
    cutoff = datetime.now() - timedelta(days=max(1, int(days)))
    now = datetime.now().isoformat(timespec="seconds")
    kill_ids: list[str] = []
    kill_meta: list[dict[str, Any]] = []
    for i, mid in enumerate(ids):
        meta = dict(metas[i] or {})
        if meta.get("archived") or meta.get("last_used"):
            continue          # já arquivada ou já foi usada alguma vez → fica
        try:
            created = datetime.fromisoformat(str(meta.get("timestamp") or ""))
        except Exception:  # noqa: BLE001
            continue
        if created < cutoff:
            meta["archived"] = True
            meta["archived_at"] = now
            kill_ids.append(str(mid))
            kill_meta.append(meta)
    if kill_ids:
        with _lock:
            for i in range(0, len(kill_ids), 200):
                col.update(ids=kill_ids[i : i + 200], metadatas=kill_meta[i : i + 200])
    return len(kill_ids)


def _mark_used(ids: list[str]) -> None:
    """Marca as memórias que entraram numa resposta (usadas) — evita o arquivamento."""
    col = _ensure_collection()
    now = datetime.now().isoformat(timespec="seconds")
    with _lock:
        got = col.get(ids=ids, include=["metadatas"])
        metas = got.get("metadatas") or []
        keep_ids = got.get("ids") or []
        new_meta: list[dict[str, Any]] = []
        for meta in metas:
            m = dict(meta or {})
            m["last_used"] = now
            m["used_count"] = int(m.get("used_count") or 0) + 1
            new_meta.append(m)
        if keep_ids:
            col.update(ids=list(keep_ids), metadatas=new_meta)


def search_memory(query: str, n: int = 5) -> list[dict[str, Any]]:
    """As N memórias mais relevantes: busca semântica + prioridade de categoria.

    "pessoal" e "preferencias" passam na frente de "tecnico"/"outros" quando a
    relevância é parecida. Memórias arquivadas (90 dias, nunca usadas) ficam fora.
    """
    q = sanitize_text(query, 300)
    if not q:
        return []
    col = _ensure_collection()
    if int(col.count()) == 0:
        return []
    vec = embed([q])[0]
    want = max(1, min(int(n), 50))
    res = col.query(
        query_embeddings=[vec],
        n_results=max(want, min(50, want * 4)),
        include=["documents", "metadatas", "distances"],
    )
    ids = (res.get("ids") or [[]])[0]
    docs = (res.get("documents") or [[]])[0]
    metas = (res.get("metadatas") or [[]])[0]
    dists = (res.get("distances") or [[]])[0]
    ranked: list[tuple[float, dict[str, Any]]] = []
    for i, mid in enumerate(ids):
        meta = metas[i] or {}
        if meta.get("archived"):
            continue          # arquivada: não entra em resposta
        category = str(meta.get("category") or "outros")
        dist = float(dists[i]) if i < len(dists) else 1.0
        # prioridade entra como um desconto pequeno: relevância continua mandando
        score = dist + CATEGORY_PRIORITY.get(category, len(CATEGORIES)) * 0.04
        ranked.append(
            (
                score,
                {
                    "id": mid,
                    "text": docs[i],
                    "source": meta.get("source", ""),
                    "timestamp": meta.get("timestamp", ""),
                    "category": category,
                    "distance": round(dist, 4),
                },
            )
        )
    ranked.sort(key=lambda p: p[0])
    out = [item for _score, item in ranked[:want]]
    if out:
        use_ids = [str(m["id"]) for m in out]
        threading.Thread(target=_mark_used, args=(use_ids,), daemon=True, name="jarvis-memory-used").start()
    return out


def list_memories(limit: int = 100) -> list[dict[str, Any]]:
    """As memórias mais recentes primeiro."""
    col = _ensure_collection()
    got = col.get(include=["documents", "metadatas"])
    ids = got.get("ids") or []
    docs = got.get("documents") or []
    metas = got.get("metadatas") or []
    items = [
        {
            "id": mid,
            "text": docs[i] if i < len(docs) else "",
            "source": (metas[i] or {}).get("source", ""),
            "timestamp": (metas[i] or {}).get("timestamp", ""),
            "category": (metas[i] or {}).get("category") or "outros",
            "archived": bool((metas[i] or {}).get("archived")),
            "used_count": int((metas[i] or {}).get("used_count") or 0),
        }
        for i, mid in enumerate(ids)
    ]
    items.sort(key=lambda m: str(m.get("timestamp") or ""), reverse=True)
    try:
        cap = max(1, min(int(limit), 500))
    except (TypeError, ValueError):
        cap = 100
    return items[:cap]


def delete_memory(memory_id: str) -> int:
    """Apaga uma memória pelo id; devolve quantas foram removidas."""
    mid = str(memory_id or "").strip()
    if not mid:
        return 0
    col = _ensure_collection()
    before = int(col.count())
    with _lock:
        try:
            col.delete(ids=[mid])
        except Exception:  # noqa: BLE001
            return 0
        return max(0, before - int(col.count()))


def delete_all_memories() -> int:
    """Apaga TUDO; devolve quantas memórias existiam."""
    col = _ensure_collection()
    total = int(col.count())
    if not total:
        return 0
    ids = col.get().get("ids") or []
    with _lock:
        for i in range(0, len(ids), 500):
            col.delete(ids=ids[i : i + 500])
    return total


def stats() -> dict[str, Any]:
    """Total, memória mais antiga e mais recente, arquivadas e categorias."""
    col = _ensure_collection()
    total = int(col.count())
    oldest = newest = ""
    archived = 0
    metas: list[Any] = []
    if total:
        got = col.get(include=["metadatas"])
        metas = got.get("metadatas") or []
        stamps = sorted(
            s
            for s in (str((m or {}).get("timestamp") or "") for m in metas)
            if s
        )
        if stamps:
            oldest, newest = stamps[0], stamps[-1]
        archived = sum(1 for m in metas if (m or {}).get("archived"))
    return {
        "total": total,
        "archived": archived,
        "active": max(0, total - archived),
        "categories": category_counts() if total else {name: 0 for name in CATEGORIES},
        "oldest": oldest,
        "newest": newest,
        "limit": MAX_MEMORIES,
        "max_chars": MAX_TEXT_CHARS,
        "archive_after_days": ARCHIVE_AFTER_DAYS,
        "embedder": embedder_kind(),
        "path": str(memory_dir()),
    }


def warmup() -> bool:
    """Pré-carrega banco + embedder e arquiva o que envelheceu (thread no start)."""
    try:
        _ensure_collection()
        embed(["warmup"])
        try:
            archive_stale()
        except Exception:  # noqa: BLE001
            pass
        return True
    except Exception:  # noqa: BLE001
        return False
