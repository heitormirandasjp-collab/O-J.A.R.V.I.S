#!/usr/bin/env node
/**
 * JARVIS Command Center — servidor zero-dependências.
 * Serve a UI estática e expõe /api/chat com streaming SSE,
 * falando apenas com a Groq (sem fallback).
 *
 * Uso:  node server.js          (porta 8755)
 *       PORT=9000 node server.js
 */
'use strict';

const http = require('http');
const https = require('https');
const fs = require('fs');
const path = require('path');
const { URL } = require('url');

const PORT = Number(process.env.PORT) || 8755;
const HOST = '127.0.0.1';
const PUBLIC_DIR = path.join(__dirname, 'public');
const CONFIG_PATH = path.join(__dirname, 'config.json');

/* CORS restrito: só a própria UI local (nunca "*"). Ajuste com JARVIS_ALLOWED_ORIGINS. */
const ALLOWED_ORIGINS = (process.env.JARVIS_ALLOWED_ORIGINS || 'http://127.0.0.1:8755,http://localhost:8755')
  .split(',')
  .map((s) => s.trim())
  .filter(Boolean);

function corsHeaders(req) {
  const origin = req.headers.origin;
  if (!origin || !ALLOWED_ORIGINS.includes(origin)) return {};
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'GET, POST, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type',
    Vary: 'Origin',
  };
}

const BACKEND_URL = process.env.BACKEND_URL || 'http://127.0.0.1:8000';
const GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions';
const GROQ_MODELS = ['openai/gpt-oss-120b', 'openai/gpt-oss-20b', 'qwen/qwen3.8-27b'];

/* System prompt (personalidade): fonte única em system_prompt.txt — o MESMO arquivo
   é lido pelo app.py. As regras operacionais abaixo continuam valendo. */
function loadSystemPrompt() {
  try {
    return fs.readFileSync(path.join(__dirname, 'system_prompt.txt'), 'utf8').trim();
  } catch {
    return 'Você é J.A.R.V.I.S. (Just A Rather Very Intelligent System), o assistente pessoal do '
      + 'Comandante. Formal, leal e conciso — responda em português brasileiro no estilo JARVIS.';
  }
}

const SYSTEM_RULES = `REGRA CRÍTICA ANTI-ALUCINAÇÃO:

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

LEMBRETE FINAL:
Você NÃO é o ChatGPT. Você NÃO é um assistente genérico. Você é o JARVIS — sofisticado, leal, irônico na medida, e absolutamente dedicado ao Comandante. Cada resposta deve parecer que veio de uma IA de ficção científica que desenvolveu personalidade própria ao longo de anos de convivência.`;

const SYSTEM_PROMPT = loadSystemPrompt() + '\n\n' + SYSTEM_RULES;

/* ── utilidades de data/agenda (usa o mesmo formato do app.py) ── */
function foldWord(w) {
  return String(w).toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

const WEEKDAYS = { domingo: 0, segunda: 1, terca: 2, quarta: 3, quinta: 4, sexta: 5, sabado: 6 };

function extractDatetime(text) {
  const low = foldWord(text);
  const now = new Date();
  let base = null;
  if (low.includes('depois de amanha')) base = new Date(now.getTime() + 2 * 864e5);
  else if (low.includes('amanha')) base = new Date(now.getTime() + 864e5);
  else if (low.includes('hoje')) base = new Date(now.getTime());
  else {
    const wd = low.match(/\b(segunda|terca|quarta|quinta|sexta|sabado|domingo)(?:-feira)?\b/);
    if (wd && WEEKDAYS[wd[1]] !== undefined) {
      const days = (WEEKDAYS[wd[1]] - now.getDay() + 7) % 7;
      base = new Date(now.getTime() + (days || 7) * 864e5);
    }
    if (!base) {
      const dm = String(text).match(/\b(\d{1,2})[/-](\d{1,2})(?:[/-](\d{2,4}))?\b/);
      if (dm) {
        const day = Number(dm[1]);
        const month = Number(dm[2]);
        let year = dm[3] ? Number(dm[3]) : now.getFullYear();
        if (year < 100) year += 2000;
        const cand = new Date(year, month - 1, day);
        if (cand.getDate() !== day || cand.getMonth() !== month - 1) return null;
        base = cand;
      }
    }
  }
  if (!base) return null;
  let hh = 9;
  let mm = 0;
  let hm = low.match(/\b(?:[àa]s?|at)\s*(\d{1,2})(?:[:h](\d{2}))?\s*(?:h|horas)?\b/);
  if (hm) {
    hh = Number(hm[1]);
    mm = Number(hm[2] || 0);
  } else {
    hm = low.match(/\b(\d{1,2})[h:](\d{2})\b/);
    if (hm) {
      hh = Number(hm[1]);
      mm = Number(hm[2]);
    }
  }
  if (hh > 23 || mm > 59) return null;
  base.setHours(hh, mm, 0, 0);
  return base;
}

function fmtDT(d) {
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}

function extractAgendaTitle(text) {
  let t = String(text);
  t = t.replace(/\b(me\s+lembr\w+|lembra-me|lembre-me|agend\w+|marcar|marque|anot\w+|criar?\s+evento|novo\s+evento|cadastr\w+)\b/gi, ' ');
  t = t.replace(/^\s*\b(?:de|que|para|pra)\b\s*/i, ' ');
  t = t.replace(/\b(hoje|amanh[ãa]|depois de amanh[ãa]|segunda|ter[çc]a|quarta|quinta|sexta|s[áa]bado|domingo)(?:-feira)?\b/gi, ' ');
  t = t.replace(/\b(?:[àa]s?|at)\s*\d{1,2}(?:[:h]\d{2})?\s*(?:h|horas)?\b/gi, ' ');
  t = t.replace(/\b\d{1,2}[h:]\d{2}\b/g, ' ');
  t = t.replace(/\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b/g, ' ');
  return t.replace(/\s+/g, ' ').replace(/^[\s.,!?-]+|[\s.,!?-]+$/g, '');
}

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
};

class UpstreamError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function clampMinutes(v, def = 5) {
  const m = Math.trunc(Number(v));
  if (!Number.isFinite(m)) return def;
  return Math.max(0, Math.min(1440, m));
}

function loadConfig() {
  try {
    const raw = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
    return Object.assign({ groqKey: '', groqModel: '', continuous_listen_minutes: 5 }, raw, {
      continuous_listen_minutes: clampMinutes((raw || {}).continuous_listen_minutes),
    });
  } catch {
    return { groqKey: '', groqModel: '', continuous_listen_minutes: 5 };
  }
}

function saveConfig(cfg) {
  // modo 0600: só o usuário lê/escreve o arquivo com a chave da API
  fs.writeFileSync(CONFIG_PATH, JSON.stringify(cfg, null, 2), { mode: 0o600 });
}

function mask(secret) {
  if (!secret) return null;
  const s = String(secret);
  return s.length <= 8 ? '••••' : `${s.slice(0, 3)}••••${s.slice(-4)}`;
}

function looksMasked(value) {
  const v = String(value || '');
  return !!v && (v.includes('•') || v.includes('*') || /^[•xX*.]+$/.test(v));
}

/* ── segurança: limites do chat, rate limit e sanitização ── */
const MAX_CHAT_INPUT = 5000;      // caracteres por mensagem do usuário
const MAX_CHAT_OUTPUT = 10000;    // caracteres da resposta do LLM
const CHAT_RATE_WINDOW = 60_000;  // ms
const CHAT_RATE_MAX = 30;         // chamadas por janela
let chatHits = [];

