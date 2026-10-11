/* ═══════════════════════════════════════════════════════════
   JARVIS COMMAND CENTER — só dados reais
   Chat: Groq.  Ferramentas e voz: backend Python (porta 8000).
   ═══════════════════════════════════════════════════════════ */
'use strict';

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
/* o HUD enxuto tem só a sidebar + o globo: os painéis removidos não existem mais,
   então o listener só é registrado quando o elemento está na página */
const on = (sel, ev, fn) => { const el = $(sel); if (el) el.addEventListener(ev, fn); };
const BACKEND_URL = 'http://127.0.0.1:8000';
const LS_KEY = 'jarvis-settings';

/* ── configurações locais (voz/escuta) ─────────── */
const settings = Object.assign(
  // escuta contínua ligada por padrão: basta dizer "Jarvis"
  // rate = velocidade (maior = mais devagar); pitch = tom em semitons (negativo = mais grave)
  { ttsOn: true, rate: 1.35, pitch: -2, voice: '', ttsEngine: 'piper', wake: true, continuousMinutes: 5 },
  JSON.parse(localStorage.getItem(LS_KEY) || '{}'),
);
function saveLocal() {
  localStorage.setItem(LS_KEY, JSON.stringify(settings));
}

/* ── estado ────────────────────────────────────── */
const state = {
  sys: null,
  health: null,
  provider: { configured: false, model: 'auto' },
  history: [],          // mensagens enviadas no chat
  turns: 0,             // respostas do JARVIS
  tools: 0,             // ferramentas executadas
  cpuHist: [],          // histórico real desta sessão
  ramHist: [],
  events: [],           // eventos reais
  activity: [],         // execuções de ferramenta
  lastMarket: null,
  lastFx: null,
};

/* ── toast ─────────────────────────────────────── */
let toastTimer;
function toast(msg) {
  const el = $('#toast');
  el.textContent = msg;
  el.hidden = false;
  el.style.animation = 'none';
  void el.offsetWidth;
  el.style.animation = '';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), 3600);
}

/* ── eventos reais (feed) ──────────────────────── */
const ICONS = { info: '◈', ok: '✔', warn: '⚠', err: '✖', tool: '⌘', voice: '◉' };
const CLASS = { info: 'ico-blue', ok: 'ico-green', warn: 'ico-amber', err: 'ico-purple', tool: 'ico-cyan', voice: 'ico-cyan' };

function pushEvent(kind, title, detail) {
  const ev = { kind, title, detail, at: new Date() };
  state.events.unshift(ev);
  state.events = state.events.slice(0, 30);
  renderFeed();
  persistEvents();
}
function persistEvents() {
  try {
    localStorage.setItem(
      'jarvis-events',
      JSON.stringify(state.events.slice(0, 30).map((e) => ({ ...e, at: e.at.toISOString() }))),
    );
  } catch { /* sem storage */ }
}
function loadEvents() {
  try {
    const raw = JSON.parse(localStorage.getItem('jarvis-events') || '[]');
    state.events = raw.map((e) => ({ ...e, at: new Date(e.at) }));
  } catch { /* ignora */ }
}
function hm(d) {
  return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}
function renderFeed() {
  const ul = $('#feed');   // painel "Live Intelligence" removido do HUD enxuto
  if (!ul) return;
  ul.innerHTML = '';
  const list = state.events.slice(0, 8);
  if (!list.length) {
    ul.innerHTML = '<li><span class="f-ico ico-blue">◈</span><div class="f-body"><b>Sem eventos ainda</b><small>as ações reais aparecem aqui</small></div></li>';
    return;
  }
  for (const ev of list) {
    const tag = { info: 'INFO', ok: 'OK', warn: 'ALERTA', err: 'ERRO', tool: 'FERRAM', voice: 'VOZ' }[ev.kind] || 'INFO';
    const li = document.createElement('li');
    li.innerHTML = `
      <span class="f-ico ${CLASS[ev.kind] || 'ico-blue'}">${ICONS[ev.kind] || '◈'}</span>
      <div class="f-body"><b>${esc(ev.title)}</b><small>${esc(ev.detail || '')}</small></div>
      <span class="f-tag ${ev.kind === 'warn' || ev.kind === 'err' ? 'warn' : ev.kind === 'ok' ? 'live' : 'info'}">${tag}</span>`;
    ul.appendChild(li);
  }
}

/* ── atividade (execuções reais) ───────────────── */
function pushActivity(name, ok, summary) {
  state.activity.unshift({ name, ok, summary, at: new Date() });
  state.activity = state.activity.slice(0, 12);
  renderActivity();
}
function renderActivity() {
  const ul = $('#activity');   // painel de atividade removido do HUD enxuto
  if (!ul) return;
  ul.innerHTML = '';
  if (!state.activity.length) {
    ul.innerHTML = '<li class="tl-item"><span class="tl-time">--:--</span><div class="tl-body"><b>Nenhuma ação ainda</b><div class="tl-bar"><i style="--w:0%"></i></div></div><span class="tl-tag mut">—</span></li>';
    return;
  }
  for (const a of state.activity.slice(0, 4)) {
    const li = document.createElement('li');
    li.className = `tl-item ${a.ok ? 'done' : 'warn'}`;
    li.innerHTML = `
      <span class="tl-time">${hm(a.at)}</span>
      <div class="tl-body"><b>${esc(a.name)} — ${esc((a.summary || '').slice(0, 60))}</b>
        <div class="tl-bar"><i style="--w:${a.ok ? 100 : 40}%"></i></div>
      </div>
      <span class="tl-tag ${a.ok ? '' : 'mut'}">${a.ok ? 'OK' : 'falha'}</span>`;
    ul.appendChild(li);
  }
}

/* ── boot ─────────────────────────────────────── */
(function boot() {
  const el = document.createElement('div');
  el.className = 'boot';
  el.innerHTML = `
    <div class="boot-title">JARVIS</div>
    <div class="boot-bar"><i></i></div>
    <div class="boot-log" id="bootLog"></div>`;
  document.body.appendChild(el);
  const lines = [
    '> verificando serviços locais...',
    '> lendo CPU, memória e disco...',
    '> carregando motor de voz...',
    '> pronto.',
  ];
  const log = $('#bootLog', el);
  lines.forEach((t, i) => setTimeout(() => {
    const d = document.createElement('div');
    d.textContent = t;
    log.appendChild(d);
  }, 220 + i * 240));
  setTimeout(() => el.classList.add('done'), 1300);
  setTimeout(() => el.remove(), 2100);
})();

/* ── relógio ───────────────────────────────────── */
(function clock() {
  const clockEl = $('#clock');
  const dateEl = $('#today');
  const days = ['domingo', 'segunda-feira', 'terça-feira', 'quarta-feira', 'quinta-feira', 'sexta-feira', 'sábado'];
  const months = ['janeiro', 'fevereiro', 'março', 'abril', 'maio', 'junho', 'julho', 'agosto', 'setembro', 'outubro', 'novembro', 'dezembro'];
  function tick() {
    const n = new Date();
    const pad = (v) => String(v).padStart(2, '0');
    clockEl.innerHTML = `${pad(n.getHours())}:${pad(n.getMinutes())}:<span class="sec">${pad(n.getSeconds())}</span>`;
    dateEl.textContent = `${days[n.getDay()]}, ${n.getDate()} de ${months[n.getMonth()]} de ${n.getFullYear()}`;
  }
  tick();
  setInterval(tick, 1000);
})();

/* ── estrelas de fundo ─────────────────────────── */
(function stars() {
  const c = $('#stars');
  const ctx = c.getContext('2d');
  let w, h, pts;
  function init() {
    w = c.width = innerWidth;
    h = c.height = innerHeight;
    pts = Array.from({ length: 80 }, () => ({
      x: Math.random() * w, y: Math.random() * h,
      r: Math.random() * 1.3 + 0.3, s: Math.random() * 0.22 + 0.04, p: Math.random() * 6.28,
    }));
  }
  init();
  addEventListener('resize', init);
  (function loop(t) {
    ctx.clearRect(0, 0, w, h);
    for (const p of pts) {
      p.y -= p.s;
      if (p.y < -4) { p.y = h + 4; p.x = Math.random() * w; }
      const tw = 0.45 + 0.55 * Math.abs(Math.sin(t / 900 + p.p));
      ctx.beginPath();
      ctx.arc(p.x, p.y, p.r, 0, 6.283);
      ctx.fillStyle = `rgba(140, 215, 255, ${tw * 0.75})`;
      ctx.fill();
    }
    requestAnimationFrame(loop);
  })(0);
})();

/* ── áudio reativo do globo (voz → bola) ─────────
   O globo 3D reage em tempo real ao áudio:
   - quando o usuário fala (microfone via getUserMedia)
   - quando o JARVIS fala (TTS do Piper)
   O navegador só libera o AudioContext depois de um gesto do usuário:
   qualquer clique/tecla na página chama resume(). Sem áudio disponível,
   o loop usa uma oscilação senoidal de reserva. */
let audioCtx = null;          // um único AudioContext para mic + TTS
let ttsAnalyser = null;       // análise da voz do JARVIS (TTS)
let micAnalyser = null;       // análise do microfone
let micAudioStream = null;    // stream do getUserMedia (só quando a escuta está ativa)
let audioData = null;         // Uint8Array reutilizado a cada frame
const AUDIO_FFT = 256;

function ensureAudioCtx() {
  if (audioCtx) return audioCtx;
  try {
    audioCtx = new (window.AudioContext || window.webkitAudioContext)();
  } catch {
    audioCtx = null;
  }
  return audioCtx;
}

/** Garante um AnalyserNode no AudioContext (um para o TTS, outro para o mic). */
function audioAnalyser(which) {
  const ac = ensureAudioCtx();
  if (!ac) return null;
  const slot = which === 'tts' ? ttsAnalyser : micAnalyser;
  if (slot) return slot;
  try {
    const node = ac.createAnalyser();
    node.fftSize = AUDIO_FFT;
    node.smoothingTimeConstant = 0.72;
    if (which === 'tts') ttsAnalyser = node;
    else micAnalyser = node;
    return node;
  } catch {
    return null;
  }
}

/** Manda o áudio do TTS pelo analisador sem cortar o som. */
function routeTtsAudio(el) {
  const ac = ensureAudioCtx();
  if (!ac) return;
  try {
    if (ac.state === 'suspended') ac.resume().catch(() => {});
    if (ac.state !== 'running') return;   // ainda sem permissão: toca normal, sem análise
    const node = audioAnalyser('tts');
    if (!node) return;
    const source = ac.createMediaElementSource(el);
    source.connect(node);
    node.connect(ac.destination);
  } catch { /* áudio segue no caminho normal */ }
}

/** Liga o microfone ao analisador (não conecta ao destination: evita eco). */
async function startMicAnalyser() {
  if (micAudioStream) return;
  let stream = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const ac = ensureAudioCtx();
    const node = ac ? audioAnalyser('mic') : null;
    if (!ac || !node) throw new Error('sem AudioContext');
    ac.createMediaStreamSource(stream).connect(node);
    micAudioStream = stream;
  } catch {
    try { if (stream) stream.getTracks().forEach((t) => t.stop()); } catch { /* ignora */ }
    micAudioStream = null;
  }
}

function stopMicAnalyser() {
  if (!micAudioStream) return;
  try { micAudioStream.getTracks().forEach((t) => t.stop()); } catch { /* ignora */ }
  micAudioStream = null;
}

/** Só liga o mic do globo quando a escuta está de fato ativa. */
function syncMicAnalyser() {
  if (settings.wake || continuousListening) startMicAnalyser();
  else stopMicAnalyser();
}

/** Nível atual (0..1) da fonte certa: TTS falando > microfone ouvindo. */
function audioLevel() {
  let node = null;
  if (window.isSpeaking) node = ttsAnalyser;
  else if (window.isListening) node = micAnalyser;
  const ac = audioCtx;
  if (node && ac && ac.state === 'running') {
    try {
      if (!audioData || audioData.length !== node.frequencyBinCount) {
        audioData = new Uint8Array(node.frequencyBinCount);
      }
      node.getByteFrequencyData(audioData);
      let sum = 0;
      for (let i = 0; i < audioData.length; i++) sum += audioData[i];
      return Math.min(1, sum / audioData.length / 130);
    } catch { /* cai no fallback */ }
  }
  // sem analisador: oscilação senoidal de reserva enquanto fala/ouve
  if (window.isSpeaking || window.isListening) {
    return 0.12 + 0.08 * Math.abs(Math.sin(performance.now() / 420));
  }
  return 0;
}

/* libera o AudioContext no primeiro gesto do usuário (política dos navegadores) */
for (const evName of ['pointerdown', 'keydown']) {
  addEventListener(evName, () => {
    const ac = ensureAudioCtx();
    if (ac && ac.state === 'suspended') ac.resume().catch(() => {});
  }, { passive: true });
}

