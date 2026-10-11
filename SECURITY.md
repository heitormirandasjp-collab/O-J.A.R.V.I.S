# JARVIS — Segurança

Este documento descreve as proteções implementadas no JARVIS (backend Python
`backend/main.py`, servidor de chat/UI `app.py` + `server.js`, interface `public/`)
e como estendê-las.

O JARVIS roda **apenas em localhost** (ferramentas/voz na porta `8000`, interface/chat
na porta `8755`) e executa ações reais na máquina do Comandante. Por isso o modelo é
tratado como **não confiável**: toda ação passa por validação no backend.

---

## 1. Execução de comandos — `POST /exec` (`backend/main.py`)

| Proteção | Detalhe |
|---|---|
| **Blacklist** | Comandos destrutivos/de sistema são bloqueados antes de executar: `rm -rf`, `del /f /s`, `format C:`, `mkfs`, `diskpart`, `fdisk`, `dd if=`, fork bomb, `shutdown`/`reboot`/`poweroff`, `bcdedit`, `vssadmin`, `cipher /w`, `wevtutil cl`, `reg delete`, `takeown`, `icacls /grant`, `net user`/`net localgroup`, `sc delete`, `schtasks /create`, `netsh firewall`, `wmic … delete`, `Remove-Item -Recurse`, `mklink` → **HTTP 403** |
| **Timeout** | Padrão e **máximo de 30 s** por comando (`EXEC_TIMEOUT_MAX`) |
| **Limite de saída** | **10.000 caracteres** por comando (`EXEC_OUTPUT_LIMIT`), com `truncated: true` |
| **Limite de entrada** | Comando com mais de 1000 caracteres → **HTTP 413** |
| **Histórico** | Todos os comandos executados vão para `exec_history.json` (últimos 200) |
| **Log** | Execuções, timeouts e bloqueios vão para `security.log` |

> `/exec` roda com `shell=True` de propósito (é o terminal do Comandante). A blacklist
> reduz o risco de autodestruição; ela **não** é uma sandbox. Energia (`shutdown`,
> `restart`, `hibernate`, `sleep`) só existe pelo endpoint próprio `/power`, com confirmação.

## 2. Leitura de arquivos — `POST /read-file` (`backend/main.py`)