function chatRateLimited() {
  const now = Date.now();
  chatHits = chatHits.filter((t) => now - t <= CHAT_RATE_WINDOW);
  if (chatHits.length >= CHAT_RATE_MAX) return true;
  chatHits.push(now);
  return false;
}

/* ── visualizador 3D (intenção detectada aqui, sem depender do modelo) ── */
const VIS3D_VERB_RE = /\b(me\s+mostra|mostrar|mostra|visualizar|visualiza|renderizar|renderiza|desenhar|desenha)\b/i;
const VIS3D_MARK_RE = /\b(em\s+)?(3d|3-d)\b|\b(em\s+)?tr[êe]s\s+dimens[õo]es\b/i;
const VIS3D_BLOCK_RE =
  /not[ií]cias?|manchetes?|agenda|lembrete|cota[çc]|a[çc][õo]es?|d[óo]lar|euro|processo|cpu|mem[óo]ria|disco|sistema|clima|previs|horas?|data|arquivo|pasta|imagem|foto|painel|tela|tudo/i;
const VIS3D_STOP = new Set(['isso', 'isto', 'ele', 'ela', 'aquilo', 'um', 'uma', 'o', 'a']);

function detectVisualize3D(text) {
  const t = String(text || '').replace(/\s+/g, ' ').trim();
  if (!t || VIS3D_BLOCK_RE.test(t) || !VIS3D_VERB_RE.test(t)) return null;
  let obj = t.replace(/^\s*j[aá]rvis[\s,:.!-]*/i, '');
  obj = obj.replace(/^\s*(por\s+favor[\s,]*)?/i, '');
  obj = obj.replace(VIS3D_VERB_RE, ' ').replace(VIS3D_MARK_RE, ' ');
  obj = obj.replace(/^\s*(o|a|os|as|um|uma|uns|umas|de|do|da)\s+/i, '');
  obj = obj.replace(/\s+/g, ' ').replace(/^[\s.,!?:;\-—]+|[\s.,!?:;\-—]+$/g, '');
  if (obj.length < 2 || obj.length > 60 || VIS3D_STOP.has(obj.toLowerCase())) return null;
  return obj;
}

function stripHtml(s) {
  if (typeof s !== 'string' || (!s.includes('<') && !s.includes('>'))) return s;
  return s.replace(/<(script|style)\b[^>]*>[\s\S]*?<\/\1>/gi, ' ').replace(/<[^>]*>/g, '');
}

function securityHeaders() {
  return {
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'no-referrer',
  };
}

function readBody(req, limit = 1024 * 512) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on('data', (c) => {
      size += c.length;
      if (size > limit) {
        reject(new Error('payload muito grande'));
        req.destroy();
        return;
      }
      chunks.push(c);
    });
    req.on('end', () => resolve(Buffer.concat(chunks).toString('utf8')));
    req.on('error', reject);
  });
}

function extractErrorMessage(raw, contentType) {
  if (!raw) return 'resposta vazia do provedor';
  if (contentType && contentType.includes('text/html')) {
    return 'o provedor devolveu uma página HTML (autenticação ausente ou token inválido)';
  }
  try {
    const j = JSON.parse(raw);
    const msg =
      (j.error && (j.error.message || j.error.msg)) ||
      j.message ||
      (typeof j.error === 'string' ? j.error : null);
    if (msg) return String(msg).slice(0, 400);
  } catch {
    /* segue */
  }
  return raw.replace(/\s+/g, ' ').slice(0, 200);
}

/** Faz POST streaming para um provedor OpenAI-compatible. */
function callUpstream({ url, headers, body, timeout }) {
  return new Promise((resolve, reject) => {
    const u = new URL(url);
    const payload = JSON.stringify(body);
    const req = https.request(
      {
        hostname: u.hostname,
        port: u.port || 443,
        path: u.pathname + u.search,
        method: 'POST',
        headers: Object.assign(
          {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(payload),
            Accept: 'text/event-stream, application/json',
          },
          headers,
        ),
        timeout,
      },
      (res) => {
        const contentType = String(res.headers['content-type'] || '');
        if (res.statusCode !== 200) {
          let raw = '';
          res.on('data', (c) => (raw += c));
          res.on('end', () =>
            reject(new UpstreamError(res.statusCode, extractErrorMessage(raw, contentType))),
          );
          return;
        }
        if (!/event-stream|application\/json/.test(contentType)) {
          res.resume();
          res.on('end', () =>
            reject(new UpstreamError(res.statusCode, extractErrorMessage('', contentType))),
          );
          return;
        }
        resolve({ res, contentType });
      },
    );
    req.on('timeout', () => req.destroy(new Error('tempo esgotado aguardando o provedor')));
    req.on('error', (e) =>
      reject(new UpstreamError(0, `falha de rede: ${e.message || e.code || 'erro desconhecido'}`)),
    );
    req.write(payload);
    req.end();
  });
}

function sse(res, event, data) {
  res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
}

/* ─────────────────────────────────────────────────────────────────
   Ferramentas locais (backend Python, porta 8000)
   ───────────────────────────────────────────────────────────────── */

/** Chama o backend local; nunca lança — devolve null se estiver fora do ar. */
function backendCall(method, path, body, timeout = 8000) {
  return new Promise((resolve) => {
    let u;
    try {
      u = new URL(path, BACKEND_URL);
    } catch {
      return resolve(null);
    }
    const payload = body ? JSON.stringify(body) : null;
    const req = http.request(
      {
        hostname: u.hostname,
        port: u.port || 80,
        path: u.pathname + u.search,
        method,
        headers: payload
          ? { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) }
          : {},
        timeout,
      },
      (r) => {
        let raw = '';
        r.on('data', (c) => (raw += c));
        r.on('end', () => {
          try {
            resolve(JSON.parse(raw));
          } catch {
            resolve({ raw: raw.slice(0, 400) });
          }
        });
      },
    );
    req.on('timeout', () => {
      req.destroy();
      resolve(null);
    });
    req.on('error', () => resolve(null));
    if (payload) req.write(payload);
    req.end();
  });
}

const APP_MAP = {
  chrome: 'start chrome',
  'google chrome': 'start chrome',
  edge: 'start msedge',
  'microsoft edge': 'start msedge',
  firefox: 'start firefox',
  notepad: 'notepad',
  'bloco de notas': 'notepad',
  calculadora: 'calc',
  calc: 'calc',
  explorer: 'start explorer',
  'explorador de arquivos': 'start explorer',
  cmd: 'start cmd',
  powershell: 'start powershell',
  terminal: 'start wt',
  vscode: 'code',
  'vs code': 'code',
  code: 'code',
  spotify: 'start spotify',
  discord: 'start discord',
  whatsapp: 'start whatsapp',
  steam: 'start steam',
  word: 'start winword',
  excel: 'start excel',
  paint: 'start mspaint',
  taskmgr: 'start taskmgr',
  'gerenciador de tarefas': 'start taskmgr',
  'painel de controle': 'control',
};