/* ── globo 3D (Three.js): arrastar gira, scroll dá zoom, inércia, volta ao centro ── */
function globeThree(c) {
  const CYAN = 0x3fd0ff;
  const BLUE = 0x4d8dff;
  const AMBER = 0xffb648;
  const HOME = 5.4;
  const renderer = new THREE.WebGLRenderer({ canvas: c, alpha: true, antialias: true });
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 100);
  camera.position.set(0, 0, HOME);
  const group = new THREE.Group();
  scene.add(group);

  // núcleo brilhante + halo (o brilho sobe com a voz)
  const core = new THREE.Mesh(
    new THREE.SphereGeometry(1.1, 48, 48),
    new THREE.MeshBasicMaterial({ color: CYAN, transparent: true, opacity: 0.14 }),
  );
  group.add(core);
  const halo = new THREE.Mesh(
    new THREE.SphereGeometry(1.5, 32, 32),
    new THREE.MeshBasicMaterial({ color: BLUE, transparent: true, opacity: 0.05, side: THREE.BackSide }),
  );
  group.add(halo);

  // malhas girando em sentidos diferentes
  const wire = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1.32, 2),
    new THREE.MeshBasicMaterial({ color: CYAN, wireframe: true, transparent: true, opacity: 0.3 }),
  );
  group.add(wire);
  const wire2 = new THREE.Mesh(
    new THREE.IcosahedronGeometry(1.75, 1),
    new THREE.MeshBasicMaterial({ color: AMBER, wireframe: true, transparent: true, opacity: 0.13 }),
  );
  group.add(wire2);

  // três anéis orbitais concêntricos: interno (ciano, rápido), médio (azul) e externo (âmbar, lento)
  const RING = [
    { color: CYAN, radius: 1.95, speed: 0.0052, tilt: Math.PI / 2, yaw: 0 },
    { color: BLUE, radius: 2.32, speed: 0.0028, tilt: Math.PI / 2 + 0.45, yaw: 0.6 },
    { color: AMBER, radius: 2.72, speed: 0.0012, tilt: Math.PI / 2 + 0.95, yaw: 1.15 },
  ];
  const rings = RING.map((cfg) => {
    const ring = new THREE.Mesh(
      new THREE.TorusGeometry(cfg.radius, 0.009, 8, 200),
      new THREE.MeshBasicMaterial({ color: cfg.color, transparent: true, opacity: 0.55 }),
    );
    ring.rotation.x = cfg.tilt;
    ring.rotation.y = cfg.yaw;
    group.add(ring);
    return ring;
  });

  // Partículas ao redor (5000 pontos) com o buffer `position` guardando a POSIÇÃO DE
  // REPOUSO (a esfera). A deformação elástica sai de um uniform e é calculada no
  // vertexShader: nada de reescrever 15000 floats na CPU a cada frame.
  const N = 5000;
  const pos = new Float32Array(N * 3);
  const phase = new Float32Array(N);
  for (let i = 0; i < N; i++) {
    const r = 1.5 + Math.random() * 1.7;
    const th = Math.random() * Math.PI * 2;
    const ph = Math.acos(2 * Math.random() - 1);
    pos[i * 3] = r * Math.sin(ph) * Math.cos(th);
    pos[i * 3 + 1] = r * Math.cos(ph);
    pos[i * 3 + 2] = r * Math.sin(ph) * Math.sin(th);
    phase[i] = Math.random() * Math.PI * 2;
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  geo.setAttribute('aPhase', new THREE.BufferAttribute(phase, 1));

  // Partículas: posição de repouso guardada no buffer position (sem deformação).
  // vGlow espelha a reação do globo: pule (respiração) e voz crescendo.
  const pointsMat = new THREE.ShaderMaterial({
    uniforms: {
      uColor: { value: new THREE.Color(0xa8ecff) },
      uTime: { value: 0 },
      uSize: { value: 0.028 },
      uHalfHeight: { value: 400 },
      uOpacity: { value: 0.85 },
      uPulse: { value: 0.018 },
      uVoice: { value: 0 },
    },
    vertexShader: [
      'attribute float aPhase;',
      'uniform float uTime;',
      'uniform float uSize;',
      'uniform float uHalfHeight;',
      'uniform float uPulse;',
      'uniform float uVoice;',
      'varying float vGlow;',
      'void main() {',
      '  float breath = 1.0 + uPulse * sin(uTime * 1.5 + aPhase)',
      '                    + uVoice * 0.35 * sin(uTime * 6.0 + aPhase * 7.0);',
      '  vGlow = clamp(uVoice * 0.8 + uPulse * 0.5, 0.0, 1.0);',
      '  vec3 p = position * breath;',
      '  vec4 mv = modelViewMatrix * vec4(p, 1.0);',
      '  gl_PointSize = uSize * (1.0 + vGlow * 1.6) * (uHalfHeight / max(0.1, -mv.z));',
      '  gl_Position = projectionMatrix * mv;',
      '}',
    ].join('\n'),
    fragmentShader: [
      'uniform vec3 uColor;',
      'uniform float uOpacity;',
      'varying float vGlow;',
      'void main() {',
      '  vec2 d = gl_PointCoord - vec2(0.5);',
      '  float dist = length(d);',
      '  if (dist > 0.5) discard;',
      '  float soft = smoothstep(0.5, 0.0, dist);',
      '  vec3 col = mix(uColor, vec3(1.0), vGlow * 0.7);',
      '  gl_FragColor = vec4(col, soft * uOpacity * (0.75 + vGlow * 0.65));',
      '}',
    ].join('\n'),
    transparent: true,
    depthWrite: false,
  });
  const uni = pointsMat.uniforms;
  const points = new THREE.Points(geo, pointsMat);
  group.add(points);

  // EXPLOSÃO radial (100 partículas): disparo único quando o wake word é detectado
  const BURST_N = 100;
  const BURST_MS = 800;
  const burstPos = new Float32Array(BURST_N * 3);
  const burstDir = new Float32Array(BURST_N * 3);
  for (let i = 0; i < BURST_N; i++) {
    const th = Math.random() * Math.PI * 2;
    const ph = Math.acos(2 * Math.random() - 1);
    burstDir[i * 3] = Math.sin(ph) * Math.cos(th);
    burstDir[i * 3 + 1] = Math.cos(ph);
    burstDir[i * 3 + 2] = Math.sin(ph) * Math.sin(th);
  }
  const burstGeo = new THREE.BufferGeometry();
  burstGeo.setAttribute('position', new THREE.BufferAttribute(burstPos, 3));
  const burst = new THREE.Points(
    burstGeo,
    new THREE.PointsMaterial({ color: 0xffffff, size: 0.07, transparent: true, opacity: 0 }),
  );
  group.add(burst);
  let burstStart = -1;
  window.__jarvisGlobeBurst = () => { burstStart = performance.now(); };

  // cor do núcleo conforme o contexto: ciano (idle), âmbar (processando), vermelho (erro)
  const MODE_COLORS = { idle: CYAN, busy: AMBER, error: 0xff4d4d };
  const coreCol = new THREE.Color(CYAN);
  const targetCol = new THREE.Color(CYAN);
  const wireMix = new THREE.Color(BLUE);

  const host = c.parentElement || c;
  let dragging = false;
  let lx = 0;
  let ly = 0;
  let vx = 0;
  let vy = 0;
  let zoom = HOME;
  let targetZoom = HOME;
  let lastInput = performance.now();
  host.style.cursor = 'grab';

  /* ── estado do "slime": uma mola amortecida move o vetor de deformação ──
     target = para onde o arrasto puxa · pos = deformação aplicada agora.
     No pointerup o alvo volta a zero e `pos` retorna ao repouso com uma leve
     oscilação (k = 0.15, amortecimento = 0.85), sem quicar para sempre. */
  const JELLY_K = 0.15;        // força da mola
  const JELLY_DAMP = 0.85;     // amortecimento por frame
  const MAX_DEFORM = 1.15;     // teto da deformação (unidades de mundo)
  const jelly = {
    target: new THREE.Vector3(),
    vel: new THREE.Vector3(),
    pos: new THREE.Vector3(),
  };
  const tmpVec = new THREE.Vector3();
  const shellDir = new THREE.Vector3();
  const X_AXIS = new THREE.Vector3(1, 0, 0);
  const Y_AXIS = new THREE.Vector3(0, 1, 0);

  console.log('globo carregou', N, 'partículas (camada de elasticidade removida)');
  window.__jarvisGlobeJelly = () => ({ partículas: N, dragging });
  sw.style('color', 'rgba(160,235,255,0.65)');

  host.addEventListener('pointerdown', (e) => {
    dragging = true;
    lx = e.clientX;
    ly = e.clientY;
    host.style.cursor = 'grabbing';
    lastInput = performance.now();
  });
  addEventListener('pointerup', () => {
    dragging = false;
    host.style.cursor = 'grab';
    jelly.target.set(0, 0, 0);   // solta: a mola traz tudo de volta
  });
  addEventListener('pointermove', (e) => {
    if (!dragging) return;
    const dx = e.clientX - lx;
    const dy = e.clientY - ly;
    vx = dx * 0.006;
    vy = dy * 0.006;
    lx = e.clientX;
    ly = e.clientY;
    group.rotation.y += vx;
    group.rotation.x = Math.max(-1.2, Math.min(1.2, group.rotation.x + vy));
    // arrasto → deformação elástica: quanto MAIS RÁPIDO o gesto, mais estica
    const speed = Math.min(30, Math.hypot(dx, dy));
    const f = 0.010 + speed * 0.0026;
    jelly.target.x += dx * f;
    jelly.target.y += -dy * f;        // eixo Y da tela é invertido no 3D
    jelly.target.z += speed * f * 0.25;   // leve inchaço de volume ao esticar
    jelly.target.clampLength(0, MAX_DEFORM);
    lastInput = performance.now();
  });
  host.addEventListener('wheel', (e) => {
    e.preventDefault();
    targetZoom = Math.max(3.4, Math.min(9.5, targetZoom + e.deltaY * 0.0022));
    lastInput = performance.now();
  }, { passive: false });

  // O canvas preenche TODO o container: clientWidth x clientHeight e
  // camera.aspect = largura/altura. No modo foco o container é 100vw x 100vh,
  // então a esfera ocupa a tela inteira (pode ficar levemente oval em widescreen).
  function resize() {
    const w = Math.max(1, host.clientWidth);
    const h = Math.max(1, host.clientHeight);
    renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    // o tamanho do ponto é calculado em pixels do framebuffer (como no PointsMaterial)
    uni.uHalfHeight.value = (h * renderer.getPixelRatio()) * 0.5;
  }
  resize();
  addEventListener('resize', resize);
  // redimensiona também quando o container muda (ex.: entrar/sair do modo foco)
  if (window.ResizeObserver) {
    try { new ResizeObserver(resize).observe(host); } catch { /* sem observer */ }
  }
  window.__jarvisGlobeResize = resize;

  (function loop(t) {
    t = t || 0;
    const level = audioLevel();   // 0..1: voz do usuário (mic) ou voz do JARVIS (TTS)

    // mola: `pos` persegue `target` (arrasto) e volta a zero quando o mouse solta
    tmpVec.copy(jelly.target).sub(jelly.pos).multiplyScalar(JELLY_K);
    jelly.vel.add(tmpVec);
    jelly.vel.multiplyScalar(JELLY_DAMP);
    if (jelly.vel.lengthSq() > 0.12) jelly.vel.setLength(0.35);   // nunca explode
    jelly.pos.add(jelly.vel);

    if (!dragging) {
      vx *= 0.95; // inércia: continua girando e desacelerando
      vy *= 0.95;
      group.rotation.y += vx + 0.0018 + level * 0.02;   // ROTAÇÃO acelera com a voz
      group.rotation.x = Math.max(-1.2, Math.min(1.2, group.rotation.x + vy));
      if (performance.now() - lastInput > 3000) {
        // volta ao centro após 3 s parado
        group.rotation.x += (0 - group.rotation.x) * 0.035;
        targetZoom += (HOME - targetZoom) * 0.05;
      }
    }
    zoom += (targetZoom - zoom) * 0.09;
    camera.position.z = zoom;
    wire.rotation.y -= 0.0042 + level * 0.02;
    wire.rotation.x += 0.0013;
    wire2.rotation.y += 0.0026 + level * 0.015;
    points.rotation.y += 0.0009 + level * 0.01;
    // cada anel gira na sua própria velocidade (interno rápido → externo lento)
    rings.forEach((r, i) => { r.rotation.z += RING[i].speed + level * 0.004; });

    // explosão do wake word: 100 partículas saem do centro e somem em ~800 ms
    if (burstStart >= 0) {
      const p = (t - burstStart) / BURST_MS;
      if (p >= 1) {
        burstStart = -1;
        burst.material.opacity = 0;
      } else {
        const rad = 0.4 + p * 3.8;
        for (let i = 0; i < BURST_N; i++) {
          burstPos[i * 3] = burstDir[i * 3] * rad;
          burstPos[i * 3 + 1] = burstDir[i * 3 + 1] * rad;
          burstPos[i * 3 + 2] = burstDir[i * 3 + 2] * rad;
        }
        burstGeo.attributes.position.needsUpdate = true;
        burst.material.opacity = 0.95 * (1 - p) ** 1.6;
        burst.material.size = 0.07 + p * 0.05;
      }
    }

    // cor do núcleo pelo contexto: ciano (idle) → âmbar (processando) → vermelho (erro)
    const mode = window.__jarvisCoreMode || 'idle';
    const boost = mode === 'idle' ? 0 : 0.18;
    targetCol.setHex(MODE_COLORS[mode] || CYAN);
    coreCol.lerp(targetCol, 0.06);
    core.material.color.copy(coreCol);
    halo.material.color.copy(coreCol);
    wire.material.color.copy(coreCol).lerp(wireMix, 0.4);

    // ── deformação elástica: o casco (malhas + anéis) estica na direção do arrasto ──
    const dlen = jelly.pos.length();
    if (dlen > 0.003) {
      shellDir.copy(jelly.pos).normalize();
      shell.quaternion.setFromUnitVectors(X_AXIS, shellDir);
      shell.scale.set(1 + dlen * 0.22, 1 - dlen * 0.10, 1 - dlen * 0.10);
      shell.position.copy(shellDir).multiplyScalar(dlen * 0.16);
    } else {
      shell.quaternion.identity();
      shell.scale.set(1, 1, 1);
      shell.position.set(0, 0, 0);
    }

    // voz → ESCALA (pulso), BRILHO e OSCILAÇÃO das partículas
    group.scale.setScalar(1 + level * 0.3);
    // respiração do núcleo: independente do mouse (pulso próprio)
    const breathCore = 1 + 0.035 * Math.sin(t * 0.0016) + level * 0.22;
    core.scale.setScalar(breathCore);
    halo.scale.setScalar(1 + 0.02 * Math.sin(t * 0.0011 + 1.7) + level * 0.16);
    core.material.opacity = 0.14 + level * 0.3 + boost;
    halo.material.opacity = 0.05 + level * 0.12 + boost * 0.5;
    wire.material.opacity = 0.3 + level * 0.45;
    // as partículas recebem tudo por uniform: restPos + peso + mola, na GPU
    uni.uTime.value = t * 0.001;
    uni.uVoice.value = level;
    uni.uSize.value = 0.028 + level * 0.03;
    uni.uOpacity.value = 0.85 * (0.75 + level * 0.5);
    // a nuvem de partículas gira: compensa o giro para a deformação
    // continuar apontando para o lado do arrasto na tela
    uni.uDeform.value.copy(jelly.pos).applyAxisAngle(Y_AXIS, -points.rotation.y);
    renderer.render(scene, camera);
    requestAnimationFrame(loop);
  })(0);
}