| Proteção | Detalhe |
|---|---|
| **Arquivos sensíveis** | Bloqueados por nome (`.env`, `.netrc`, `.git-credentials`, `id_rsa`, `id_ed25519`, `shadow`, `passwd`, `sam`, `security`, `config.json`…), por extensão (`.key`, `.pem`, `.pfx`, `.p12`, `.kdbx`, `.jks`, `.keystore`, `.ppk`, `.asc`, `.ovpn`) e por caminho (`…\System32\config`, `…\System32\SAM`, `%APPDATA%\Microsoft\Credentials`, `/etc/shadow`, `/etc/passwd`, `/etc/sudoers`, `.ssh/`, `/root/`, `.git/config`) → **HTTP 403** |
| **Pastas permitidas** | Somente **Documents**, **Downloads**, **Desktop** (do usuário), a pasta do app e a pasta de dados (`%APPDATA%\JARVIS`); compare com caminho normalizado (funciona com `\` ou `/`) |
| **Tamanho** | Máximo **1 MB** por arquivo (`READ_MAX_BYTES`), com `truncated: true` |
| **Log** | Leitura permitida e tentativa bloqueada vão para `security.log` |

Ampliar as pastas permitidas (ex.: uma pasta de projetos):

```bat
set JARVIS_READ_ROOTS=D:\Projetos;E:\Docs
```

## 3. Desligamento/reinício — `POST /power` (`backend/main.py` + `app.py`)

- O desligamento **nunca** executa direto: `/power` **registra o pedido** e o fluxo de
  confirmação só libera a execução quando o Comandante responde **"sim"** na próxima mensagem
  (`AFFIRM_RE`); um **"não"/"cancela"** limpa o pedido (`DENY_RE`).
- O campo `confirmed` vindo **do modelo é descartado** (`args.pop("confirmed", None)` no
  `app.py` e no `server.js`) — o modelo não pode confirmar por conta própria.
- **TTL de 120 s** (`POWER_CONFIRM_TTL`): pedido expirado exige nova ordem explícita.
- Uma mesma ordem executa **no máximo um** desligamento.
- `POST /power` tem carência de **30 s** (`shutdown /s /t 30`), cancelável com `POST /power/cancel`.
- **Log** de todos os pedidos: registrados, confirmados, cancelados e expirados.
- `JARVIS_POWER_DRY_RUN=1` percorre toda a cadeia **sem desligar** (modo simulação).

## 4. Voz / TTS — `POST /tts` (`backend/main.py`)

- Texto limitado a **2000 caracteres** (`TTS_MAX_CHARS`) — o excesso é truncado e registrado.
- `_sanitize_tts()` remove **caracteres de controle** (`\x00-\x1f`, `\x7f`) e **tags/SSML**
  (`<…>`) antes de chegar ao sintetizador, então não há injeção de SSML nem de comandos
  (vale para os dois motores).
- `_speech_text()` ainda normaliza URLs, emojis, sufixos de fonte, números, horas e valores.
- **Dois motores** (`engine`): `piper` (padrão, local — voz cadu) e `edge`. Valor desconhecido
  é registrado no `security.log` e tratado como `piper`.
- **Edge TTS é o único ponto que sai do computador para falar**: com `engine=edge` o texto
  falado é enviado em HTTPS para o serviço `edge-tts` da Microsoft (nada é gravado em disco
  do lado de lá por nós, e não há chave de API). O **padrão é o Piper**, que não sai da
  máquina: só quem escolher o Edge TTS nas configurações envia a frase para fora.
- **Reserva nos dois sentidos**: com `engine=piper` (padrão), se a voz local não existir ou o
  modelo estiver corrompido, o `/tts` sintetiza com o Edge TTS; com `engine=edge`, se faltar
  internet ou o serviço falhar, ele cai para o Piper local. As duas quedas são registradas no
  `security.log` — quem exige que **nada** saia da máquina deve desligar o Edge TTS por
  completo (ou remover a biblioteca `edge-tts`), já que a reserva é automática.
- **Nome de voz validado**: `_edge_voice()` só aceita `pt-BR-*` (resto do nome é descartado
  por regex — `[A-Za-z0-9-]`); no Piper, `resolve_voice()` só aceita um arquivo `.onnx` que
  exista de verdade na pasta de vozes. Nenhum caminho de arquivo vem do cliente.
- A voz/engine escolhidos também são validados em `app.py` (`clamp_tts_engine`/`clamp_tts_voice`)
  antes de ir para o `config.json`, então um valor do front nunca vira caminho nem comando.

## 5. Chat / LLM — `POST /api/chat` (`app.py` e `server.js`)

| Proteção | Detalhe |
|---|---|
| **Rate limit** | **30 chamadas por minuto** (janela deslizante) → **HTTP 429** |
| **Entrada** | Mensagem do usuário com mais de **5000 caracteres** → **HTTP 413** |
| **Saída** | Resposta do modelo limitada a **10.000 caracteres** (corta o streaming) |
| **Sanitização** | `strip_html()` remove `<script>`/`<style>` e demais tags antes de enviar ao front (a UI também escapa tudo com `esc()`) |
| **Prompt do sistema** | O `system` enviado pelo front é **descartado**: o prompt de personalidade do backend é sempre aplicado |
| **Contexto dinâmico** | `detect_context()`/`build_context_block()` geram só texto a partir do **horário local** e de palavras-chave fixas da mensagem (4 modos). Nada é interpolado sem sanitização e o bloco só orienta tom — a própria diretriz manda não alterar fatos nem memórias |

## 6. Configuração e segredos

- `config.json` (chave da Groq) é gravado com permissão **0600** (`mode 0o600` / `os.chmod`)
  — só o usuário lê.
- `GET /api/config/masked` (e `POST /config/masked`) devolve a chave **mascarada**
  (`gsk••••7890`), nunca o segredo — seguro para exibir/logar.
- `POST /api/config` **ignora valores mascarados** (`••••`, `****`): um placeholder nunca
  sobrescreve a chave real.
- `GET /api/status` também devolve apenas a chave mascarada.

## 7. CORS e headers

- CORS restrito a **`http://127.0.0.1:8755`** e **`http://localhost:8755`** (nunca `"*"`),
  métodos `GET/POST/DELETE/OPTIONS`, header `Content-Type`, sem credenciais.
  Sobrescrever: `set JARVIS_ALLOWED_ORIGINS=http://127.0.0.1:9000`.
- Headers em todas as respostas: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`
  (e `Cross-Origin-Opener-Policy: same-origin` no `app.py`).

## 8. Logs de segurança

Arquivo **`%APPDATA%\JARVIS\security.log`** (em dev, `jarvis/security.log`), uma linha por evento:

```
2026-10-10T15:11:59 [exec] cmd='ipconfig' exit=0
2026-10-10T15:11:59 [exec] BLOQUEADO comando bloqueado (blacklist): shutdown /s /t 0
2026-10-10T15:11:59 [read-file] C:\Users\WIN\Documents\nota.txt (182 bytes)
2026-10-10T15:11:59 [read-file] BLOQUEADO fora das pastas permitidas: C:\Windows\win.ini
2026-10-10T15:12:00 [power] pedido registrado (aguardando sim): {'action': 'shutdown'}
2026-10-10T15:12:05 [power] pedido CANCELADO pelo Comandante (shutdown)
2026-10-10T15:12:10 [power] pedido CONFIRMADO pelo Comandante (shutdown)
2026-10-10T15:12:10 [power] pedido expirado sem confirmação (restart)
2026-10-10T15:12:20 [chat] BLOQUEADO rate limit excedido (30/60s)
2026-10-10T15:12:30 [chat] BLOQUEADO mensagem acima de 5000 caracteres
2026-10-10T15:13:00 [config] BLOQUEADO tentativa de gravar chave mascarada
2026-10-10T15:14:00 [visualize-3d] um carro vermelho (572 bytes) -> jarvis-3d-8c12….html
2026-10-10T15:14:30 [visualize-3d] fechado pelo usuário e removido: 8c12…
2026-10-10T15:24:00 [visualize-3d] limpeza automática: 8c12…
```

Cobre: comandos executados, arquivos lidos, tentativas de desligamento (registradas,
confirmadas, canceladas e expiradas), erros de validação/bloqueios e uso do visualizador 3D
e do modo programador.

## 9. Visualizador 3D — `POST /visualize-3d` (`backend/main.py`)

- **Prompt** limitado a **200 caracteres**; `_vis3d_sanitize()` remove tags HTML, tokens de
  script (`javascript`, `onerror`, `eval`, `document`…), metacaractere de shell (`; | & $ > < { }`
  backtick, `\`), URLs/`file://` e palavras de comando (`rm`, `del`, `format`, `shutdown`,
  `powershell`…). Prompt vazio após limpeza → **HTTP 400**.