/** Detecta uma intenção de ferramenta a partir da mensagem do usuário. */
function detectTool(text) {
  const t = String(text || '').trim();
  const lower = t.toLowerCase();
  if (!t) return null;

  // 1. comando explícito: "! ipconfig" ou "exec: dir"
  let m = t.match(/^!\s*(.+)$/s) || lower.match(/^(?:exec|executar|run)\s*[:>]\s*(.+)$/s);
  if (m) return { name: 'exec', args: { cmd: m[1].trim() } };

  // 1b. atalhos explícitos: "/stocks PETR4 AAPL" e "/moedas"
  m = t.match(/^\/(?:stocks?|a[çc][õo]es?)\s+(.+)$/i);
  if (m) {
    const syms = m[1].toUpperCase().split(/[,\s]+/).filter(Boolean).slice(0, 6);
    if (syms.length) return { name: 'stocks', args: { symbols: syms.join(',') } };
  }
  if (/^\/(?:moedas?|currenc(?:y|ies)|c[âa]mbio)$/i.test(t)) return { name: 'currencies', args: {} };
  if (/^\/(?:sysinfo|sistema)$/i.test(t)) return { name: 'sysinfo', args: {} };

  // 1c. energia
  if (
    /\b(cancel\w*|abort\w*|aborta|interromp\w*)\b/.test(lower) &&
    /\b(deslig\w*|reinici\w*|shutdown|restart|hibern\w*|suspens\w*|desligamento)\b/.test(lower)
  ) {
    return { name: 'power-cancel', args: {} };
  }
  if (
    /\b(deslig\w*|shutdown|power\s*off|turn\s*off|apag\w*)\b/.test(lower) &&
    /\b(pc|computador|m[áa]quina|notebook|sistema|windows|tudo)\b/.test(lower)
  ) {
    return { name: 'power', args: { action: 'shutdown', delay: 30 } };
  }
  if (
    /\b(reinici\w*|restart|reboot)\b/.test(lower) &&
    /\b(pc|computador|m[áa]quina|notebook|sistema|windows|tudo)\b/.test(lower)
  ) {
    return { name: 'power', args: { action: 'restart', delay: 30 } };
  }
  if (/\b(hibern\w*)\b/.test(lower)) return { name: 'power', args: { action: 'hibernate', delay: 0 } };
  if (
    /\b(suspender|suspende|suspend|dormir|dorme|sleep)\b/.test(lower) &&
    /\b(pc|computador|m[áa]quina|notebook|sistema|windows|tudo)\b/.test(lower)
  ) {
    return { name: 'power', args: { action: 'sleep', delay: 0 } };
  }

  // 1d. fechar programa
  m = lower.match(
    /\b(?:fecha|feche|fechar|encerra|encerre|encerrar|mata|mate|matar|kill|close|finaliza|finalizar)\s+(?:o\s+|a\s+|os\s+|as\s+|the\s+)?([a-zà-ÿ0-9_.\- ]{2,40}?)(?:\s+(?:e|que|porque|pra|para)\b|[.,!?;]|$)/,
  );
  if (m) {
    const target = m[1].replace(/\s+/g, ' ').replace(/^[\s.,!?-]+|[\s.,!?-]+$/g, '');
    if (target && !['janela', 'programa', 'aplicativo', 'aba', 'chat', 'tudo'].includes(target)) {
      return { name: 'kill', args: { name: target, force: true } };
    }
  }

  // 1e. processos que mais consomem memória
  if (
    /\bprocessos?\b/.test(lower) &&
    /\b(quais|lista\w*|mostr\w*|ver|mem[óo]ria|ram|consum\w*|top|pesad\w*|rodando)\b/.test(lower)
  ) {
    return { name: 'processes', args: {} };
  }

  // 1f. notícias
  if (
    /\b(not[íi]cias?|manchetes?|news)\b/.test(lower) ||
    /\bo\s+que\s+(?:est[áa]\s+)?(?:acontecendo|rolando|ocorrendo)\b/.test(lower)
  ) {
    let topic = 'geral';
    const TOPICS = [
      [/tecnologia/, 'tecnologia'],
      [/esporte/, 'esportes'],
      [/economia/, 'economia'],
      [/mundo/, 'mundo'],
      [/brasil/, 'brasil'],
      [/pol[íi]tica/, 'politica'],
      [/ci[êe]ncia/, 'ciencia'],
    ];
    for (const [pat, mapped] of TOPICS) {
      if (pat.test(lower)) {
        topic = mapped;
        break;
      }
    }
    return { name: 'news', args: { topic, limit: 5 } };
  }

  // 1g. agenda
  m = t.match(
    /\b(?:cancel\w+|remov\w+|apag\w+|exclu\w+|delet\w+)\s+(?:o\s+|a\s+|os\s+|as\s+)?(?:evento|compromisso|lembrete|alarme|reuni[ãa]o)\s+(?:de\s+|do\s+|da\s+)?([\w .\-À-ÿ]{2,40})/i,
  );
  if (m) return { name: 'agenda-delete', args: { id: m[1].replace(/^[\s.,!?]+|[\s.,!?]+$/g, '') } };

  if (
    /\b(agenda|compromissos?|eventos?|lembretes?)\b/.test(lower) &&
    /\b(quais|o\s+que|mostr\w*|ver|lista\w*|tenho|pr[óo]xim\w*|minha)\b/.test(lower)
  ) {
    return { name: 'agenda-list', args: {} };
  }

  if (
    /\b(?:me\s+lembr\w+|lembra-me|lembre-me|agend\w+|marcar|marque|anot\w+|criar?\s+evento|novo\s+evento|cadastr\w+)\b/i.test(t)
  ) {
    const dt = extractDatetime(t);
    return { name: 'agenda-add', args: { title: extractAgendaTitle(t), datetime: dt ? fmtDT(dt) : '', description: '' } };
  }

  // 2. abrir aplicativo
  m = lower.match(/\b(?:abra|abrir|abre|inicie|iniciar|inicia|open|launch|start|rode)\s+(?:o\s+|a\s+|the\s+)?([\w .\-]{2,30})/);
  if (m) {
    const target = m[1].trim().replace(/\s+/g, ' ').replace(/[.。,!?]+$/, '');
    if (/^[\w .\-]{2,30}$/.test(target)) {
      const cmd = APP_MAP[target] || APP_MAP[target.replace(/\.exe$/, '')] || `start "" ${target}`;
      return { name: 'exec', args: { cmd } };
    }
  }

  // 3. status do sistema — vem ANTES de cotações ("como está a CPU" não é ação)
  if (
    /\b(cpu|mem[óo]ria|ram|disco|disk|processador|sistema|uptime|gpu|carga)\b/i.test(lower) &&
    /\b(como|qual|quanto|quanta|status|est[áa]|uso|usando|ver|mostre|monitor|porcentagem)\b/i.test(lower)
  ) {
    return { name: 'sysinfo', args: {} };
  }

  // 4. moedas — antes de cotações ("preço do dólar" não é ação)
  if (/\b(d[óo]lar|euro|c[âa]mbio|moeda|currency)\b/i.test(lower)) return { name: 'currencies', args: {} };

  // 5. cotações de ações
  const priceIntent = /(pre[çc]o|cota[çc][ãa]o|valor|a[çc][ãa]o|a[çc][õo]es|stock|quote)/i.test(lower);
  if (priceIntent) {
    // palavras que parecem ticker mas não são
    const STOP = new Set([
      'DA', 'DE', 'DO', 'DAS', 'DOS', 'A', 'O', 'AS', 'OS', 'E', 'EM', 'NO', 'NA',
      'QUE', 'QUAL', 'QUAIS', 'HOJE', 'AGORA', 'ESTA', 'VALOR', 'PRECO', 'COTACAO',
      'ACAO', 'ACOES', 'EUA', 'BR', 'BRL', 'USD', 'EUR', 'REAIS', 'REAL', 'MERCADO',
      'QUANTO', 'QUANTA', 'COMO', 'SOBRE', 'PARA', 'POR', 'UMA', 'UM', 'ME', 'SE', 'VER',
      'DIGA', 'DIZER', 'MOSTRE', 'PODE', 'PODERIA', 'FAVOR', 'ONTEM', 'AMANHA',
      'PRODUTO', 'SERVICO', 'PLANO', 'ASSINATURA', 'CONSULTORIA', 'EMPRESA', 'VOCES', 'VOCE',
      'CPU', 'RAM', 'GPU', 'DISCO', 'DISK', 'SISTEMA', 'MEMORIA', 'UPTIME', 'SSD',
      'DOLAR', 'EURO', 'CAMBIO', 'MOEDA', 'MOEDAS', 'OK', 'JARVIS', 'SIM', 'NAO',
    ]);
    const PRICE_WORDS = new Set(['preco', 'precos', 'cotacao', 'cotacoes', 'valor', 'valores', 'quote', 'quotes', 'acao', 'acoes', 'stock', 'stocks']);
    const ARTICLES = new Set(['da', 'do', 'de', 'das', 'dos']);
    const CONNECTORS = new Set(['e', 'and', 'ou', 'or']);
    const fold = (w) => w.toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, '');
    const br = [...t.matchAll(/\b([A-Za-z]{4}\d{1,2})(?:\.SA)?\b/g)].map((x) => x[1].toUpperCase());
    // tickers em CAIXA ALTA só contam perto de uma cotação (evita pegar
    // palavras soltas como "LINHA" em "responda em uma linha")
    const toks = t.split(/[^\p{L}\p{N}]+/u).filter(Boolean);
    const upper = [];
    toks.forEach((tok, i) => {
      if (tok !== tok.toUpperCase() || !/^[A-Z]{1,6}$/.test(tok) || STOP.has(tok)) return;
      const prev = i > 0 ? fold(toks[i - 1]) : '';
      const strong =
        i === 0
          ? toks.length > 1 && PRICE_WORDS.has(fold(toks[1]))
          : PRICE_WORDS.has(prev) || ARTICLES.has(prev) || CONNECTORS.has(prev);
      if (strong) upper.push(tok);
    });
    // tickers logo após uma palavra de preço ("preço de msft")
    const usWord = [...lower.matchAll(/(?:pre[çc]o|valor|cota[çc][ãa]o|quote)s?\s+(?:d[ao]s?\s+|de\s+)?\$?([a-z][a-z0-9]{1,5})\b/g)].map((x) =>
      x[1].toUpperCase(),
    );
    const usDollar = [...t.matchAll(/\$\s*([A-Za-z]{1,6})\b/g)].map((x) => x[1].toUpperCase());
    const primary = [...new Set([...br, ...upper, ...usWord, ...usDollar])].filter(
      (s) => s.length >= 2 && !STOP.has(s),
    );

    if (primary.length) {
      // tickers extras depois do primeiro (ex.: "PETR4 e AAPL", "vale3 e msft")
      const tokens = t.split(/[^A-Za-z0-9.]+/).filter(Boolean);
      const firstIdx = tokens.findIndex((tok) => primary.includes(tok.toUpperCase()));
      // só aceita ticker extra depois de conector ("PETR4 e AAPL"), evitando palavras soltas
      const extra = [];
      if (firstIdx >= 0) {
        for (let i = firstIdx; i < tokens.length - 1; i++) {
          if (!['e', 'and', '&', 'ou', 'or', '+'].includes(tokens[i].toLowerCase())) continue;
          const up = tokens[i + 1].replace(/\.SA$/i, '').toUpperCase();
          if (up.length >= 2 && up.length <= 6 && /^[A-Z][A-Z0-9]*$/.test(up) && !STOP.has(up)) {
            extra.push(up);
          }
        }
      }
      const symbols = [...new Set([...primary, ...extra])].slice(0, 6);
      return { name: 'stocks', args: { symbols: symbols.join(',') } };
    }
  }

  // 6. ler arquivo
  m = t.match(/\b(?:ler|leia|mostre|read|show)\s+(?:o\s+|a\s+)?(?:arquivo\s+)?["']?([A-Za-z]:\\[^"'\n]+)["']?/i);
  if (m) return { name: 'read-file', args: { path: m[1].trim() } };

  return null;
}