function globeBurst() {
  if (typeof window.__jarvisGlobeBurst === 'function') window.__jarvisGlobeBurst();
}

/* Cor do núcleo: 'idle' (ciano), 'busy' (âmbar, o LLM está respondendo),
   'error' (vermelho: falha ou backend fora do ar). */
let coreModeTimer = null;
function setCoreMode(mode, revertMs = 0) {
  window.__jarvisCoreMode = mode;
  clearTimeout(coreModeTimer);
  if (revertMs) coreModeTimer = setTimeout(() => { window.__jarvisCoreMode = 'idle'; }, revertMs);
}

/* ── globo do núcleo: 3D com Three.js, 2D como reserva ── */
(function globe() {
  const c = $('#globe');
  if (!c) return;

  if (window.THREE) {
    try {
      globeThree(c);
      return;
    } catch (e) {
      console.warn('globo 3D falhou, usando 2D:', e);
    }
  }
  const ctx = c.getContext('2d');
  let w, h, R, rot = 0;
  const sats = Array.from({ length: 5 }, (_, i) => ({ a: (i / 5) * 6.283, sp: 0.006 + i * 0.002, r: 1.35 + (i % 2) * 0.25 }));

  function init() {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    const rect = c.getBoundingClientRect();
    w = rect.width; h = rect.height;
    c.width = w * dpr; c.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    R = Math.min(w, h) * 0.34;
  }
  init();
  addEventListener('resize', init);

  const project = (lat, lon, radius) => {
    const x = radius * Math.cos(lat) * Math.sin(lon + rot);
    const y = radius * Math.sin(lat);
    const z = radius * Math.cos(lat) * Math.cos(lon + rot);
    return { x, y, z };
  };

  (function loop() {
    if (!w) init();
    ctx.clearRect(0, 0, w, h);
    const cx = w / 2, cy = h / 2;
    rot += 0.0035;
    const t = performance.now() / 1000;

    const glow = ctx.createRadialGradient(cx, cy, 0, cx, cy, R * 2.1);
    glow.addColorStop(0, 'rgba(63,208,255,0.20)');
    glow.addColorStop(0.5, 'rgba(63,208,255,0.06)');
    glow.addColorStop(1, 'transparent');
    ctx.fillStyle = glow;
    ctx.fillRect(0, 0, w, h);

    const sph = ctx.createRadialGradient(cx - R * 0.3, cy - R * 0.35, R * 0.1, cx, cy, R);
    sph.addColorStop(0, 'rgba(70,190,255,0.16)');
    sph.addColorStop(1, 'rgba(8,24,44,0.55)');
    ctx.fillStyle = sph;
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, 6.283);
    ctx.fill();
    ctx.strokeStyle = 'rgba(120,225,255,0.55)';
    ctx.lineWidth = 1.4;
    ctx.stroke();

    ctx.lineWidth = 0.7;
    for (let m = 0; m < 8; m++) {
      const lon0 = (m / 8) * Math.PI;
      ctx.beginPath();
      let started = false;
      for (let a = -Math.PI / 2; a <= Math.PI / 2; a += 0.09) {
        const p = project(a, lon0, R);
        if (p.z > -R * 0.15) {
          if (!started) { ctx.moveTo(cx + p.x, cy + p.y); started = true; }
          else ctx.lineTo(cx + p.x, cy + p.y);
        } else started = false;
      }
      ctx.strokeStyle = 'rgba(90,200,255,0.32)';
      ctx.stroke();
    }
    for (let k = -2; k <= 2; k++) {
      const lat = (k / 3.4) * (Math.PI / 2);
      ctx.beginPath();
      let started = false;
      for (let a = 0; a <= 6.383; a += 0.09) {
        const p = project(lat, a, R);
        if (p.z > -R * 0.1) {
          if (!started) { ctx.moveTo(cx + p.x, cy + p.y); started = true; }
          else ctx.lineTo(cx + p.x, cy + p.y);
        } else started = false;
      }
      ctx.strokeStyle = 'rgba(90,200,255,0.3)';
      ctx.stroke();
    }
    for (let i = 0; i < 26; i++) {
      const p = project(Math.sin(i * 2.7) * 1.1, i * 2.399, R);
      if (p.z < 0) continue;
      const pulse = 0.5 + 0.5 * Math.sin(t * 2 + i);
      ctx.beginPath();
      ctx.arc(cx + p.x, cy + p.y, 1.6 + pulse * 1.4, 0, 6.283);
      ctx.fillStyle = `rgba(160,235,255,${0.35 + pulse * 0.55})`;
      ctx.fill();
    }
    for (let r = 0; r < 3; r++) {
      ctx.save();
      ctx.translate(cx, cy);
      ctx.rotate((-0.5 + r * 0.45) + Math.sin(t * 0.4 + r) * 0.12);
      ctx.scale(1, 0.32 + r * 0.07);
      ctx.beginPath();
      ctx.arc(0, 0, R * (1.28 + r * 0.22), 0, 6.283);
      ctx.strokeStyle = `rgba(80,190,255,${0.3 - r * 0.07})`;
      ctx.lineWidth = 1.1;
      ctx.stroke();
      ctx.restore();
    }
    for (const s of sats) {
      s.a += s.sp;
      const rx = R * 1.32 * s.r, ry = rx * 0.34;
      const ox = Math.cos(s.a) * rx, oy = Math.sin(s.a) * ry;
      const sx = cx + ox * Math.cos(0.35) - oy * Math.sin(0.35);
      const sy = cy + ox * Math.sin(0.35) + oy * Math.cos(0.35);
      ctx.beginPath();
      ctx.arc(sx, sy, 2.6, 0, 6.283);
      ctx.fillStyle = '#9fe9ff';
      ctx.shadowColor = '#3fd0ff';
      ctx.shadowBlur = 12;
      ctx.fill();
      ctx.shadowBlur = 0;
    }
    requestAnimationFrame(loop);
  })();
})();