- O HTML é **gerado pela Groq** (`max_tokens: 16384`, senão o gpt-oss corta a resposta),
  então é validado: precisa começar com `<!DOCTYPE html`/`<html` **e terminar com `</html>`
  contendo `renderer.render`/`requestAnimationFrame` (HTML incompleto = página preta, tenta
  de novo, até 2 tentativas) e é cortado em **500 KB** (`VIS3D_MAX_HTML`).
  Além disso, o backend exige que o HTML mencione **300.000 partículas** ou contenha
  estrutura do THREE.Points com BufferGeometry (verificados por expressões regulares na
  função `_vis3d_extract_html`), senão considera inválido e tenta outro modelo.
- A **URL do beacon é reescrita** com o id real do arquivo antes de gravar: o modelo não
  conhece o id (escreve `{id}` ou `crypto.randomUUID()`), então a reescrita garante que o
  `close/{id}` recebido é sempre o id que o backend registrou — sem isso o beacon apagaria
  nada e o arquivo só sairia pela limpeza automática.
- Um **meta CSP restritivo** é injetado no documento: `default-src 'self' data: blob:`,
  `script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://unpkg.com https://cdnjs.cloudflare.com`,
  `style-src 'self' 'unsafe-inline'`, `img-src 'self' data: blob:`, `connect-src 'self' http://127.0.0.1:8000 http://localhost:8000`,
  `font-src 'self' data:`, `worker-src blob:`. O uso de `'unsafe-inline'` é **necessário** porque o modelo gera o script inline da cena;
  esse HTML é criado localmente em `%TEMP%`, aberto via `file:///`, com beacon para `127.0.0.1:8000` — risco contido por esse contexto.
- Arquivo em `%TEMP%\jarvis-3d-{uuid}.html`, aberto com `file:///…`; **removido** pelo beacon
  `/visualize-3d/close/{id}` (botão fechar e `beforeunload`) e por **limpeza automática** de
  60 em 60 s para o que passar de **10 minutos**.
- Tudo registrado em `security.log`.