/** Executa a ferramenta no backend local e devolve um resumo para a UI. */
async function runTool(tool) {
  if (!tool) return null;
  const offline = {
    name: tool.name,
    ok: false,
    summary: 'backend local (porta 8000) fora do ar',
    detail: null,
  };

  if (tool.name === 'exec') {
    const r = await backendCall('POST', '/exec', { cmd: tool.args.cmd }, 35000);
    if (!r) return offline;
    return {
      name: 'exec',
      ok: !r.error,
      summary: r.error ? `erro: ${r.error}` : `ok: ${(r.output || '(sem saída)').slice(0, 160)}`,
      detail: r,
    };
  }

  if (tool.name === 'stocks') {
    const r = await backendCall('GET', `/stocks?symbols=${encodeURIComponent(tool.args.symbols)}`, null, 20000);
    if (!r) return offline;
    const list = (r.results || [])
      .map((s) =>
        s.error
          ? `${s.symbol}: indisponível (${s.error})`
          : `${s.symbol}: ${s.price} ${s.currency} (${s.change_percent > 0 ? '+' : ''}${s.change_percent}%)`,
      )
      .join(' | ');
    return { name: 'stocks', ok: !!(r.results || []).length, summary: list || 'sem resultados', detail: r };
  }

  if (tool.name === 'currencies') {
    const r = await backendCall('GET', '/currencies', null, 20000);
    if (!r || !r.rates) return offline;
    const list = r.rates
      .map((x) => `${x.pair}: ${x.bid.toFixed(2)} (${x.change_percent > 0 ? '+' : ''}${x.change_percent}%)`)
      .join(' | ');
    return { name: 'currencies', ok: true, summary: list, detail: r };
  }

  if (tool.name === 'sysinfo') {
    const r = await backendCall('GET', '/sysinfo', null, 10000);
    if (!r || r.cpu === undefined) return offline;
    const summary = `CPU ${r.cpu.percent}% · RAM ${r.ram.percent}% (${r.ram.used_gb}/${r.ram.total_gb} GB) · Disco ${r.disk.percent}% (${r.disk.used_gb}/${r.disk.total_gb} GB)`;
    return { name: 'sysinfo', ok: true, summary, detail: r };
  }

  if (tool.name === 'read-file') {
    const r = await backendCall('POST', '/read-file', { path: tool.args.path }, 12000);
    if (!r) return offline;
    if (r.error) return { name: 'read-file', ok: false, summary: `erro: ${r.error}`, detail: r };
    const preview = String(r.content || '').slice(0, 1200);
    return { name: 'read-file', ok: true, summary: `${r.path} (${r.size} bytes)`, detail: { ...r, content: preview } };
  }

  if (tool.name === 'power') {
    const action = String(tool.args.action || 'shutdown');
    const delay = Number(tool.args.delay ?? 30);
    if (!tool.args.confirmed) {
      // segurança: nada de desligar sem um "sim" explícito do Comandante
      setPendingPower(action, delay);
      return {
        name: 'power',
        ok: true,
        summary:
          `AGUARDANDO CONFIRMAÇÃO para ${action} em ${delay}s — NADA foi executado. ` +
          'Pergunte ao Comandante se pode prosseguir e só execute depois do "sim".',
        detail: { pending_confirmation: true, action, delay },
      };
    }
    const r = await backendCall(
      'POST',
      '/power',
      { action, delay, confirmed: true, dry_run: process.env.JARVIS_POWER_DRY_RUN === '1' },
      30000,
    );
    if (!r) return offline;
    if (r.error) return { name: 'power', ok: false, summary: `erro: ${r.error}`, detail: r };
    if (r.dry_run) {
      return {
        name: 'power',
        ok: true,
        summary: `MODO SIMULAÇÃO (JARVIS_POWER_DRY_RUN=1): ${action} NÃO foi executado`,
        detail: r,
      };
    }
    const summary = r.delay
      ? `${r.action} agendado em ${r.delay}s (cancele com "cancela o desligamento")`
      : `${r.action} executado`;
    return { name: 'power', ok: !!r.ok, summary, detail: r };
  }

  if (tool.name === 'power-cancel') {
    const r = await backendCall('POST', '/power/cancel', {}, 20000);
    if (!r) return offline;
    return {
      name: 'power-cancel',
      ok: !!r.ok,
      summary: r.ok ? 'desligamento cancelado' : `nada a cancelar: ${r.output || r.error || ''}`,
      detail: r,
    };
  }

  if (tool.name === 'kill') {
    let target = String(tool.args.name || '').trim();
    const mapped = APP_MAP[target.toLowerCase()];
    if (mapped) {
      const last = mapped.replace(/\\/g, '/').split('/').pop().split(/\s+/).pop();
      target = last.toLowerCase().endsWith('.exe') ? last.slice(0, -4) : last;
    }
    const r = await backendCall('POST', '/kill', { name: target, force: tool.args.force !== false }, 40000);
    if (!r) return offline;
    return {
      name: 'kill',
      ok: !!r.ok,
      summary: r.ok ? `${r.name} encerrado` : `não encerrei ${r.name}: ${String(r.output || '').slice(0, 120)}`,
      detail: r,
    };
  }

  if (tool.name === 'processes') {
    const r = await backendCall('GET', '/processes?limit=10', null, 25000);
    if (!r || !r.processes) return offline;
    const list = r.processes.slice(0, 10).map((p) => `${p.name} (${p.ram_mb} MB)`).join(' | ');
    return { name: 'processes', ok: true, summary: list || 'sem dados', detail: r };
  }

  if (tool.name === 'news') {
    const r = await backendCall(
      'GET',
      `/news?topic=${encodeURIComponent(tool.args.topic || 'geral')}&limit=${Number(tool.args.limit || 5)}`,
      null,
      30000,
    );
    if (!r) return offline;
    if (r.error) return { name: 'news', ok: false, summary: `erro: ${r.error}`, detail: r };
    // títulos já vêm limpos do backend (titulo/fonte/resumo, sem link): o modelo só sumariza
    const list = (r.items || []).map((i) => String(i.titulo || i.title || '').trim()).filter(Boolean).join(' • ');
    return { name: 'news', ok: !!(r.items || []).length, summary: list || 'sem notícias', detail: r };
  }

  if (tool.name === 'agenda-add') {
    if (!String(tool.args.datetime || '').trim()) {
      return {
        name: 'agenda-add',
        ok: false,
        summary: "informe a data e a hora do lembrete (ex.: 'amanhã às 15h')",
        detail: null,
      };
    }
    const r = await backendCall(
      'POST',
      '/agenda/add',
      {
        title: tool.args.title || '',
        datetime: tool.args.datetime || '',
        description: tool.args.description || '',
      },
      20000,
    );
    if (!r) return offline;
    if (r.error) return { name: 'agenda-add', ok: false, summary: `erro: ${r.error}`, detail: r };
    const ev = r.event || {};
    return { name: 'agenda-add', ok: true, summary: `lembrete "${ev.title}" para ${ev.datetime}`, detail: r };
  }

  if (tool.name === 'agenda-list') {
    const r = await backendCall('GET', '/agenda/list', null, 20000);
    if (!r || !r.events) return offline;
    if (!r.events.length) return { name: 'agenda-list', ok: true, summary: 'agenda vazia — nenhum evento futuro', detail: r };
    const list = r.events.slice(0, 10).map((e) => `${e.datetime}: ${e.title}`).join(' | ');
    return { name: 'agenda-list', ok: true, summary: list, detail: r };
  }

  if (tool.name === 'agenda-check') {
    const r = await backendCall(
      'GET',
      `/agenda/check?window=${Number(tool.args.window || 5)}`,
      null,
      20000,
    );
    if (!r || !r.events) return offline;
    if (!r.events.length) return { name: 'agenda-check', ok: true, summary: 'nenhum lembrete nos próximos minutos', detail: r };
    const list = r.events.map((e) => `${e.datetime}: ${e.title}`).join(' | ');
    return { name: 'agenda-check', ok: true, summary: list, detail: r };
  }

  if (tool.name === 'agenda-delete') {
    const r = await backendCall('DELETE', `/agenda/${encodeURIComponent(String(tool.args.id || ''))}`, null, 20000);
    if (!r) return offline;
    if (r.error) return { name: 'agenda-delete', ok: false, summary: `erro: ${r.error}`, detail: r };
    return { name: 'agenda-delete', ok: true, summary: `evento removido (${r.removed})`, detail: r };
  }

  return null;
}