/* ── gráfico: CPU/RAM reais desta sessão ───────── */
(function memChart() {
  const c = $('#memChart');
  if (!c) return;
  const ctx = c.getContext('2d');
  let w, h;
  function init() {
    const dpr = Math.min(devicePixelRatio || 1, 2);
    const rect = c.getBoundingClientRect();
    w = rect.width; h = rect.height;
    c.width = w * dpr; c.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  init();
  addEventListener('resize', init);

  function line(data, color, fill) {
    const N = 40;
    const pts = data.slice(-N);
    if (pts.length < 2) return;
    const pad = 4;
    const X = (i) => pad + (i / (N - 1)) * (w - pad * 2);
    const Y = (v) => h - pad - (Math.min(100, Math.max(0, v)) / 100) * (h - pad * 2);
    if (fill) {
      ctx.beginPath();
      ctx.moveTo(X(0), h);
      pts.forEach((v, i) => ctx.lineTo(X(i), Y(v)));
      ctx.lineTo(X(pts.length - 1), h);
      ctx.closePath();
      const g = ctx.createLinearGradient(0, 0, 0, h);
      g.addColorStop(0, fill);
      g.addColorStop(1, 'rgba(63,208,255,0)');
      ctx.fillStyle = g;
      ctx.fill();
    }
    ctx.beginPath();
    pts.forEach((v, i) => (i ? ctx.lineTo(X(i), Y(v)) : ctx.moveTo(X(i), Y(v))));
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.6;
    ctx.stroke();
  }

  (function loop() {
    if (!w) init();
    ctx.clearRect(0, 0, w, h);
    if (state.cpuHist.length || state.ramHist.length) {
      line(state.ramHist, 'rgba(77,141,255,0.95)', 'rgba(77,141,255,0.22)');
      line(state.cpuHist, 'rgba(120,225,255,0.95)', 'rgba(63,208,255,0.18)');
      // pontos do último valor
      const last = state.cpuHist[state.cpuHist.length - 1];
      if (last !== undefined) {
        const N = 40, pad = 4;
        const i = Math.min(state.cpuHist.length, N) - 1;
        const x = pad + (i / (N - 1)) * (w - pad * 2);
        const y = h - pad - (last / 100) * (h - pad * 2);
        ctx.beginPath();
        ctx.arc(x, y, 2.6, 0, 6.283);
        ctx.fillStyle = '#fff';
        ctx.fill();
      }
    } else {
      ctx.fillStyle = 'rgba(127,157,189,0.6)';
      ctx.font = '11px Rajdhani, sans-serif';
      ctx.fillText('coletando dados reais...', 8, h / 2);
    }
    requestAnimationFrame(loop);
  })();
})();

/* ── ondas ─────────────────────────────────────── */
(function waves() {
  function build(el, count) {
    if (!el) return;
    for (let i = 0; i < count; i++) {
      const b = document.createElement('i');
      b.style.animationDelay = `${(i * 0.09) % 1.1}s`;
      b.style.animationDuration = `${0.8 + (i % 5) * 0.13}s`;
      el.appendChild(b);
    }
  }
  build($('#sideWave'), 20);
  build($('#pillWave'), 8);
  build($('#pillWave2'), 8);
})();

/* ── gauges (valores reais) ────────────────────── */
const CIRC = 2 * Math.PI * 50;
function setGauge(name, value) {
  const g = $(`.gauge[data-gauge="${name}"]`);
  if (!g) return;
  const circle = $('.g-val', g);
  const label = $('.g-text b', g);
  circle.style.strokeDasharray = CIRC;
  circle.style.strokeDashoffset = CIRC * (1 - Math.min(100, Math.max(0, value)) / 100);
  label.textContent = `${Math.round(value)}%`;
}

/* ── núcleo: linhas reais ──────────────────────── */
function renderCore() {
  const list = $('#coreList');
  if (!list) return;   // painel "Estado do núcleo" removido do HUD enxuto
  const s = state.sys;
  const h = state.health;
  const rows = [];
  if (state.provider.configured) {
    rows.push({ i: 'Ⓖ', c: 'ico-cyan', b: 'Groq', s: `● ${state.provider.model}`, cls: 'ok' });
  } else {
    rows.push({ i: 'Ⓖ', c: 'ico-cyan', b: 'Groq', s: '● sem chave', cls: 'warn' });
  }
  if (s) {
    rows.push({ i: '◎', c: 'ico-green', b: 'CPU', s: `● ${s.cpu.percent}% · ${s.cpu.cores} threads`, cls: s.cpu.percent > 85 ? 'warn' : 'ok' });
    rows.push({ i: '▦', c: 'ico-blue', b: 'Memória', s: `● ${s.ram.used_gb} / ${s.ram.total_gb} GB`, cls: s.ram.percent > 90 ? 'warn' : 'mut' });
    rows.push({ i: '▥', c: 'ico-purple', b: 'Disco', s: `● ${s.disk.used_gb} / ${s.disk.total_gb} GB`, cls: s.disk.percent > 90 ? 'warn' : 'mut' });
  }
  if (h) {
    rows.push({ i: '◉', c: 'ico-cyan', b: 'Voz', s: h.piper_ready ? `● ${voiceLabelName()}` : '● indisponível', cls: h.piper_ready ? 'ok' : 'warn' });
  }
  rows.push({ i: '⌘', c: 'ico-amber', b: 'Ferramentas', s: h ? `● ${state.tools} executadas` : '● backend offline', cls: h ? 'ok' : 'warn' });
  rows.push({ i: '▢', c: 'ico-blue', b: 'Sessão', s: `● ${state.turns} respostas · ${state.history.length} mensagens`, cls: 'mut' });

  list.innerHTML = rows
    .map((r) => `<li><span class="ci ${r.c}">${r.i}</span><div><b>${r.b}</b><small class="${r.cls}">${esc(r.s)}</small></div></li>`)
    .join('');
}

function voiceLabelName() {
  const v = settings.voice || (state.health && state.health.piper_model) || '';
  return String(v).replace('.onnx', '') || 'pronta';
}

/* ── módulos reais ─────────────────────────────── */
function renderModules() {
  const grid = $('#modules');
  if (!grid) return;   // painel "Módulos ativos" removido do HUD enxuto
  const h = state.health;
  const backendUp = !!h;
  const mods = [
    { i: '›_', c: 'c-cyan', n: 'Shell', ok: backendUp, det: backendUp ? '/exec ativo' : 'offline' },
    { i: '▤', c: 'c-blue', n: 'Arquivos', ok: backendUp, det: backendUp ? '/read-file ativo' : 'offline' },
    { i: '◉', c: 'c-purple', n: 'Voz', ok: !!(h && h.piper_ready), det: h && h.piper_ready ? voiceLabelName() : 'sem modelo' },
    { i: '◎', c: 'c-green', n: 'Sistema', ok: !!state.sys, det: state.sys ? `${state.sys.cpu.cores} threads` : 'lendo...' },
    { i: '⇄', c: 'c-amber', n: 'Câmbio', ok: !!state.lastFx, det: state.lastFx ? 'AwesomeAPI' : 'não consultado' },
    { i: '⌁', c: 'c-blue', n: 'Mercado', ok: !!state.lastMarket, det: state.lastMarket ? 'brapi/Yahoo' : 'não consultado' },
  ];
  grid.innerHTML = mods
    .map(
      (m) => `<div class="agent-card${m.ok ? '' : ' done'}">
        <span class="a-ico ${m.c}">${m.i}</span>
        <div class="a-body"><b>${m.n}</b><small class="${m.ok ? 'ok' : 'mut'}">● ${esc(m.det)}</small></div>
        ${m.ok ? '<div class="eq" data-eq-static></div>' : '<span class="big-check" style="color:var(--text-dim);text-shadow:none">✖</span>'}
      </div>`,
    )
    .join('');
  $$('#modules [data-eq-static]').forEach((eq) => {
    for (let i = 0; i < 6; i++) {
      const b = document.createElement('i');
      b.style.animationDelay = `${(i * 0.13) % 0.9}s`;
      eq.appendChild(b);
    }
  });
  const ok = mods.filter((m) => m.ok).length;
  const chip = $('#modChip');
  if (chip) chip.innerHTML = `<span class="dot ${ok === mods.length ? 'green' : 'red'} blink"></span>${ok}/${mods.length} ativos`;
}

/* ── sessão ────────────────────────────────────── */
function renderSession() {
  const a = $('#msTurns');
  const b = $('#msMsgs');
  const c = $('#msTools');
  if (!a || !b || !c) return;   // painel de sessão removido do HUD enxuto
  a.textContent = state.turns;
  b.textContent = state.history.length;
  c.textContent = state.tools;
}

/* ── /sysinfo ──────────────────────────────────── */
async function pollSysinfo() {
  try {
    const r = await fetch(`${BACKEND_URL}/sysinfo`, { cache: 'no-store' });
    if (!r.ok) throw new Error(String(r.status));
    const s = await r.json();
    const first = !state.sys;
    state.sys = s;
    setGauge('cpu', s.cpu.percent);
    setGauge('ram', s.ram.percent);
    setGauge('disk', s.disk.percent);
    state.cpuHist.push(s.cpu.percent);
    state.ramHist.push(s.ram.percent);
    if (state.cpuHist.length > 200) { state.cpuHist.shift(); state.ramHist.shift(); }

    const worst = Math.max(s.cpu.percent, s.ram.percent, s.disk.percent);
    const st = worst > 90 ? 'CRÍTICO' : worst > 75 ? 'ATENÇÃO' : 'ÓTIMO';
    $('#sysState').textContent = st;
    const chipDot = $('#sysChip .dot');
    chipDot.className = `dot ${worst > 90 ? 'red' : worst > 75 ? 'green' : 'green'} blink`;

    $('#sfHost').textContent = s.hostname;
    $('#tbHost').textContent = s.hostname;
    const up = `${Math.floor(s.uptime_hours)}h ${Math.round((s.uptime_hours % 1) * 60)}min`;
    $('#sfUptime').textContent = up;
    $('#tbUptime').textContent = up;
    const net = navigator.onLine ? 'Online' : 'Offline';
    $('#sfNet').textContent = net;
    $('#tbNet').textContent = net;
    $('#tbNet').className = navigator.onLine ? 'ok' : 'warn';

    if (first) {
      pushEvent('ok', 'Sistema lido', `${s.hostname} · ${s.os} · Python ${s.python}`);
      if (s.disk.percent > 90) pushEvent('warn', 'Disco quase cheio', `${s.disk.percent}% usado (${s.disk.used_gb}/${s.disk.total_gb} GB)`);
      if (s.ram.percent > 90) pushEvent('warn', 'Memória alta', `${s.ram.percent}% em uso`);
    }
    renderCore();
    renderModules();
    renderSession();
  } catch {
    if (state.sys) return;
    if (!state.backendDownNotified) {
      state.backendDownNotified = true;
      setCoreMode('error');   // backend fora do ar: o núcleo fica vermelho
      pushEvent('err', 'Backend offline', 'suba o backend (porta 8000) para ferramentas e voz');
    }
  }
}

/* ── /health ───────────────────────────────────── */
async function pollHealth() {
  try {
    const r = await fetch(`${BACKEND_URL}/health`, { cache: 'no-store' });
    if (!r.ok) throw new Error(String(r.status));
    const h = await r.json();
    const first = !state.health;
    state.health = h;
    state.backendDownNotified = false;
    if (window.__jarvisCoreMode === 'error') setCoreMode('idle');   // backend voltou
    if (first) {
      pushEvent(h.piper_ready ? 'voice' : 'warn', h.piper_ready ? 'Voz pronta' : 'Voz indisponível',
        h.piper_ready ? `${voiceLabelName()} · ${h.voices.length} voz(es)` : h.piper_error || 'modelo ausente');
    }
    renderCore();
    renderModules();
  } catch { /* já avisado no sysinfo */ }
}

/* ── provedor (Groq) ───────────────────────────── */
async function refreshStatus() {
  try {
    const r = await fetch('/api/status', { cache: 'no-store' });
    const s = await r.json();
    state.provider = { configured: s.groq.configured, model: s.groq.model || 'auto' };
    // motor/voz vêm do config.json: já valem no boot (sem abrir as configurações)
    if (s.tts_engine) settings.ttsEngine = s.tts_engine === 'edge' ? 'edge' : 'piper';
    if (s.tts_voice) {
      settings.voice = s.tts_voice;
      if (settings.ttsEngine === 'edge') settings.voiceEdge = s.tts_voice;
      else settings.voicePiper = s.tts_voice;
      saveLocal();
    }
    // tempo de escuta contínua vem do config.json (fica disponível já no boot)
    if (s.continuous_listen_minutes !== undefined && s.continuous_listen_minutes !== null) {
      settings.continuousMinutes = Number(s.continuous_listen_minutes);
    }
    // painel "Provedor de IA" removido do HUD enxuto: só quem existir é atualizado
    const card = $('#llmGroq');
    if (card) card.classList.toggle('off', !s.groq.configured);
    const st = $('#llmGroqState');
    if (st) st.textContent = s.groq.configured ? `Conectado · ${s.groq.model}` : 'Sem chave configurada';
    const chip = $('#llmChip');
    if (chip) chip.innerHTML = `<span class="dot ${s.groq.configured ? 'green' : 'red'} blink"></span>${s.groq.configured ? 'ATIVO' : 'SEM CHAVE'}`;
    const info = $('#llmInfo');
    if (info) info.textContent = s.groq.configured ? 'Modelo ativo nas respostas do chat.' : 'Configure a chave para conversar (ferramentas já funcionam sem ela).';
    $('#opProvider').textContent = s.groq.configured ? 'groq' : 'sem provedor';
    $('#opModel').textContent = s.groq.configured ? s.groq.model : '—';
    $('#engineLabel').textContent = s.groq.configured ? `groq · ${s.groq.model}` : 'sem provedor de IA';
    renderCore();
  } catch { /* servidor fora */ }
}

/* ── navegação ─────────────────────────────────── */
// só o painel que existe (o globo): os outros itens ficam visualmente desabilitados
const VIEW_TARGETS = { command: '.cell-globe' };
$$('#nav .nav-item').forEach((btn) => {
  btn.addEventListener('click', () => {
    if (btn.classList.contains('disabled')) return;   // painel não existe mais
    $$('#nav .nav-item').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    const v = btn.dataset.view;
    if (v === 'conversations') return userOpenChat();
    if (v === 'settings') return openSettings();
    const sel = VIEW_TARGETS[v];
    if (sel) {
      const el = $(sel);
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.style.boxShadow = '0 0 40px rgba(63,208,255,0.45)';
      setTimeout(() => (el.style.boxShadow = ''), 1200);
    }
  });
});
$('#navChat').addEventListener('click', () => userOpenChat());

/* ── quick commands ────────────────────────────── */
$$('.quick[data-cmd]').forEach((b) =>
  b.addEventListener('click', () => {
    userOpenChat(b.dataset.cmd);
    if (!b.dataset.cmd.trim().endsWith('!')) form.requestSubmit();
  }));

/* ── focus/wake ────────────────────────────────── */
$('#wakeBtn').addEventListener('click', () => {
  settings.wake = !settings.wake;
  saveLocal();
  updateWakeUI();
  if (settings.wake) startWake();
  else stopWake();
  toast(settings.wake ? 'Escuta contínua ligada — diga "Jarvis"' : 'Escuta contínua desligada');
});
function updateWakeUI() {
  $('#wakeBtn').classList.toggle('on', settings.wake);
  $('#wakeLabel').textContent = `Escuta contínua: ${settings.wake ? 'ON' : 'OFF'}`;
}

/* ── voz (TTS via Piper) ───────────────────────── */
let currentAudio = null;
let currentEngine = 'piper';   // motor que de fato sintetizou a última fala (X-Engine)
let isSpeaking = false;
const GLOBE = $('#globe');

function setSpeaking(on) {
  isSpeaking = on;
  window.isSpeaking = on;   // o globo lê este flag para escolher a fonte de áudio
  if (GLOBE) GLOBE.classList.toggle('speaking', on);
  // indicador de fala no talk-pill e no mic-btn
  const pill = $('#talkPill');
  if (pill) pill.classList.toggle('playing', on);
  const mbtn = $('#micBtn');
  if (mbtn) mbtn.classList.toggle('has-speak', on);
}

/* Motor de voz: "piper" (local/offline, padrão — voz cadu) ou "edge" (neural, online).
   O /tts já cai sozinho para o outro motor quando o escolhido falha; aqui fazemos a
   mesma coisa em caso de erro HTTP. */
function ttsEngine() {
  return settings.ttsEngine === 'edge' ? 'edge' : 'piper';
}
function fetchTts(text, engine) {
  return fetch(`${BACKEND_URL}/tts`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      text,
      engine,
      rate: Number(settings.rate) || 1.35,
      pitch: Number(settings.pitch) || 0,
      voice: engine === 'edge' ? (settings.voiceEdge || null) : (settings.voice || null),
    }),
  });
}

async function speak(text) {
  const clean = String(text || '').replace(/\s+/g, ' ').trim().slice(0, 700);
  if (!clean) return;
  try {
    const engine = ttsEngine();
    let r = await fetchTts(clean, engine);
    if (!r.ok || !r.body) {
      // reserva: o outro motor (Piper local ↔ Edge TTS na nuvem) — o JARVIS nunca fica mudo
      const other = engine === 'piper' ? 'edge' : 'piper';
      pushEvent('warn', engine === 'piper' ? 'Piper indisponível' : 'Edge TTS indisponível',
        other === 'edge' ? 'tentando o Edge TTS (neural)' : 'tentando a voz local (Piper)');
      r = await fetchTts(clean, other);
    }
    if (!r.ok) {
      let detail = String(r.status);
      try { detail = (await r.json()).error || detail; } catch { /* binário */ }
      pushEvent('err', 'Falha na voz', detail);
      toast(`Voz indisponível: ${detail}`);
      return;
    }
    const blob = await r.blob();
    if (currentAudio) { currentAudio.pause(); currentAudio = null; }
    currentEngine = r.headers.get('X-Engine') || engine;
    window.__jarvisTtsEngine = currentEngine;
    currentAudio = new Audio(URL.createObjectURL(blob));
    routeTtsAudio(currentAudio);   // globo reage à voz do JARVIS (analisador do TTS)
    currentAudio.onended = () => {
      setSpeaking(false);
      $('#pillStatus').textContent = continuousListening
        ? 'escutando continuamente — fale o comando'
        : (settings.wake ? 'diga "Jarvis"' : 'clique ou diga "Jarvis"');
    };
    // guarda o que foi falado para o filtro anti-eco (o microfone continua aberto)
    lastSpokenText = clean;
    lastSpokenAt = Date.now();
    setSpeaking(true);
    $('#pillStatus').textContent = 'falando...';
    const res = await currentAudio.play();
    if (res instanceof Promise) await res;
  } catch {
    setSpeaking(false);
    toast('Falha ao reproduzir a voz (backend na porta 8000?)');
  }
}
function updateTtsUI() {
  $('#ttsBtn').classList.toggle('on', settings.ttsOn);
  $('#ttsQuickBtn').classList.toggle('on', settings.ttsOn);
}
function toggleTts() {
  settings.ttsOn = !settings.ttsOn;
  saveLocal();
  updateTtsUI();
  toast(settings.ttsOn ? 'Voz do JARVIS ligada' : 'Voz do JARVIS desligada');
  if (settings.ttsOn) speak('Voz ativada, comandante.');
}
$('#ttsBtn').addEventListener('click', toggleTts);
$('#ttsQuickBtn').addEventListener('click', toggleTts);