## 10. Outras proteções

- `/kill` valida o nome do processo por regex (`[A-Za-z0-9_.\- ]{1,60}\.exe`) antes do `taskkill`.
- `/power` limita a carência a 5–3600 s e usa apenas comandos fixos com `/t`.
- Servidor de arquivos estáticos (`app.py`) impede path traversal (`target` precisa estar
  dentro de `public/`).
- O executável só escuta em `127.0.0.1`; nada é exposto na rede local.

## 11. Memória persistente (`/memory`, `backend/memory.py`)

- **Filtro de relevância**: antes de gravar, `is_worth_remembering()` descarta conversa
  fiada (`oi`/`ok`/`valeu`…), perguntas passageiras (começa com `que`/`qual`/`como`/`onde`…)
  e textos curtos (< 30 caracteres) sem verbo de afirmação. O motivo do descarte vai para o
  `security.log` (nunca o texto).
- **Categorias**: `category_of()` classifica por heurística em `pessoal`, `preferencias`,
  `tecnico`, `rotina`, `projetos` ou `outros` — é só um rótulo de metadado, não muda as
  regras acima.
- **Expiração**: `archive_stale(90)` marca `archived: true` em memórias com mais de 90 dias
  que **nunca** foram usadas numa resposta. Arquivar **não apaga**: elas somem da busca e
  ficam visíveis (riscadas) no HUD, e `DELETE /memory/{id}` continua funcionando normalmente.
- **Uso**: as memórias que entram numa resposta recebem `last_used`/`used_count` (thread de
  background) — é isso que as protege do arquivamento.

- **Onde fica**: tudo é local — ChromaDB em `%APPDATA%\JARVIS\chroma_db` (ou
  `JARVIS_MEMORY_DIR`). Nada é enviado para fora; só o **texto da consulta** passa pelo
  embedder local (MiniLM) para a busca semântica.
- **Sanitização**: todo texto é limpo antes de gravar (`memory.py:sanitize_text`): remove
  `<script>`/`<style>`, todas as tags HTML e caracteres de controle, colapsa espaços e corta
  em **1000 caracteres**.
- **Conteúdo sensível nunca é salvo**: `looks_sensitive()` bloqueia chaves de API
  (`gsk_`, `sk-`, `xox*`, `ghp_`, `AIza`, `AKIA`…) e palavras como `api key`, `secret`,
  `senha`, `password`, `credencial` e `token`. O bloqueio é registrado no `security.log`
  (sem o texto).
- **Limite total**: **10.000 memórias** (`MAX_MEMORIES`) — ao passar, as mais antigas são
  podadas automaticamente (`_prune_locked`).
- **No chat**, a mensagem do usuário só vira memória acima de **20 caracteres** e nunca
  comandos (`!`/`/`). A busca injeta no máximo **5 memórias** por resposta.
- **Personalidade aprendida**: as memórias voltam em toda resposta como uma mensagem de
  sistema — `MEMÓRIAS SOBRE O COMANDANTE: …` + `MEMORY_PERSONALITY_GUIDE` (constante fixa em
  `app.py`, não vem do front e nenhum cliente pode sobrescrevê-la). O guia só descreve
  estilo/tom e obriga usar **apenas** as memórias listadas (“NÃO invente memórias”), de modo
  que a memória não vira uma fonte de fatos fabricados.
- **Endpoints** só em `127.0.0.1:8000`; `DELETE /memory/{id}` e `DELETE /memory/all`
  (reset) ficam registrados no `security.log` (quantidade, nunca o texto).

## 12. Modo programador — `POST /generate-code` (`backend/main.py`)

- **Prompt** limitado a **500 caracteres**; `_gcode_sanitize()` remove blocos `<script>`,
  todas as tags HTML, caracteres de controle, URLs (`http://`, `file://`) e `` ` ``/`{`/`}`/`$`.
  Prompt vazio após a limpeza → **HTTP 400**.
- **Nenhuma extensão executável**: a linguagem pedida é validada contra uma **whitelist**
  (`html`, `css`, `js`, `py`, `md`, `txt`, `json`, `sql` — `GENCODE_EXTENSIONS`, com aliases
  como `python`→`py`). Pedido fora dela é **bloqueado e registrado** (HTTP 400), então não há
  como gerar `.exe`, `.bat`, `.cmd`, `.ps1` ou qualquer binário — só código-fonte/texto. O
  nome do arquivo é sempre `jarvis-code-{uuid}.{ext}`, com extensão escolhida pelo backend
  (nunca pelo usuário ou pelo modelo).
- **Saída controlada**: cercas markdown/explicações são descartadas (`_gcode_extract`), exige
  **100 caracteres** mínimos de código e, em HTML, `<!DOCTYPE html>`/`<html>` com corte em
  `</html>`. O arquivo é limitado a **200 KB** (`GENCODE_MAX_CODE`) — acima disso é truncado e
  o corte fica no log.
- **O código é escrito em `%TEMP%` e aberto localmente**: HTML no navegador padrão
  (`file:///…`), os demais no editor padrão (`os.startfile`). Nada é enviado para fora além do
  prompt para a própria API da Groq, e nenhum código gerado é executado pelo JARVIS.