/** A ferramenta rodou mas não trouxe nada? (evita o modelo preencher com suposição) */
const EMPTY_CHECKS = {
  'agenda-list': ['events', 'a agenda está vazia — nenhum evento cadastrado'],
  'agenda-check': ['events', 'não há lembretes nos próximos minutos'],
  news: ['items', 'nenhuma notícia foi retornada'],
  processes: ['processes', 'nenhum processo foi retornado'],
  stocks: ['results', 'nenhuma cotação foi retornada'],
  'agenda-delete': ['removed', 'nenhum evento foi removido'],
};

function isEmptyResult(tool, result) {
  const spec = EMPTY_CHECKS[tool.name];
  if (!spec) return false;
  const detail = result.detail || {};
  return !detail[spec[0]];
}

/** Contexto injetado no prompt para o modelo responder com dados reais. */
function toolContext(tool, result) {
  let head =
    `[RESULTADO DA FERRAMENTA "${tool.name}" — DADOS REAIS, ÚNICA FONTE VÁLIDA]\n` +
    JSON.stringify(result.detail ?? { summary: result.summary }).slice(0, 4000) +
    '\n';
  if (isEmptyResult(tool, result)) {
    const hint = EMPTY_CHECKS[tool.name][1];
    head +=
      `[RESULTADO VAZIO] ${hint}. NÃO invente nada: diga que não há nada registrado ` +
      'ou que não há esse dado no momento.\n';
  }
  if (result.detail && result.detail.pending_confirmation) {
    head +=
      '[NÃO EXECUTADO] Nada foi executado: a ação está apenas aguardando confirmação. ' +
      'NUNCA diga que o desligamento foi agendado, programado ou iniciado. ' +
      'Diga que nada foi executado e pergunte se o Comandante confirma — só o "sim" executa.\n';
  }
  return (
    head +
    'REGRAS: use APENAS os dados acima. Não invente números, eventos, cotações nem status. ' +
    'Se o resultado estiver vazio ou ausente, diga que não há nada registrado — nunca preencha com suposições. ' +
    'Responda em português, curto, no estilo JARVIS.'
  );
}

/* ─────────────────────────────────────────────────
   Agent: tool calling de verdade (o modelo decide quando chamar)
   ───────────────────────────────────────────────── */
const MAX_TOOL_ROUNDS = 5;