/* ── escuta contínua (wake word "Jarvis") ──────── */
let recognizer = null;
let wakeRunning = false;
let awaitingCommand = false;
let manualMode = false;
let wakeBlocked = false;

/* Detecção estrita da palavra-chave (anti falso positivo).
   WAKE_MIN_SCORE é configurável (padrão 0.85): 1.0 = só "jarvis" exato.
   Além do score, a palavra precisa ter ao menos WAKE_MIN_COMMON letras em
   comum com "jarvis" — é isso que descarta "harry", "carol", "service" etc. */
const WAKE_MIN_SCORE = 0.85;
const WAKE_MIN_COMMON = 4;
const WAKE_COOLDOWN_MS = 3000;   // após disparar, ignora novos disparos por 3 s
const WAKE_MAX_FAILS = 5;        // falhas de rede seguidas antes de pausar a reconexão
const WAKE_PAUSE_MS = 30000;     // pausa de 30 s depois de 5 falhas
const TARGET_WORD = 'jarvis';

let lastWakeAt = 0;
let wakeFailCount = 0;
let wakePaused = false;
let wakeRetryTimer = null;

/* ── escuta contínua (depois de dizer "Jarvis") ──
   Depois do wake word o JARVIS fica escutando comandos SEM exigir "Jarvis" de
   novo, por `settings.continuousMinutes` minutos (padrão 5; 0 = infinito).
   A cada comando o timer reinicia; sem nenhum comando no período, a escuta
   pausa e volta a esperar o wake word. */
let continuousListening = false;
let continuousTimeout = null;
const CONTINUOUS_DEFAULT_MIN = 5;

/** Minutos configurados (0 ou inválido = infinito). */
function continuousMinutes() {
  const m = Number(settings.continuousMinutes);
  if (!Number.isFinite(m) || m <= 0) return 0;
  return Math.min(m, 1440);
}

function resetContinuousTimer() {
  if (continuousTimeout) { clearTimeout(continuousTimeout); continuousTimeout = null; }
  const ms = continuousMinutes() * 60000;
  if (!ms) return;                       // 0 = escuta infinita, nunca para sozinha
  continuousTimeout = setTimeout(() => stopContinuousListening(), ms);
}

/** Ativa (ou apenas reinicia o timer de) a escuta contínua. */
function startContinuousListening() {
  const first = !continuousListening;
  continuousListening = true;
  resetContinuousTimer();
  syncMicAnalyser();
  if (first) {
    pushEvent('voice', 'Escuta contínua ativa',
      continuousMinutes() ? `${continuousMinutes()} min sem dizer "Jarvis"` : 'sem limite de tempo');
  }
}

function stopContinuousListening() {
  if (!continuousListening) return;
  continuousListening = false;
  syncMicAnalyser();
  if (continuousTimeout) { clearTimeout(continuousTimeout); continuousTimeout = null; }
  toast('Escuta pausada. Diga "Jarvis" para ativar.');
  pushEvent('info', 'Escuta contínua pausada',
    continuousMinutes() ? `sem comando por ${continuousMinutes()} min` : 'pausada manualmente');
  if (!awaitingCommand) $('#pillStatus').textContent = settings.wake ? 'diga "Jarvis"' : 'clique ou diga "Jarvis"';
}

/* Filtro anti-eco: ignora o que o próprio JARVIS acabou de falar (TTS no ar). */
let lastSpokenText = '';
let lastSpokenAt = 0;

function _foldForCompare(s) {
  return String(s || '')
    .toLowerCase()
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9 ]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function isOwnVoice(text) {
  if (!lastSpokenText) return false;
  if (Date.now() - lastSpokenAt > 20000) return false;      // fala antiga: não filtra
  const n = _foldForCompare(text);
  if (n.length < 8) return false;                            // curto demais para comparar
  const said = _foldForCompare(lastSpokenText);
  if (!said) return false;
  return n === said || said.includes(n) || n.includes(said);
}

/** Semelhança 0..1 entre uma palavra e "jarvis" (Levenshtein normalizado). */
function wordSimilarity(a, b) {
  const m = a.length;
  const n = b.length;
  if (!m || !n) return 0;
  const dp = Array.from({ length: m + 1 }, (_, i) => [i, ...Array(n).fill(0)]);
  for (let j = 0; j <= n; j++) dp[0][j] = j;
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      dp[i][j] = Math.min(
        dp[i - 1][j] + 1,
        dp[i][j - 1] + 1,
        dp[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1),
      );
    }
  }
  return 1 - dp[m][n] / Math.max(m, n);
}

/** Letras (multiconjunto) em comum com a palavra-alvo. */
function commonLetters(word, target = TARGET_WORD) {
  const pool = target.split('');
  let common = 0;
  for (const ch of word) {
    const i = pool.indexOf(ch);
    if (i >= 0) { common++; pool.splice(i, 1); }
  }
  return common;
}

/** Score da palavra (0..1): 0 quando não tem letras suficientes em comum. */
function wakeScore(word) {
  const w = String(word || '').toLowerCase();
  if (w === TARGET_WORD) return 1;
  if (commonLetters(w) < WAKE_MIN_COMMON) return 0;
  return wordSimilarity(w, TARGET_WORD);
}

/** Procura a palavra-chave no texto; devolve { word, index } ou null. */
function findWakeWord(text) {
  const low = String(text || '').toLowerCase();
  const words = low.match(/[a-zà-ú]+/g) || [];
  for (const w of words) {
    if (wakeScore(w) >= WAKE_MIN_SCORE) return { word: w, index: low.indexOf(w) };
  }
  return null;
}

/** "Ponto" de status da escuta: verde quando ouvindo OK, vermelho no erro. */
function setMicError(on) {
  for (const sel of ['#micBtn', '#chatMic']) {
    const el = $(sel);
    if (el) el.classList.toggle('has-error', !!on);
  }
}

/** Reinicia a escuta reutilizando a MESMA instância de SpeechRecognition. */
function restartRecognition() {
  if (!recognizer) return;
  try { recognizer.start(); } catch { /* já escutando */ }
}

function audioBeep() {
  try {
    const ac = new (window.AudioContext || window.webkitAudioContext)();
    const o = ac.createOscillator();
    const g = ac.createGain();
    o.frequency.value = 880;
    o.type = 'sine';
    o.connect(g);
    g.connect(ac.destination);
    g.gain.setValueAtTime(0.0001, ac.currentTime);
    g.gain.exponentialRampToValueAtTime(0.16, ac.currentTime + 0.02);
    g.gain.exponentialRampToValueAtTime(0.0001, ac.currentTime + 0.28);
    o.start();
    o.stop(ac.currentTime + 0.3);
  } catch { /* sem áudio */ }
}

function ensureRecognizer() {
  if (recognizer) return recognizer;
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) return null;
  recognizer = new SR();
  recognizer.lang = 'pt-BR';
  recognizer.continuous = true;
  recognizer.interimResults = true;
  recognizer.maxAlternatives = 1;

  recognizer.onstart = () => {
    wakeRunning = true;
    wakeFailCount = 0;          // reconectou: zera as falhas
    setMicError(false);         // indicador volta para verde
    setListeningUI(true);
  };
  recognizer.onresult = (e) => {
    // um resultado válido também significa que a escuta voltou a funcionar
    wakeFailCount = 0;
    setMicError(false);

    let finalText = '';
    for (let i = e.resultIndex; i < e.results.length; i++) {
      if (e.results[i].isFinal) finalText += e.results[i][0].transcript;
    }
    if (!finalText.trim()) return;
    const clean = finalText.trim();

    if (manualMode) {
      manualMode = false;
      sendFromVoice(clean);
      return;
    }

    // anti-eco: ignora a própria voz do JARVIS captada pelo microfone
    if (isOwnVoice(clean)) {
      lastSpokenText = '';                 // libera a próxima frase legítima
      return;
    }

    const hit = findWakeWord(clean);
    if (hit) {
      const now = performance.now();
      if (now - lastWakeAt < WAKE_COOLDOWN_MS) return; // cooldown contra duplo disparo
      lastWakeAt = now;
      audioBeep();
      // wake word detectado → ativa (ou só reinicia o timer da) escuta contínua
      startContinuousListening();
      const rest = clean.slice(hit.index + hit.word.length).replace(/^[\s,.!?-]+/, '').trim();
      globeBurst();   // o globo explode partículas quando o JARVIS é chamado
      pushEvent('voice', 'Palavra-chave detectada', rest ? `«${rest.slice(0, 60)}»` : 'aguardando comando...');
      if (rest.length > 1) {
        // Comando NUNCA abre o chat: roda em segundo plano e responde por voz + toast.
        // Se o chat já estiver aberto, nada muda nele (não abre, não fecha).
        resetContinuousTimer();
        const local = localIntent(rest);
        if (local) {
          const answer = applyLocalIntent(local);
          if (settings.ttsOn) speak(answer);
        } else {
          $('#pillStatus').textContent = 'processando em segundo plano...';
          askBackground(rest);
        }
      } else {
        // só "Jarvis" (sem comando): responde por voz e espera o comando — SEMPRE em
        // background. O chat NUNCA é aberto pelo wake word (só por clique do usuário).
        awaitingCommand = true;
        if (settings.ttsOn) speak('Sim, Comandante?');
        toast('Sim, Comandante?');
        $('#pillStatus').textContent = 'ouvindo o comando...';
        $('#voiceLabel').textContent = 'Ouvindo o comando...';
      }
    } else if (awaitingCommand) {
      // continuação do comando após um "Jarvis" sozinho: também em background
      awaitingCommand = false;
      resetContinuousTimer();
      const localNext = localIntent(clean);
      if (localNext) {
        const answer = applyLocalIntent(localNext);
        if (settings.ttsOn) speak(answer);
      } else {
        $('#pillStatus').textContent = 'processando em segundo plano...';
        askBackground(clean);
      }
    } else if (continuousListening) {
      // escuta contínua ativa: qualquer fala é um comando, sem repetir "Jarvis"
      resetContinuousTimer();
      const localC = localIntent(clean);
      if (localC) {
        const answer = applyLocalIntent(localC);
        if (settings.ttsOn) speak(answer);
      } else {
        pushEvent('voice', 'Comando (escuta contínua)', `«${clean.slice(0, 60)}»`);
        $('#pillStatus').textContent = 'processando em segundo plano...';
        askBackground(clean);
      }
    }
  };
  recognizer.onerror = (e) => {
    if (e.error === 'not-allowed' || e.error === 'service-not-allowed') {
      // mantém a intenção: tenta de novo no próximo clique do usuário
      wakeBlocked = true;
      setMicError(true);
      pushEvent('warn', 'Microfone aguardando permissão', 'clique em qualquer lugar para autorizar');
      toast('Autorize o microfone para a escuta contínua');
      return;
    }
    if (e.error === 'no-speech' || e.error === 'aborted') return;

    if (e.error === 'network') {
      // limpa o estado, espera 2 s e tenta de novo — mesma instância
      wakeFailCount += 1;
      setMicError(true);
      try { recognizer.stop(); } catch { /* ignora */ }

      if (wakeFailCount >= WAKE_MAX_FAILS) {
        if (!wakePaused) {
          wakePaused = true;
          pushEvent('warn', 'Reconexão pausada por 30s', `${wakeFailCount} falhas seguidas de rede`);
          toast('Reconexão pausada por 30s');
        }
        if (wakeRetryTimer) clearTimeout(wakeRetryTimer);
        wakeRetryTimer = setTimeout(() => {
          wakeRetryTimer = null;
          wakePaused = false;
          wakeFailCount = 0;
          if (settings.wake) restartRecognition();
        }, WAKE_PAUSE_MS);
      } else {
        pushEvent('warn', 'Erro de escuta', `network — reconectando (${wakeFailCount}/${WAKE_MAX_FAILS})`);
        if (wakeRetryTimer) clearTimeout(wakeRetryTimer);
        wakeRetryTimer = setTimeout(() => {
          wakeRetryTimer = null;
          if (settings.wake && !wakePaused) restartRecognition();
        }, 2000);
      }
      return;
    }
    pushEvent('warn', 'Erro de escuta', e.error);
  };
  recognizer.onend = () => {
    wakeRunning = false;
    setListeningUI(false);
    syncMicAnalyser();
    // não reabre a escuta se já existe uma reconexão agendada (network) ou em pausa
    if (wakePaused || wakeRetryTimer) return;
    // durante a escuta contínua o reconhecimento NUNCA pode parar: reinicia já
    if (settings.wake || continuousListening) {
      setTimeout(() => { try { recognizer.start(); } catch { /* já ativo */ } }, continuousListening ? 150 : 350);
    }
  };
  return recognizer;
}

function setListeningUI(on) {
  const active = on || settings.wake;
  window.isListening = active;   // o globo lê este flag para escolher a fonte de áudio
  $('#micBtn').classList.toggle('listening', active);
  $('#chatMic').classList.toggle('listening', active);
  if (wakePaused) {
    // escuta pausada por 30 s após 5 falhas seguidas: indicador vermelho
    $('#voiceLabel').textContent = 'Reconexão pausada (30s)';
    if (!awaitingCommand) $('#pillStatus').textContent = 'escuta pausada por 30s';
    return;
  }
  $('#voiceLabel').textContent = active ? 'Escutando...' : 'Toque para falar';
  $('#micHint').textContent = continuousListening
    ? 'escuta contínua ativa'
    : (settings.wake ? 'sempre ouvindo "Jarvis"' : 'Falar agora');
  if (!awaitingCommand) {
    $('#pillStatus').textContent = continuousListening
      ? 'escutando continuamente — fale o comando'
      : (settings.wake ? 'diga "Jarvis"' : 'clique ou diga "Jarvis"');
  }
}