- **Descarte automático**: o HTML gerado recebe um `<script>` de beacon (injetado no
  `</body>`, com o id real do arquivo) que chama `POST /generate-code/close/{id}` em
  `beforeunload`/`pagehide` — o arquivo é apagado na hora. Uma **thread de limpeza** roda a
  cada 60 s e apaga o que passar de **10 minutos** (`_gcode_cleanup_once`).
- Tudo registrado em `security.log` (`generate-code: {prompt} ({size} bytes)`), inclusive
  bloqueios de linguagem, truncamento e limpezas automáticas.

## 13. Notícias brasileiras — `GET /news/brasil` (`backend/main.py`)

- **Fonte e tópico em whitelist** (`BR_NEWS_FEEDS`): o cliente escolhe **nomes** (`g1`,
  `thenews`, `geral`, `tecnologia`, …) — **nenhuma URL vem do cliente**. Fonte desconhecida →
  **HTTP 400** (e registro `BLOQUEADO` no `security.log`); tópico que não existe naquela fonte
  cai para `geral` e também é registrado.
- **Rate limit**: **30 chamadas por minuto** (janela deslizante) → **HTTP 429**, registrado.
- **Sanitização do RSS**: cada item passa pela mesma `_clean_news_text()` do `/news` — tags
  HTML, `&entidades;`, URLs, hashtags, emojis e sufixo de veículo são removidos; o resumo é
  cortado em **200 caracteres** na fronteira de palavra. O texto limpo é o que vai para o
  prompt/voz (defesa em profundidade: o front também escapa tudo com `textContent`, nunca
  `innerHTML`).
- **Links**: `_news_link()` só aceita `http`/`https` com domínio — `javascript:`, `data:` e
  `file:` vindos do feed são descartados antes de chegar ao HUD.
- **Este endpoint NÃO executa nada, não lê arquivos e não escreve em disco**; só faz GET nos
  feeds oficiais (15 s de timeout) e devolve JSON. Se o feed cair, retorna `ok:false` com o
  erro (o `/news` antigo continua no ar como reserva no chat).
- Todo acesso é registrado no `security.log` com a fonte, o tópico e quantos itens vieram
  (nunca o texto das notícias).
- **Saudação ("bom dia")** não adiciona superfície de ataque: é detecção de texto no próprio
  processo, que só chama os endpoints acima (`/weather` e `/news/brasil`) e injeta o resultado
  como mensagem de sistema — o formato e a proibição de inventar dados fazem parte do bloco.

## 14. Como estender

| Variável de ambiente | Efeito |
|---|---|
| `JARVIS_READ_ROOTS` | Pastas extras que o `/read-file` pode ler (separadas por `;`) |
| `JARVIS_ALLOWED_ORIGINS` | Origens CORS permitidas (separadas por `,`) |
| `JARVIS_POWER_DRY_RUN=1` | Simula o desligamento sem executar |
| `JARVIS_CONFIG` | Caminho alternativo do `config.json` |
| `JARVIS_AGENDA` | Caminho alternativo do `agenda.json` |
| `JARVIS_MEMORY_DIR` | Pasta alternativa do banco de memória (`chroma_db`) |
| `JARVIS_BACKEND` | URL do backend de ferramentas (padrão `http://127.0.0.1:8000`) |
| `JARVIS_TOOLS_PORT` | Porta em que o backend sobe — usada também pelo beacon do modo programador |

Para endurecer mais: trocar a blacklist do `/exec` por uma **whitelist** (só comandos
conhecidos), rodar o backend em uma conta de usuário sem privilégios administrativos e
assinar os `.exe` publicados.