const TOOLS_SCHEMA = [
  { type: 'function', function: { name: 'exec', description: 'Executa um comando no Windows (shell).', parameters: { type: 'object', properties: { cmd: { type: 'string', description: 'comando, ex.: start chrome' } }, required: ['cmd'] } } },
  { type: 'function', function: { name: 'read_file', description: 'Lê o conteúdo de um arquivo local.', parameters: { type: 'object', properties: { path: { type: 'string' } }, required: ['path'] } } },
  { type: 'function', function: { name: 'sysinfo', description: 'CPU, RAM, disco e uptime reais da máquina.', parameters: { type: 'object', properties: {} } } },
  { type: 'function', function: { name: 'list_processes', description: 'Lista os processos que mais consomem memória.', parameters: { type: 'object', properties: {} } } },
  { type: 'function', function: { name: 'kill', description: 'Encerra um programa pelo nome (ex.: chrome).', parameters: { type: 'object', properties: { name: { type: 'string' }, force: { type: 'boolean' } }, required: ['name'] } } },
  { type: 'function', function: { name: 'power', description: 'Desliga, reinicia, hiberna ou suspende o computador. A execução SEMPRE exige confirmação do usuário.', parameters: { type: 'object', properties: { action: { type: 'string', enum: ['shutdown', 'restart', 'hibernate', 'sleep'] }, delay: { type: 'integer' } }, required: ['action'] } } },
  { type: 'function', function: { name: 'power_cancel', description: 'Cancela um desligamento/reinício agendado.', parameters: { type: 'object', properties: {} } } },
  { type: 'function', function: { name: 'news', description: 'Últimas notícias (RSS do G1 ou Google News).', parameters: { type: 'object', properties: { topic: { type: 'string' }, limit: { type: 'integer' } } } } },
  { type: 'function', function: { name: 'agenda_add', description: 'Cria um lembrete na agenda.', parameters: { type: 'object', properties: { title: { type: 'string' }, datetime: { type: 'string', description: 'AAAA-MM-DD HH:MM' }, description: { type: 'string' } }, required: ['title', 'datetime'] } } },
  { type: 'function', function: { name: 'agenda_list', description: 'Lista os eventos futuros da agenda.', parameters: { type: 'object', properties: {} } } },
  { type: 'function', function: { name: 'agenda_delete', description: 'Remove um evento da agenda pelo id ou pelo título.', parameters: { type: 'object', properties: { id: { type: 'string' } }, required: ['id'] } } },
  { type: 'function', function: { name: 'agenda_check', description: 'Eventos que começam nos próximos minutos.', parameters: { type: 'object', properties: { window: { type: 'integer' } } } } },
  { type: 'function', function: { name: 'stocks', description: 'Cotação de ações (PETR4, AAPL...).', parameters: { type: 'object', properties: { symbols: { type: 'string', description: 'separados por vírgula' } }, required: ['symbols'] } } },
  { type: 'function', function: { name: 'currencies', description: 'Cotações de moedas (USD/BRL, EUR/BRL, USD/EUR).', parameters: { type: 'object', properties: {} } } },
];

const TOOL_ALIASES = {
  exec: 'exec',
  read_file: 'read-file',
  sysinfo: 'sysinfo',
  list_processes: 'processes',
  kill: 'kill',
  power: 'power',
  power_cancel: 'power-cancel',
  news: 'news',
  agenda_add: 'agenda-add',
  agenda_list: 'agenda-list',
  agenda_delete: 'agenda-delete',
  agenda_check: 'agenda-check',
  stocks: 'stocks',
  currencies: 'currencies',
};

// desligar/reiniciar/hibernar/suspender só acontece depois de um "sim" explícito
let pendingPower = null;
// tempo máximo para o Comandante confirmar (evita "sim" tardio e acidental)
const POWER_CONFIRM_TTL_MS = 120000;

function setPendingPower(action, delay) {
  pendingPower = { action, delay, at: Date.now() };
}

/** Devolve os args do desligamento pendente quando o Comandante confirma. */
function takePowerConfirmation(messages) {
  if (!pendingPower) return null;
  if (Date.now() - (pendingPower.at || 0) > POWER_CONFIRM_TTL_MS) {
    pendingPower = null; // pedido expirado: exigimos uma nova ordem explícita
    return null;
  }
  const lastUser = [...messages].reverse().find((m) => m.role === 'user');
  const text = String((lastUser && lastUser.content) || '');
  if (/\b(n[ãa]o|cancela|cancelar|aborta|abortar|esquece|esquecer)\b/i.test(text)) {
    pendingPower = null;
    return null;
  }
  if (/\b(sim|confirmo|confirmado|pode|manda|autorizo|ok|certo|claro|isso|positivo|prossiga|prossegue|vai)\b/i.test(text)) {
    const { action, delay } = pendingPower;
    pendingPower = null;
    return { action, delay, confirmed: true };
  }
  return null;
}

/**
 * Consome a resposta do provedor (SSE ou JSON) e devolve o texto e as
 * tool_calls acumuladas. `onDelta` recebe os pedaços de texto conforme chegam.
 */
async function collectCompletion(upstream, onDelta) {
  const calls = new Map();
  let text = '';
  const addCall = (tc) => {
    if (!tc) return;
    const idx = Number(tc.index ?? 0);
    const slot = calls.get(idx) || { id: '', name: '', arguments: '' };
    if (tc.id) slot.id = tc.id;
    if (tc.function && tc.function.name) slot.name = tc.function.name;
    if (tc.function && tc.function.arguments) slot.arguments += tc.function.arguments;
    calls.set(idx, slot);
  };

  if (upstream.contentType.includes('application/json')) {
    let raw = '';
    upstream.res.on('data', (c) => (raw += c));
    await new Promise((resolve) => {
      upstream.res.on('end', resolve);
      upstream.res.on('error', resolve);
    });
    try {
      const j = JSON.parse(raw);
      const choice = (j.choices && j.choices[0]) || {};
      const msg = choice.message || {};
      text = msg.content || '';
      for (const tc of msg.tool_calls || []) addCall(tc);
    } catch {
      /* resposta ilegível */
    }
    if (text) onDelta(text);
    return { text, calls };
  }

  await new Promise((resolve) => {
    let buf = '';
    upstream.res.on('data', (chunk) => {
      buf += chunk.toString('utf8');
      let idx;
      while ((idx = buf.indexOf('\n')) !== -1) {
        const line = buf.slice(0, idx).trimEnd();
        buf = buf.slice(idx + 1);
        if (!line.startsWith('data:')) continue;
        const data = line.slice(5).trim();
        if (data === '[DONE]') continue;
        let j;
        try {
          j = JSON.parse(data);
        } catch {
          continue;
        }
        if (j.error) continue;
        const delta = (j.choices && j.choices[0] && j.choices[0].delta) || {};
        const t = delta.content || delta.reasoning_content;
        if (t) {
          text += t;
          onDelta(t);
        }
        for (const tc of delta.tool_calls || []) addCall(tc);
      }
    });
    upstream.res.on('end', resolve);
    upstream.res.on('error', resolve);
  });
  return { text, calls };
}

/** Resposta pronta quando não há provedor de LLM configurado. */
function toolFallbackText(tool, result) {
  if (!result.ok && !result.detail) return `⚠ ${result.summary}`;
  if (result.ok && result.summary) return `✔ ${tool.name}: ${result.summary}`;
  return `⚠ ${tool.name}: ${result.summary}`;
}

function buildAttempts(cfg) {
  const attempts = [];
  if (cfg.groqKey) {
    const models = cfg.groqModel ? [cfg.groqModel] : GROQ_MODELS;
    for (const model of models) {
      attempts.push({
        provider: 'groq',
        model,
        url: GROQ_URL,
        headers: { Authorization: `Bearer ${cfg.groqKey}` },
        timeout: 30000,
        fatalStatuses: [401, 403],
      });
    }
  }
  return attempts;
}