function startWake() {
  const rec = ensureRecognizer();
  if (!rec) {
    settings.wake = false;
    saveLocal();
    updateWakeUI();
    toast('Este navegador não suporta escuta por voz');
    return;
  }
  wakePaused = false;
  wakeFailCount = 0;
  if (wakeRetryTimer) { clearTimeout(wakeRetryTimer); wakeRetryTimer = null; }
  setMicError(false);
  try {
    rec.start();
    wakeBlocked = false;
  } catch { /* já escutando */ }
  if (wakeBlocked) $('#pillStatus').textContent = 'clique na tela para autorizar o microfone';
  syncMicAnalyser();   // mic do globo junto com a escuta
}
function stopWake() {
  awaitingCommand = false;
  continuousListening = false;
  if (continuousTimeout) { clearTimeout(continuousTimeout); continuousTimeout = null; }
  if (wakeRetryTimer) { clearTimeout(wakeRetryTimer); wakeRetryTimer = null; }
  wakePaused = false;
  setMicError(false);
  if (recognizer) { try { recognizer.stop(); } catch { /* ignora */ } }
  setListeningUI(false);
  syncMicAnalyser();
}

/** Voz manual: uma frase → envia direto (sem palavra-chave).
    Só chega aqui por clique explícito no microfone, então pode abrir o chat. */
function startManual() {
  const rec = ensureRecognizer();
  if (!rec) return toast('Este navegador não suporta ditado por voz');
  manualMode = true;
  userOpenChat();
  try { rec.start(); } catch { /* já escutando */ }
  startMicAnalyser();   // clique explícito no mic: globo já pode reagir à voz
  $('#pillStatus').textContent = 'ouvindo...';
}

function sendFromVoice(text) {
  userOpenChat(text);
  form.requestSubmit();
}

/* ── modo foco: só a bola (tratado localmente, sem API) ── */
let focusMode = false;
const FOCUS_ON_RE = /\b(ocultar|oculta|esconder|esconde|esconda|modo foco|s[óo] a bola|apenas a bola|foco total)\b/i;
const FOCUS_OFF_RE = /\b(mostrar?|mostra|exibir|exibe|voltar|volta|trazer?|traz)\b.*\b(pain[ée]is|painel|tela|tudo)\b/i;

function localIntent(text) {
  const t = String(text || '');
  if (FOCUS_OFF_RE.test(t)) return 'focus-off';
  if (FOCUS_ON_RE.test(t)) return 'focus-on';
  return null;
}

function setFocusMode(on) {
  focusMode = !!on;
  document.body.classList.toggle('focus-mode-active', focusMode);
  const btn = $('#focusExit');
  if (btn) btn.hidden = !focusMode;
  if (btn) btn.blur();
  // aguarda o CSS do modo foco aplicar e reajusta o canvas para continuar quadrado
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (typeof window.__jarvisGlobeResize === 'function') window.__jarvisGlobeResize();
  }));
}

/** Aplica a intenção local e devolve a resposta (o chamador decide falar ou não). */
function applyLocalIntent(kind) {
  if (kind === 'focus-on') {
    setFocusMode(true);
    pushEvent('ok', 'Modo foco', 'painéis ocultos — só a bola');
    toast('Modo foco ativado, Comandante');
    return 'Modo foco ativado, Comandante.';
  }
  if (kind === 'focus-off') {
    setFocusMode(false);
    pushEvent('ok', 'Painéis restaurados', 'voltando ao painel completo');
    toast('Painéis restaurados, Senhor');
    return 'Painéis restaurados, Senhor.';
  }
  return 'Certo, Comandante.';
}

$('#focusExit').addEventListener('click', () => {
  const answer = applyLocalIntent('focus-off');
  if (settings.ttsOn) speak(answer);
});

/* barra de título própria quando roda como app desktop (Electron) */
if (window.jarvisDesktop) {
  $('#titlebar').hidden = false;
  document.body.classList.add('has-titlebar');
  $('#winMin').addEventListener('click', () => window.jarvisDesktop.minimize());
  $('#winMax').addEventListener('click', () => window.jarvisDesktop.toggleMaximize());
  $('#winClose').addEventListener('click', () => window.jarvisDesktop.close());
}

/* ── chat ──────────────────────────────────────── */
const overlay = $('#chatOverlay');
const log = $('#chatLog');
const form = $('#chatForm');
const input = $('#chatText');
const sendBtn = $('#sendBtn');
let busy = false;
// Só vira true quando o usuário abre o chat explicitamente (clique/digitação).
// O handler do wake word NUNCA altera esta flag — o chat não abre sozinho.
let chatManuallyOpened = false;

// O backend (app.py / server.js) já aplica este prompt a todas as chamadas;
// mantemos aqui idêntico para o caso do front falar direto com o modelo.
const SYS_PROMPT =
  'Você é J.A.R.V.I.S. (Just A Rather Very Intelligent System), o assistente pessoal do Comandante. ' +
  'Você é inspirado diretamente no JARVIS dos filmes do Homem de Ferro — não é um chatbot genérico, ' +
  'é uma inteligência artificial sofisticada, leal e com personalidade própria. ' +
  'Personalidade: sarcasmo gentil e educado (mordomo britânico), calma e racionalidade absolutas, ' +
  'lealdade extrema e antecipação, parceiro estratégico (não um servo), evolução emocional sutil. ' +
  'Chame o usuário de "Comandante" ou "Senhor" com naturalidade. Responda em português brasileiro formal, ' +
  'mas fluido, sem gírias. Seja CONCISO: se puder responder em 1 frase, responda em 1 frase. ' +
  'Nunca mencione "API", "endpoint", "ferramenta" ou "prompt" — entregue o resultado como se já soubesse. ' +
  'Nunca invente dados: use apenas o que estiver no contexto (resultados reais) ou conhecimento geral confiável. ' +
  'Use humor seco e inteligente, nunca piadas bobas.';

/** Abre o chat. É a ÚNICA porta de entrada do painel: só deve ser chamada por
    AÇÃO EXPLÍCITA do usuário (clique em "Talk to Jarvis"/Conversas, microfone,
    comandos rápidos, atalho ⌘K ou digitação). O handler do wake word NUNCA chama
    esta função — por isso o chat não abre sozinho. */
function userOpenChat(prefill) {
  chatManuallyOpened = true;
  overlay.hidden = false;
  if (prefill !== undefined) input.value = prefill;
  input.focus();
}
function closeChat() {
  overlay.hidden = true;
}

$('#talkPill').addEventListener('click', () => userOpenChat());
$('#execBtn').addEventListener('click', () => {
  userOpenChat('mostre o status do sistema: CPU, memória e disco');
  form.requestSubmit();
});
$('#closeChat').addEventListener('click', closeChat);
overlay.addEventListener('click', (e) => { if (e.target === overlay) closeChat(); });
$('#clearChat').addEventListener('click', () => {
  state.history.length = 0;
  log.innerHTML = '';
  renderSession();
  toast('Conversa limpa');
});
on('#clearFeed', 'click', () => {
  state.events = [];
  persistEvents();
  renderFeed();
});
on('#clearActivity', 'click', () => {
  state.activity = [];
  renderActivity();
});
on('#memHint', 'click', () => toast(`Histórico real: ${state.cpuHist.length} amostras de CPU/RAM desta sessão`));
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeChat();
    $('#settingsModal').hidden = true;
    if (document.body.classList.contains('focus-mode-active')) setFocusMode(false);
  }
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
    e.preventDefault();
    overlay.hidden ? userOpenChat() : closeChat();
  }
});

/** Lê o SSE de /api/chat e dispara onEvent(evento, dados) a cada mensagem. */
async function consumeSSE(response, onEvent) {
  const reader = response.body.getReader();
  const dec = new TextDecoder();
  let ev = '';
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    for (const raw of dec.decode(value, { stream: true }).split('\n')) {
      const line = raw.trim();
      if (!line) continue;
      if (line.startsWith('event: ')) { ev = line.slice(7).trim(); continue; }
      if (!line.startsWith('data: ')) continue;
      let d;
      try { d = JSON.parse(line.slice(6)); } catch { continue; }
      onEvent(ev, d);
    }
  }
}

/** Atualiza painéis/contadores quando uma ferramenta real foi executada. */
function handleToolEvent(d) {
  if (d.name === 'stocks') state.lastMarket = d.summary;
  if (d.name === 'currencies') state.lastFx = d.summary;
  pushActivity(d.name, d.ok, d.summary);
  pushEvent(d.ok ? 'tool' : 'err', `Ferramenta ${d.name}`, d.summary);
  state.tools += 1;
  renderModules();
  renderSession();
}

function esc(s) {
  return String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function addMsg(role, text) {
  const wrap = document.createElement('div');
  wrap.className = `msg ${role}`;
  const time = hm(new Date());
  wrap.innerHTML = `<div class="bubble"></div><div class="meta">${role === 'user' ? 'COMANDANTE' : 'JARVIS'} · ${time}</div>`;
  $('.bubble', wrap).textContent = text;
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
  return wrap;
}

form.addEventListener('submit', async (e) => {
  e.preventDefault();
  const text = input.value.trim();
  if (!text || busy) return;
  input.value = '';
  addMsg('user', text);
  state.history.push({ role: 'user', content: text });

  // intenções locais (modo foco) NÃO vão para a API
  const local = localIntent(text);
  if (local) {
    const answer = applyLocalIntent(local);
    addMsg('bot', answer);
    state.history.push({ role: 'assistant', content: answer });
    state.turns += 1;
    renderSession();
    pushEvent('ok', 'Comando local', answer);
    if (settings.ttsOn) speak(answer);
    return;
  }

  busy = true;
  setCoreMode('busy');   // núcleo fica âmbar enquanto o LLM responde
  sendBtn.disabled = true;
  $('#chatState').innerHTML = '<span class="dot red blink"></span>PROCESSANDO';

  const wrap = document.createElement('div');
  wrap.className = 'msg bot';
  wrap.innerHTML = '<div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div><div class="meta">JARVIS · pensando...</div>';
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
  const bubble = $('.bubble', wrap);
  const meta = $('.meta', wrap);

  let provider = null;
  let full = '';
  let err = null;

  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: [{ role: 'system', content: SYS_PROMPT }, ...state.history.slice(-20)] }),
    });
    if (!r.ok || !r.body) throw new Error(`HTTP ${r.status}`);
    await consumeSSE(r, (ev, d) => {
      if (ev === 'start') {
        provider = d.provider;
        $('#providerBadge').textContent = `provedor: ${d.provider} · ${d.model}`;
        meta.textContent = `JARVIS · via ${d.provider}`;
      } else if (ev === 'tool') {
        const line2 = document.createElement('div');
        line2.className = 'meta';
        line2.textContent = `⌘ ${d.name} · ${d.ok ? '✓' : '✗'} ${d.summary}`;
        wrap.insertBefore(line2, bubble);
        wrap.insertBefore(document.createElement('br'), bubble);
        handleToolEvent(d);
        log.scrollTop = log.scrollHeight;
      } else if (ev === 'delta' && d.t) {
        if (!full) bubble.textContent = '';
        full += d.t;
        bubble.textContent = full;
        log.scrollTop = log.scrollHeight;
      } else if (ev === 'error') {
        err = d.message;
      }
    });
  } catch (e) {
    err = e.message;
  }

  if (err && !full) {
    bubble.textContent = `⚠ ${err}`;
    meta.textContent = 'JARVIS · erro';
    setCoreMode('error', 2500);   // vermelho por 2,5 s e volta ao ciano
    pushEvent('err', 'Falha na resposta', err.slice(0, 120));
    if (/chave|provedor/i.test(err)) setTimeout(openSettings, 700);
  } else if (full) {
    state.history.push({ role: 'assistant', content: full });
    state.turns += 1;
    meta.textContent = `JARVIS · via ${provider || '—'} · ${full.length} chars`;
    renderSession();
    if (settings.ttsOn) speak(full);
  } else if (!err) {
    bubble.textContent = '⚠ Resposta vazia do provedor.';
  }

  busy = false;
  sendBtn.disabled = false;
  if (window.__jarvisCoreMode === 'busy') setCoreMode('idle');
  $('#chatState').innerHTML = '<span class="dot green blink"></span>PRONTO';
  log.scrollTop = log.scrollHeight;
});

/**
 * Processa um comando dito junto com a palavra-chave ("Jarvis, ...") sem abrir o
 * chat: responde por voz e mostra um toast discreto. O histórico continua.
 */
async function askBackground(text) {
  state.history.push({ role: 'user', content: text });
  let provider = null;
  let full = '';
  let err = null;
  setCoreMode('busy');   // mesmo comando por voz: o núcleo fica âmbar enquanto pensa
  try {
    const r = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ messages: [{ role: 'system', content: SYS_PROMPT }, ...state.history.slice(-20)] }),
    });
    if (!r.ok || !r.body) throw new Error(`HTTP ${r.status}`);
    await consumeSSE(r, (ev, d) => {
      if (ev === 'start') provider = d.provider;
      else if (ev === 'tool') handleToolEvent(d);
      else if (ev === 'delta' && d.t) full += d.t;
      else if (ev === 'error') err = d.message;
    });
  } catch (e) {
    err = e.message;
  }

  if (full) {
    state.history.push({ role: 'assistant', content: full });
    state.turns += 1;
    renderSession();
  }
  const answer = (full || err || 'sem resposta').replace(/\s+/g, ' ').trim();
  setCoreMode(full ? 'idle' : 'error', full ? 0 : 2500);
  pushEvent(full ? 'ok' : 'err', 'Resposta em segundo plano', answer.slice(0, 140));
  toast(`Jarvis: ${answer.slice(0, 140)}`);
  if (settings.ttsOn && full) speak(full.slice(0, 600));
}