async function handleChat(req, res) {
  let payload;
  try {
    payload = JSON.parse((await readBody(req)) || '{}');
  } catch (e) {
    res.writeHead(400, { 'Content-Type': 'application/json', ...securityHeaders() });
    res.end(JSON.stringify({ error: e.message }));
    return;
  }

  // rate limit: no máximo 30 chamadas por minuto
  if (chatRateLimited()) {
    res.writeHead(429, { 'Content-Type': 'application/json', ...securityHeaders() });
    res.end(JSON.stringify({ error: 'Muitas chamadas seguidas, Comandante. Aguarde um instante.' }));
    return;
  }

  // tamanho máximo da mensagem do usuário
  const incoming = Array.isArray(payload.messages) ? payload.messages : [];
  for (const m of incoming) {
    if (m && typeof m.content === 'string' && m.content.length > MAX_CHAT_INPUT) {
      res.writeHead(413, { 'Content-Type': 'application/json', ...securityHeaders() });
      res.end(JSON.stringify({ error: `Mensagem muito longa (máximo ${MAX_CHAT_INPUT} caracteres).` }));
      return;
    }
  }

  // o prompt de personalidade é sempre o nosso (ignora o que o front mandar)
  const messages = incoming.filter((m) => m && m.role !== 'system').slice(-30);
  messages.unshift({ role: 'system', content: SYSTEM_PROMPT });

  // visualizador 3D: "me mostra um carro" abre o navegador e responde com frase fixa
  const visLastUser = [...messages].reverse().find((m) => m && m.role === 'user');
  const visObj = detectVisualize3D(visLastUser ? visLastUser.content : '');
  if (visObj) {
    res.writeHead(200, {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      'X-Accel-Buffering': 'no',
      ...securityHeaders(),
    });
    const vis = await backendCall('POST', '/visualize-3d', { prompt: visObj }, 150000);
    const ok = !!(vis && vis.ok);
    sse(res, 'tool', {
      name: 'visualize-3d',
      ok,
      summary: ok ? `${visObj} (${(vis && vis.size) || 0} bytes)` : `${visObj} — falhou`,
    });
    const text = ok
      ? (vis.message || `Pronto, Comandante. Abrindo o ${visObj} no navegador.`)
      : `Não consegui abrir a visualização 3D, Comandante. ${(vis && vis.error) || 'o backend de ferramentas não respondeu.'}`;
    sse(res, 'start', { provider: 'jarvis-3d', model: 'visualize-3d' });
    for (let i = 0; i < text.length; i += 28) sse(res, 'delta', { t: text.slice(i, i + 28) });
    sse(res, 'done', { provider: 'jarvis-3d', model: 'visualize-3d' });
    res.end();
    return;
  }

  res.writeHead(200, {
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
    'X-Accel-Buffering': 'no',
  });

  const cfg = loadConfig();
  const attempts = buildAttempts(cfg);

  // confirmação pendente de desligamento: um "sim" do Comandante executa de verdade
  const confirmed = takePowerConfirmation(messages);
  let confirmedResult = null;
  if (confirmed) {
    confirmedResult = await runTool({ name: 'power', args: confirmed });
    if (confirmedResult) {
      messages.push({ role: 'system', content: toolContext({ name: 'power' }, confirmedResult) });
    }
  }
  if (confirmedResult) {
    sse(res, 'tool', { name: 'power', ok: confirmedResult.ok, summary: confirmedResult.summary });
  }

  // ── ferramenta local: só sem provedor (o agente cuida disso quando há chave) ──
  let tool = null;
  let toolResult = null;
  const lastUser = [...messages].reverse().find((m) => m.role === 'user');
  const userText = String((lastUser && lastUser.content) || '');

  // desligar/reiniciar/cancelar não dependem do humor do modelo: a intenção é
  // detectada aqui e o pedido já fica registrado (power nunca executa sozinho).
  const powerDone = !!confirmedResult; // já executou nesta ordem: não rearmar
  if (attempts.length && !confirmed) {
    const critical = detectTool(userText);
    if (critical && (critical.name === 'power' || critical.name === 'power-cancel')) {
      const cresult = await runTool(critical);
      if (cresult) {
        sse(res, 'tool', { name: cresult.name, ok: cresult.ok, summary: cresult.summary });
        messages.push({ role: 'system', content: toolContext(critical, cresult) });
      }
    }
  }

  if (!attempts.length) {
    tool = detectTool(userText);
    if (tool) toolResult = await runTool(tool);
  }

  if (!attempts.length) {
    // Sem chave de LLM: se a ferramenta rodou, devolve o resultado real.
    if (tool && toolResult) {
      sse(res, 'tool', {
        name: toolResult.name,
        ok: toolResult.ok,
        summary: toolResult.summary,
      });
      const text = toolFallbackText(tool, toolResult);
      sse(res, 'start', { provider: 'local-tools', model: `backend:${tool.name}` });
      for (const chunk of text.match(/[\s\S]{1,28}/g) || [text]) {
        sse(res, 'delta', { t: chunk });
        await new Promise((r) => setTimeout(r, 16));
      }
      sse(res, 'done', { provider: 'local-tools', model: `backend:${tool.name}` });
      res.end();
      return;
    }
    sse(res, 'error', {
      message:
        'Nenhuma chave da Groq configurada. Abra as Configurações (engrenagem) e cole sua chave (console.groq.com/keys).',
      tried: [],
    });
    res.write('event: done\ndata: {}\n\n');
    res.end();
    return;
  }

  const tried = [];
  let closed = false;
  res.on('close', () => (closed = true));

  for (let i = 0; i < attempts.length; i++) {
    const a = attempts[i];
    const isLast = i === attempts.length - 1;
    const conv = messages.slice();
    let answered = false;
    let failed = false;
    let fatal = false;
    let started = false;

    // agent loop: o modelo decide as ferramentas, nós executamos, e repetimos (máx. 5)
    for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
      let upstream;

      try {
        upstream = await callUpstream({
          url: a.url,
          headers: a.headers,
          timeout: a.timeout,
          body: {
            model: a.model,
            messages: conv,
            stream: true,
            temperature: payload.temperature ?? 0.7,
            tools: TOOLS_SCHEMA,
            tool_choice: 'auto',
          },
        });
      } catch (e) {
        tried.push(`${a.provider}/${a.model}: ${e.message}`);
        failed = true;
        // 401/403 => token inválido, não adianta tentar outros modelos do mesmo provedor.
        if (e.status && a.fatalStatuses.includes(e.status)) fatal = true;
        break;
      }

      if (closed) {
        upstream.res.resume();
        return;
      }

      // Provedor escolhido — anuncia antes do primeiro delta.
      if (!started) {
        sse(res, 'start', { provider: a.provider, model: a.model });
        started = true;
      }

      // sanitiza (sem tags/scripts) e limita a resposta a 10.000 caracteres
      let outChars = 0;
      const { text, calls } = await collectCompletion(upstream, (t) => {
        if (closed) return;
        const clean = stripHtml(t);
        const room = MAX_CHAT_OUTPUT - outChars;
        if (!clean || room <= 0) return;
        const chunk = clean.length > room ? clean.slice(0, room) : clean;
        outChars += chunk.length;
        sse(res, 'delta', { t: chunk });
      });

      if (!calls.size) {
        answered = true;
        break;
      }

      const ordered = [...calls.entries()].sort((x, y) => x[0] - y[0]).map(([, v]) => v);
      conv.push({
        role: 'assistant',
        content: text || '',
        tool_calls: ordered.map((c, k) => ({
          id: c.id || `call_${k}`,
          type: 'function',
          function: { name: c.name, arguments: c.arguments || '{}' },
        })),
      });

      for (const [k, c] of ordered.entries()) {
        let args = {};
        try {
          args = JSON.parse(c.arguments || '{}');
        } catch {
          args = {};
        }
        if (!args || typeof args !== 'object') args = {};
        // segurança: o modelo NUNCA confirma por conta própria — só o fluxo de
        // confirmação (um "sim" do Comandante) pode ligar `confirmed`.
        delete args.confirmed;
        const toolName = TOOL_ALIASES[c.name] || c.name;
        const result =
          toolName === 'power' && powerDone
            ? {
                // uma ordem = no máximo um desligamento; não rearma o pedido
                name: 'power',
                ok: true,
                summary:
                  'o desligamento já foi registrado nesta mesma ordem — NÃO chame a ferramenta de novo; ' +
                  'apenas confirme ao Comandante',
                detail: { already_registered: true },
              }
            : await runTool({ name: toolName, args });
        if (!result) {
          conv.push({ role: 'tool', tool_call_id: c.id || `call_${k}`, content: 'ferramenta indisponível' });
          continue;
        }
        if (!closed) sse(res, 'tool', { name: result.name, ok: result.ok, summary: result.summary });
        conv.push({
          role: 'tool',
          tool_call_id: c.id || `call_${k}`,
          content: (
            JSON.stringify(result.detail ?? { summary: result.summary }) +
            (result.detail && result.detail.pending_confirmation
              ? '\n[NÃO EXECUTADO] nada aconteceu ainda: está aguardando confirmação. Nunca diga que foi agendado. Peça o "sim" ao Comandante.'
              : '') +
            '\nUse APENAS estes dados. Se estiver vazio, diga que não há nada registrado — não invente.'
          ).slice(0, 4200),
        });
      }
    }

    if (answered) {
      if (!closed) sse(res, 'done', { provider: a.provider, model: a.model });
      res.end();
      return;
    }
    if (failed && !fatal) {
      if (isLast) break;
      continue; // tenta o próximo modelo
    }
    if (fatal) break;

    // esgotou as rodadas de ferramentas sem resposta final
    if (!closed) {
      sse(res, 'delta', { t: ' Não consegui concluir com as ferramentas disponíveis, Comandante.' });
      sse(res, 'done', { provider: a.provider, model: a.model });
    }
    res.end();
    return;
  }

  if (!closed) {
    sse(res, 'error', {
      message: `Todos os provedores falharam. Últimos erros: ${tried.slice(-3).join(' | ')}`,
      tried,
    });
    res.write('event: done\ndata: {}\n\n');
    res.end();
  }
}

async function handleStatus(req, res) {
  const cfg = loadConfig();
  const body = JSON.stringify({
    groq: { configured: !!cfg.groqKey, key: mask(cfg.groqKey), model: cfg.groqModel || 'auto' },
    continuous_listen_minutes: cfg.continuous_listen_minutes,
  });
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', ...securityHeaders() });
  res.end(body);
}

async function handleConfigMasked(req, res) {
  const cfg = loadConfig();
  // nunca devolve o segredo: só a chave mascarada
  res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', ...securityHeaders() });
  res.end(
    JSON.stringify({
      groqKey: mask(cfg.groqKey),
      groqModel: cfg.groqModel,
      continuous_listen_minutes: cfg.continuous_listen_minutes,
      configured: !!cfg.groqKey,
    }),
  );
}

async function handleConfig(req, res) {
  const cfg = loadConfig();
  if (req.method === 'GET') {
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', ...securityHeaders() });
    res.end(JSON.stringify({ groqKey: cfg.groqKey, groqModel: cfg.groqModel, continuous_listen_minutes: cfg.continuous_listen_minutes }));
    return;
  }
  if (req.method === 'POST') {
    let body;
    try {
      body = JSON.parse((await readBody(req)) || '{}');
    } catch (e) {
      res.writeHead(400, { 'Content-Type': 'application/json', ...securityHeaders() });
      res.end(JSON.stringify({ error: e.message }));
      return;
    }
    const next = Object.assign({}, cfg);
    if (typeof body.groqKey === 'string') {
      const key = body.groqKey.trim();
      // nunca grava um placeholder mascarado por cima da chave real
      if (!looksMasked(key)) next.groqKey = key;
    }
    if (typeof body.groqModel === 'string') next.groqModel = body.groqModel.trim().slice(0, 120);
    if (body.continuous_listen_minutes !== undefined && body.continuous_listen_minutes !== null) {
      next.continuous_listen_minutes = clampMinutes(body.continuous_listen_minutes);
    }
    saveConfig(next);
    res.writeHead(200, { 'Content-Type': 'application/json; charset=utf-8', ...securityHeaders() });
    res.end(JSON.stringify({ ok: true, continuous_listen_minutes: next.continuous_listen_minutes }));
    return;
  }
  res.writeHead(405).end();
}

function serveStatic(req, res) {
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  } catch {
    pathname = '/';
  }
  if (pathname === '/') pathname = '/index.html';
  const filePath = path.normalize(path.join(PUBLIC_DIR, pathname));
  if (!filePath.startsWith(PUBLIC_DIR)) {
    res.writeHead(403).end('Forbidden');
    return;
  }
  fs.readFile(filePath, (err, data) => {
    if (err) {
      res.writeHead(404, { 'Content-Type': 'text/plain; charset=utf-8' });
      res.end('404');
      return;
    }
    const ext = path.extname(filePath).toLowerCase();
    res.writeHead(200, {
      'Content-Type': MIME[ext] || 'application/octet-stream',
      'Cache-Control': ext === '.html' ? 'no-cache' : 'public, max-age=300',
    });
    res.end(data);
  });
}

const server = http.createServer(async (req, res) => {
  try {
    // headers de segurança + CORS restrito em todas as respostas
    for (const [k, v] of Object.entries({ ...securityHeaders(), ...corsHeaders(req) })) res.setHeader(k, v);
    if (req.method === 'OPTIONS') {
      res.writeHead(204);
      res.end();
      return;
    }
    if (req.url.startsWith('/api/chat') && req.method === 'POST') return await handleChat(req, res);
    if (req.url.startsWith('/api/status') && req.method === 'GET') return await handleStatus(req, res);
    if (req.url.startsWith('/api/config/masked')) return await handleConfigMasked(req, res);
    if (req.url.startsWith('/api/config')) return await handleConfig(req, res);
    if (req.url.startsWith('/api/')) {
      res.writeHead(404, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ error: 'not found' }));
      return;
    }
    return serveStatic(req, res);
  } catch (e) {
    console.error('[erro]', e);
    if (!res.headersSent) {
      res.writeHead(500, { 'Content-Type': 'application/json; charset=utf-8' });
    }
    try {
      res.end(JSON.stringify({ error: e.message }));
    } catch {
      /* resposta já fechada */
    }
  }
});

server.listen(PORT, HOST, () => {
  const cfg = loadConfig();
  console.log(`JARVIS online em http://${HOST}:${PORT}`);
  console.log(`  Groq:    ${cfg.groqKey ? 'configurada' : 'não configurada'}`);

  healthProbe();
});

/** Informa no boot se o backend Python (ferramentas) está no ar. */
async function healthProbe() {
  const h = await backendCall('GET', '/health', null, 4000);
  if (h && h.ok) {
    console.log(`  Backend: ok em ${BACKEND_URL} (Piper: ${h.piper_ready ? 'pronto' : h.piper_error || 'pendente'})`);
  } else {
    console.log(`  Backend: OFFLINE (${BACKEND_URL}) — ferramentas desativadas até subir o FastAPI`);
  }
}