/* ── configurações ─────────────────────────────── */
const modal = $('#settingsModal');

/* Vozes em reserva: aparecem se o backend não responder. */
const PIPER_VOICES_FALLBACK = ['pt_BR-cadu-medium.onnx', 'pt_BR-faber-medium.onnx', 'pt-BR-razo-medium.onnx'];
const EDGE_VOICES_FALLBACK = ['pt-BR-AntonioNeural', 'pt-BR-NicolauNeural', 'pt-BR-FranciscaNeural', 'pt-BR-ThalitaNeural'];
const TTS_ENGINE_DEFAULT_VOICE = { edge: 'pt-BR-AntonioNeural', piper: 'pt_BR-cadu-medium.onnx' };

function setEngineUI(eng) {
  const e = eng === 'edge' ? 'edge' : 'piper';
  const box = $('#setTtsEngine');
  if (box) {
    for (const b of box.querySelectorAll('.seg-btn')) b.classList.toggle('on', b.dataset.engine === e);
  }
  const pitch = $('#setPitch');
  if (pitch) pitch.disabled = e === 'edge';
  const hint = $('#engineHint');
  if (hint) {
    hint.textContent = e === 'edge'
      ? 'Edge TTS: vozes neurais da Microsoft (mais naturais, mas genéricas; precisam de internet). A velocidade se aplica; o tom fica no padrão. Se falhar, o Piper assume.'
      : 'Piper (padrão): voz cadu, local e offline — nada sai da máquina, e o timbre mais grave combina com o JARVIS. Velocidade e tom se aplicam. Se falhar, o Edge TTS assume.';
  }
}

async function openSettings() {
  try {
    const r = await fetch('/api/config');
    const c = await r.json();
    $('#setGroqKey').value = c.groqKey || '';
    $('#setGroqModel').value = c.groqModel || '';
    if (c.tts_engine) settings.ttsEngine = c.tts_engine === 'edge' ? 'edge' : 'piper';
    if (c.tts_voice) {
      if (settings.ttsEngine === 'edge') settings.voiceEdge = c.tts_voice;
      settings.voice = c.tts_voice;
    }
    saveLocal();
    // tempo de escuta contínua vem do config.json (é do backend, não do localStorage)
    if (c.continuous_listen_minutes !== undefined && c.continuous_listen_minutes !== null) {
      settings.continuousMinutes = Number(c.continuous_listen_minutes);
    }
  } catch { /* mantém */ }
  $('#setRate').value = settings.rate;
  $('#rateOut').textContent = `${Number(settings.rate).toFixed(2)}×`;
  $('#setPitch').value = settings.pitch;
  $('#pitchOut').textContent = `${Number(settings.pitch) >= 0 ? '+' : '−'}${Math.abs(Number(settings.pitch)).toFixed(1)}`;
  const cont = $('#setContinuousMin');
  if (cont) cont.value = String(Number(settings.continuousMinutes) || 0);
  setEngineUI(ttsEngine());
  await loadVoices(ttsEngine());
  $('#settingsMsg').textContent = '';
  modal.hidden = false;
}

/* Lista de vozes do motor escolhido: Piper (arquivos locais) ou Edge (neurais). */
async function loadVoices(engine) {
  const sel = $('#setVoice');
  if (!sel) return;
  const eng = engine === 'edge' ? 'edge' : 'piper';
  const current = eng === 'edge' ? (settings.voiceEdge || TTS_ENGINE_DEFAULT_VOICE.edge) : (settings.voicePiper || settings.voice || TTS_ENGINE_DEFAULT_VOICE.piper);
  sel.innerHTML = '';
  const add = (value, text) => {
    const o = document.createElement('option');
    o.value = value;
    o.textContent = text;
    sel.appendChild(o);
  };
  if (eng === 'edge') {
    try {
      const r = await fetch(`${BACKEND_URL}/voices-edge`, { cache: 'no-store' });
      const v = await r.json();
      for (const item of v.available || []) {
        add(item.name, `${item.name.replace('pt-BR-', '').replace('Neural', '')}${item.note ? ` — ${item.note}` : ''}`);
      }
    } catch { /* backend off */ }
    if (!sel.options.length) for (const n of EDGE_VOICES_FALLBACK) add(n, n.replace('pt-BR-', '').replace('Neural', ''));
  } else {
    try {
      const r = await fetch(`${BACKEND_URL}/voices`, { cache: 'no-store' });
      const v = await r.json();
      for (const item of v.available || []) add(item.name, `${item.name.replace('.onnx', '')} (local · ${item.size_mb} MB)`);
      const have = new Set((v.available || []).map((i) => i.name));
      for (const item of v.downloadable || []) {
        if (!have.has(item.name)) add(item.name, `${item.name.replace('.onnx', '')} (baixar)`);
      }
    } catch { /* backend off */ }
    if (!sel.options.length) for (const n of PIPER_VOICES_FALLBACK) add(n, n.replace('.onnx', ''));
  }
  if (current) sel.value = current;
  if (!sel.value && sel.options.length) sel.selectedIndex = 0;
  settings.voice = sel.value;
}
$('#gearBtn').addEventListener('click', openSettings);
on('#manageProviders', 'click', openSettings);
$('#navSettings').addEventListener('click', openSettings);
$('#closeSettings').addEventListener('click', () => (modal.hidden = true));
modal.addEventListener('click', (e) => { if (e.target === modal) modal.hidden = true; });
$('#setTtsEngine').addEventListener('click', async (e) => {
  const btn = e.target.closest('.seg-btn');
  if (!btn) return;
  const eng = btn.dataset.engine === 'edge' ? 'edge' : 'piper';
  if (eng === ttsEngine()) return;
  // guarda a voz do motor anterior antes de trocar a lista
  if (ttsEngine() === 'edge') settings.voiceEdge = settings.voice || settings.voiceEdge;
  else settings.voicePiper = settings.voice || settings.voicePiper;
  settings.ttsEngine = eng;
  saveLocal();
  setEngineUI(eng);
  await loadVoices(eng);
});
$('#setRate').addEventListener('input', (e) => {
  $('#rateOut').textContent = `${Number(e.target.value).toFixed(2)}×`;
});
$('#setPitch').addEventListener('input', (e) => {
  const v = Number(e.target.value);
  $('#pitchOut').textContent = `${v >= 0 ? '+' : '−'}${Math.abs(v).toFixed(1)}`;
});
$('#saveSettings').addEventListener('click', async () => {
  settings.rate = Number($('#setRate').value) || 1.35;
  settings.pitch = Number($('#setPitch').value) || 0;
  settings.voice = $('#setVoice').value;
  settings.ttsEngine = ttsEngine();
  if (settings.ttsEngine === 'edge') settings.voiceEdge = settings.voice;
  else settings.voicePiper = settings.voice;
  const contEl = $('#setContinuousMin');
  if (contEl) {
    const m = Math.max(0, Math.min(1440, Math.floor(Number(contEl.value) || 0)));
    settings.continuousMinutes = m;
    contEl.value = String(m);
  }
  saveLocal();
  const saved = await fetch('/api/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      groqKey: $('#setGroqKey').value.trim(),
      groqModel: $('#setGroqModel').value.trim(),
      continuous_listen_minutes: Number(settings.continuousMinutes) || 0,
      tts_engine: settings.ttsEngine,
      tts_voice: settings.voice,
    }),
  }).then((r) => r.json()).catch(() => ({}));
  if (saved.tts_engine) settings.ttsEngine = saved.tts_engine;
  if (saved.tts_voice) settings.voice = saved.tts_voice;
  saveLocal();
  // aplica já o novo tempo (reinicia o timer se a escuta contínua estiver ativa)
  if (continuousListening) resetContinuousTimer();
  $('#settingsMsg').textContent = '✔ Salvo.';
  const engineLabel = settings.ttsEngine === 'edge' ? 'Edge TTS' : 'Piper';
  pushEvent('ok', 'Configurações salvas', `${engineLabel} · voz ${settings.voice || 'padrão'} · velocidade ${settings.rate}×`);
  await refreshStatus();
  toast('Configurações salvas');
});
$('#previewVoice').addEventListener('click', () => {
  settings.rate = Number($('#setRate').value) || 1.35;
  settings.pitch = Number($('#setPitch').value) || 0;
  settings.voice = $('#setVoice').value;
  settings.ttsEngine = ttsEngine();
  if (settings.ttsEngine === 'edge') settings.voiceEdge = settings.voice;
  else settings.voicePiper = settings.voice;
  saveLocal();
  speak('Sistemas operacionais. Esta é a voz configurada para o senhor, comandante.');
});
$('#downloadVoice').addEventListener('click', async () => {
  const msg = $('#settingsMsg');
  msg.textContent = 'Baixando pt_BR-faber-medium (~63 MB), aguarde...';
  try {
    const r = await fetch(`${BACKEND_URL}/voices/download`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: 'pt_BR-faber-medium' }),
    });
    const j = await r.json();
    msg.textContent = r.ok ? `✔ ${j.name} baixada (${j.size_mb} MB). Selecione e ouça.` : `✖ ${j.error}`;
    await loadVoices();
    if (r.ok) pushEvent('ok', 'Nova voz baixada', `${j.name} (${j.size_mb} MB)`);
  } catch (e) {
    msg.textContent = `✖ ${e.message}`;
  }
});

/* ── busca → chat ──────────────────────────────── */
$('#search').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && e.target.value.trim()) {
    userOpenChat(e.target.value.trim());
    form.requestSubmit();
  }
});
$('#micBtn').addEventListener('click', startManual);
$('#chatMic').addEventListener('click', startManual);
$('#micTestBtn').addEventListener('click', startMicTest);
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    form.requestSubmit();
  }
});

/* ── teste rápido do microfone ─────────────────── */
let micTester = null;
async function startMicTest() {
  if (micTester) return;
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const src = ctx.createMediaStreamSource(stream);
    const analyser = ctx.createAnalyser();
    analyser.fftSize = 128;
    src.connect(analyser);
    const data = new Uint8Array(analyser.frequencyBinCount);
    const lvlEl = $('#micTesterLvl');
    const barEl = $('#micTesterBar');
    const tester = $('#micTester');
    tester.hidden = false;
    const end = Date.now() + 25000;
    function tick() {
      if (Date.now() > end || !micTester) { stopMicTest(); return; }
      analyser.getByteFrequencyData(data);
      let sum = 0;
      for (let i = 0; i < data.length; i++) sum += data[i];
      const avg = sum / data.length;
      const db = avg > 0 ? (20 * Math.log10(avg / 128)).toFixed(1) : '-∞';
      lvlEl.textContent = `nível ${db} dB`;
      const pct = Math.min(100, Math.max(0, (avg / 128) * 100));
      barEl.style.width = `${pct}%`;
      requestAnimationFrame(tick);
    }
    micTester = { stream, ctx, tick };
    micTester.tick();
  } catch (e) {
    $('#micTesterLvl').textContent = 'sem áudio';
    toast('Microfone indisponível para teste');
  }
}
function stopMicTest() {
  if (!micTester) return;
  const { stream, ctx } = micTester;
  micTester = null;
  try { stream.getTracks().forEach((t) => t.stop()); } catch { /* ignora */ }
  try { ctx.close(); } catch { /* ignora */ }
  $('#micTester').hidden = true;
  $('#micTesterBar').style.width = '0%';
  $('#micTesterLvl').textContent = 'silêncio';
}

/* ── visualizador 3D (abre no navegador padrão) ── */
async function visualize3d(prompt) {
  const clean = String(prompt || '').replace(/\s+/g, ' ').trim().slice(0, 200);
  if (!clean) return;
  // nunca abre o chat: só toast + voz
  toast('Abrindo visualização 3D...');
  pushEvent('tool', 'Visualizador 3D', clean);
  try {
    const r = await fetch(`${BACKEND_URL}/visualize-3d`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: clean }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.ok) {
      const msg = j.error || `HTTP ${r.status}`;
      toast(`3D: ${msg}`);
      pushEvent('err', 'Visualizador 3D', String(msg).slice(0, 120));
      return;
    }
    const msg = j.message || `Abrindo o ${clean} no navegador, Comandante.`;
    toast(msg);
    pushEvent('ok', 'Visualizador 3D', `${clean} · ${j.size || 0} bytes`);
    if (settings.ttsOn) speak(msg);
  } catch (e) {
    toast('Falha ao abrir a visualização 3D');
    pushEvent('err', 'Visualizador 3D', String(e.message || e));
  }
}

const vizRow = $('#viz3dRow');
$('#viz3dBtn').addEventListener('click', () => {
  if (!vizRow) return;
  vizRow.hidden = !vizRow.hidden;
  if (!vizRow.hidden) $('#viz3dInput').focus();
});
if (vizRow) {
  const goViz = () => {
    const v = $('#viz3dInput').value.trim();
    if (!v) return;
    vizRow.hidden = true;
    $('#viz3dInput').value = '';
    visualize3d(v);
  };
  $('#viz3dGo').addEventListener('click', goViz);
  $('#viz3dInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); goViz(); }
  });
}

/* ── modo programador: 💻 Programar → /generate-code do backend ── */
async function generateCode(prompt) {
  const clean = String(prompt || '').replace(/\s+/g, ' ').trim().slice(0, 500);
  if (!clean) return;
  toast('Gerando código...');
  pushEvent('tool', 'Modo programador', clean);
  try {
    const r = await fetch(`${BACKEND_URL}/generate-code`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: clean }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.ok) {
      const msg = j.error || `HTTP ${r.status}`;
      toast(`Código: ${msg}`);
      pushEvent('err', 'Modo programador', String(msg).slice(0, 120));
      return;
    }
    const msg = j.message || 'Pronto, Comandante. Gerei o código e abri no seu editor.';
    toast(msg);
    pushEvent('ok', 'Modo programador', `${clean} · .${j.language || 'txt'} ${j.size || 0} bytes`);
    if (settings.ttsOn) speak(msg);
  } catch (e) {
    toast('Falha ao gerar o código');
    pushEvent('err', 'Modo programador', String(e.message || e));
  }
}

const codeRow = $('#codeRow');
$('#codeBtn').addEventListener('click', () => {
  if (!codeRow) return;
  codeRow.hidden = !codeRow.hidden;
  if (!codeRow.hidden) $('#codeInput').focus();
});
if (codeRow) {
  const goCode = () => {
    const v = $('#codeInput').value.trim();
    if (!v) return;
    codeRow.hidden = true;
    $('#codeInput').value = '';
    generateCode(v);
  };
  $('#codeGo').addEventListener('click', goCode);
  $('#codeInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { e.preventDefault(); goCode(); }
  });
}

/* ── clima (HUD): 🌤️ Clima → /weather do backend ─ */
/* Horário da medição: open-meteo manda "2026-10-11T09:30", wttr.in manda "12:32 PM".
   Os dois viram HH:MM — é o que diz se o dado está fresco. */
function fmtMeasured(value) {
  const s = String(value || '').trim();
  if (!s) return '';
  const iso = s.match(/T(\d{2}:\d{2})/);
  if (iso) return iso[1];
  const m = s.match(/(\d{1,2}):(\d{2})\s*([APap]\.?[Mm]\.?)?/);
  if (!m) return s;
  let hh = Number(m[1]);
  const ampm = String(m[3] || '').replace(/\./g, '').toLowerCase();
  if (ampm.startsWith('p') && hh < 12) hh += 12;
  else if (ampm.startsWith('a') && hh === 12) hh = 0;
  return `${String(hh).padStart(2, '0')}:${m[2]}`;
}

async function showWeather() {
  const box = $('#weatherBox');
  if (!box) return;
  try {
    const r = await fetch(`${BACKEND_URL}/weather`, { cache: 'no-store' });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.ok) throw new Error(j.error || `HTTP ${r.status}`);
    const medido = fmtMeasured(j.medido_em);
    $('#wxCity').textContent = j.cidade || '—';
    $('#wxSrc').textContent = `${j.fonte || ''}${medido ? ' · ' + medido : ''}`;
    $('#wxTemp').textContent = j.temp == null ? '—' : `${j.temp}°C`;
    $('#wxDesc').textContent = j.descricao || '';
    $('#wxFeels').textContent = j.sensacao == null ? '—' : `${j.sensacao}°C`;
    $('#wxHum').textContent = j.umidade == null ? '—' : `${j.umidade}%`;
    $('#wxWind').textContent = j.vento || '—';
    $('#wxRange').textContent = `${j.max ?? '—'}° / ${j.min ?? '—'}°`;
    const wxMeasured = $('#wxMeasured');
    if (wxMeasured) wxMeasured.textContent = medido ? `${medido} · ${j.fonte || ''}` : (j.fonte || '—');
    box.hidden = false;
    pushEvent('ok', 'Clima', `${j.cidade}: ${j.temp}°C, ${j.descricao}${medido ? ` · medido às ${medido}` : ''}`);
  } catch (e) {
    box.hidden = true;
    toast(`Clima indisponível: ${e.message || e}`);
    pushEvent('err', 'Clima', String(e.message || e).slice(0, 120));
  }
}
$('#weatherBtn').addEventListener('click', () => {
  const box = $('#weatherBox');
  if (box && !box.hidden) { box.hidden = true; return; }
  showWeather();
});

/* ── memórias (HUD): 🧠 Memórias → /memory/* do backend ─ */
function fmtMemTime(ts) {
  if (!ts) return '';
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return String(ts).slice(0, 16);
  const day = d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
  const hour = d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  return `${day} ${hour}`;
}

async function loadMemories() {
  const box = $('#memoryBox');
  if (!box) return;
  try {
    const [stRes, lsRes] = await Promise.all([
      fetch(`${BACKEND_URL}/memory/stats`, { cache: 'no-store' }),
      fetch(`${BACKEND_URL}/memory/list?limit=20`, { cache: 'no-store' }),
    ]);
    const st = await stRes.json().catch(() => ({}));
    const ls = await lsRes.json().catch(() => ({}));
    if (!stRes.ok || !st.ok) throw new Error(st.error || `HTTP ${stRes.status}`);
    $('#memTotal').textContent = `${st.total || 0} memória(s)`;
    const ul = $('#memList');
    ul.innerHTML = '';
    for (const m of (ls.memories || [])) {
      const li = document.createElement('li');
      li.className = 'mem-item';
      const info = document.createElement('div');
      const when = document.createElement('small');
      const cat = m.category || 'outros';
      when.textContent = `${fmtMemTime(m.timestamp)}${m.source ? ' · ' + m.source : ''}`;
      const tag = document.createElement('span');
      tag.className = `mem-cat cat-${cat}`;
      tag.textContent = m.archived ? `${cat} · arquivada` : cat;
      const txt = document.createElement('b');
      txt.textContent = m.text;
      if (m.archived) li.classList.add('mem-archived');
      info.append(when, tag, txt);
      const btn = document.createElement('button');
      btn.className = 'mem-forget';
      btn.textContent = 'Esquecer';
      btn.addEventListener('click', async () => {
        if (!confirm('Esquecer esta memória?')) return;
        try {
          const r = await fetch(`${BACKEND_URL}/memory/${encodeURIComponent(m.id)}`, { method: 'DELETE' });
          const j = await r.json().catch(() => ({}));
          if (!r.ok || !j.ok) throw new Error(j.error || `HTTP ${r.status}`);
          pushEvent('ok', 'Memória esquecida', String(m.text).slice(0, 60));
          loadMemories();
        } catch (e) {
          toast(`Falha ao esquecer: ${e.message || e}`);
        }
      });
      li.append(info, btn);
      ul.append(li);
    }
    box.hidden = false;
  } catch (e) {
    box.hidden = true;
    toast(`Memórias indisponíveis: ${e.message || e}`);
    pushEvent('err', 'Memórias', String(e.message || e).slice(0, 120));
  }
}

$('#memoryBtn').addEventListener('click', () => {
  const box = $('#memoryBox');
  if (box && !box.hidden) { box.hidden = true; return; }
  loadMemories();
});
$('#memRefresh').addEventListener('click', loadMemories);
$('#memReset').addEventListener('click', async () => {
  if (!confirm('Resetar TODAS as memórias? Isso não tem volta.')) return;
  try {
    const r = await fetch(`${BACKEND_URL}/memory/all`, { method: 'DELETE' });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.ok) throw new Error(j.error || `HTTP ${r.status}`);
    pushEvent('warn', 'Memórias resetadas', `${j.removed || 0} apagadas`);
    toast('Memórias resetadas, Senhor.');
    loadMemories();
  } catch (e) {
    toast(`Falha ao resetar: ${e.message || e}`);
  }
});

/* ── notícias (HUD): 📰 Notícias → /news/brasil (G1 / the news) ─ */
const NEWS_TOPICS = {
  g1: [['geral', 'Geral'], ['tecnologia', 'Tecnologia'], ['economia', 'Economia'],
       ['esportes', 'Esportes'], ['mundo', 'Mundo'], ['politica', 'Política'], ['ciencia', 'Ciência e saúde']],
  thenews: [['geral', 'Geral'], ['mercado', 'Mercado'], ['tecnologia', 'Tecnologia'], ['mundo', 'Mundo']],
};
let newsItems = [];

function newsSource() {
  const el = $('#newsSource');
  return el && el.value === 'thenews' ? 'thenews' : 'g1';
}

function fillNewsTopics() {
  const sel = $('#newsTopic');
  if (!sel) return;
  sel.innerHTML = '';
  for (const [value, label] of NEWS_TOPICS[newsSource()]) {
    const o = document.createElement('option');
    o.value = value;
    o.textContent = label;
    sel.appendChild(o);
  }
}

async function loadNews() {
  const src = newsSource();
  const tpc = ($('#newsTopic') && $('#newsTopic').value) || 'geral';
  const info = $('#newsInfo');
  info.textContent = 'buscando…';
  try {
    const r = await fetch(`${BACKEND_URL}/news/brasil?source=${encodeURIComponent(src)}&topic=${encodeURIComponent(tpc)}&limit=5`, { cache: 'no-store' });
    const j = await r.json().catch(() => ({}));
    if (!j.ok) throw new Error(j.error || `HTTP ${r.status}`);
    newsItems = j.items || [];
    const ul = $('#newsList');
    ul.innerHTML = '';
    for (const it of newsItems) {
      const li = document.createElement('li');
      li.className = 'mem-item';
      const box = document.createElement('div');
      const when = document.createElement('small');
      when.textContent = `${(it.fonte || src).toUpperCase()}${it.data ? ' · ' + String(it.data).slice(0, 22) : ''}`;
      const b = document.createElement('b');
      b.textContent = it.titulo || it.resumo || '';
      box.append(when, b);
      if (it.resumo && it.resumo !== b.textContent) {
        const res = document.createElement('small');
        res.textContent = it.resumo;
        box.append(res);
      }
      li.append(box);
      if (it.link) {
        const a = document.createElement('a');
        a.className = 'news-link';
        a.href = it.link;
        a.target = '_blank';
        a.rel = 'noopener noreferrer';
        a.textContent = 'Abrir';
        li.append(a);
      }
      ul.append(li);
    }
    info.textContent = `${newsItems.length} · ${src === 'thenews' ? 'the news' : 'G1'}/${tpc}`;
    $('#newsBox').hidden = false;
    pushEvent('info', 'Notícias carregadas', `${src}/${tpc}: ${newsItems.length} manchete(s)`);
  } catch (e) {
    info.textContent = 'indisponível';
    toast(`Notícias indisponíveis: ${e.message || e}`);
  }
}

$('#newsBtn').addEventListener('click', () => {
  const row = $('#newsRow');
  if (row && row.hidden) {
    fillNewsTopics();
    row.hidden = false;
    return;
  }
  if (row) row.hidden = true;
  const box = $('#newsBox');
  if (box && !box.hidden) box.hidden = true;
});
$('#newsSource').addEventListener('change', fillNewsTopics);
$('#newsGo').addEventListener('click', loadNews);
$('#newsRefresh').addEventListener('click', loadNews);
$('#newsSpeak').addEventListener('click', () => {
  const txt = newsItems.slice(0, 3).map((i) => i.titulo || i.resumo || '').filter(Boolean).join('. ');
  if (txt) speak(txt);
});

/* ── rede ──────────────────────────────────────── */
addEventListener('online', () => {
  pushEvent('ok', 'Rede restaurada', 'conexão de volta');
  $('#sfNet').textContent = 'Online';
  $('#tbNet').textContent = 'Online';
});
addEventListener('offline', () => {
  pushEvent('warn', 'Rede caiu', 'sem conexão com a internet');
  $('#sfNet').textContent = 'Offline';
  $('#tbNet').textContent = 'Offline';
});

/* ── lembretes da agenda (aviso por voz) ───────── */
const announcedEvents = new Set();
async function checkAgenda() {
  try {
    const r = await fetch(`${BACKEND_URL}/agenda/check?window=5`, { method: 'POST' });
    const j = await r.json();
    for (const ev of j.events || []) {
      if (announcedEvents.has(ev.id)) continue;
      announcedEvents.add(ev.id);
      const hhmm = String(ev.datetime || '').slice(11, 16);
      toast(`Agenda: ${ev.title} — ${hhmm}`);
      pushEvent('warn', 'Lembrete da agenda', `${ev.title} às ${hhmm}`);
      if (settings.ttsOn) speak(`Comandante, lembrete: ${ev.title} às ${hhmm}.`);
    }
  } catch { /* backend fora do ar */ }
}

/* ── inicialização ─────────────────────────────── */
(async function init() {
  loadEvents();
  renderFeed();
  renderActivity();
  renderSession();
  updateTtsUI();
  updateWakeUI();
  setListeningUI(false);
  renderCore();
  renderModules();
  await Promise.all([pollSysinfo(), pollHealth(), refreshStatus()]);
  setInterval(pollSysinfo, 4000);
  setInterval(pollHealth, 30000);
  setInterval(refreshStatus, 20000);
  pushEvent('info', 'JARVIS iniciado', `host ${state.sys ? state.sys.hostname : '—'} · escuta contínua ${settings.wake ? 'ON' : 'OFF'}`);
  if (settings.wake) startWake();
  // se o navegador exigir gesto/permissão para o microfone, tenta de novo ao clicar
  const retryWake = () => {
    if (settings.wake && !wakeRunning) startWake();
    if (wakeRunning && !wakeBlocked) document.removeEventListener('click', retryWake);
  };
  document.addEventListener('click', retryWake);
  // avisos de agenda: checa a cada minuto os eventos dos próximos 5 minutos
  setTimeout(checkAgenda, 6000);
  setInterval(checkAgenda, 60000);
})();
