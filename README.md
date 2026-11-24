# JARVIS — Command Center

<p align="center"><img src="logo.jpg" width="180" alt="Logo do JARVIS"></p>

Assistente pessoal com HUD animado, voz pt-BR (Piper), ferramentas locais reais e chat
com streaming via **Groq** ou **NVIDIA NIM** (nuvem) ou **Ollama** (modelos locais).

> Nada aqui usa o backend do OpenJarvis. Só o modelo de voz vem de lá
> (`pt-BR-razo-medium.onnx`, na raiz do projeto).

## O que é o JARVIS

Assistente pessoal **local** para Windows, com HUD animado, globo 3D, voz pt-BR (Piper/Edge
TTS), chat com streaming via **Groq**, **NVIDIA NIM** (nuvem) ou **Ollama** (modelos
locais) e ferramentas de verdade na máquina (comandos, leitura de arquivos, clima,
notícias, agenda, memória persistente). Com o Ollama, o texto não sai da máquina; com a
Groq ou a NVIDIA NIM, o único serviço externo de texto é a API do provedor escolhido — e,
se você escolher o Edge TTS, a voz usa a API da Microsoft. Não é o OpenJarvis — projeto
próprio, sem backend remoto.

## Arquitetura

```
┌─────────────────────────┐
│ Frontend  public/       │  HUD + globo 3D (Three.js r128, servido localmente em
│ HTML/CSS/JS, sem build  │  /vendor/three.min.js — funciona sem internet)
└───────────┬─────────────┘
            │ fetch (mesma origem)
            ▼
┌─────────────────────────┐      ┌──────────────────────────┐
│ Servidor da UI :8755    │ ───▶ │ API do provedor: Groq,   │
│ app.py (Python)         │      │ NVIDIA NIM ou Ollama —   │
│  ou server.js (Node)    │      │ chat + tool calling      │
└───────────┬─────────────┘      └──────────────────────────┘
            │ BACKEND_URL = http://127.0.0.1:8000
            ▼
┌─────────────────────────┐      ┌──────────────────────────┐
│ Backend :8000           │ ───▶ │ Voz: Piper (local) ou    │
│ backend/main.py         │      │ Edge TTS (neural)        │
│ (FastAPI + uvicorn)     │      │ Memória: chroma_db +     │
└─────────────────────────┘      │ MiniLM (embeddings)      │
                                 │ Sistema: exec, arquivos, │
                                 │ clima, notícias, agenda  │
                                 └──────────────────────────┘
```

## Requisitos

- Windows 10/11
- Python **3.10+** (testado em 3.12)
- Node.js **18+** (testado com 20+ — só é necessário para `server.js` e para o app Electron)
- No modo `.exe` (`dist/JARVIS/JARVIS.exe`): nada além dos arquivos gerados
- Hardware mínimo (RAM/disco) não foi medido. O Piper e o Ollama pesam mais que o resto;
  os modelos de voz têm ~63 MB cada e os modelos do Ollama são de vários GB.

## Instalação

```bash
# 1) clonar
git clone https://github.com/heitormirandasjp-collab/O-J.A.R.V.I.S.git
cd O-J.A.R.V.I.S

# 2) backend Python — ferramentas + voz (porta 8000)
python -m venv backend/venv
backend\venv\Scripts\activate
pip install -r backend/requirements.txt

# 3) interface + chat (porta 8755) — um dos dois caminhos:
node server.js                              # Node puro (sem npm install: só módulos nativos)
backend\venv\Scripts\python.exe launcher.py  # ou tudo em Python, que ainda abre a janela

# 4) app desktop (opcional)
cd electron && npm install && npm start
```

Atalhos no Windows: **`start-backend.bat`** (cria o venv sozinho se faltar e sobe o backend
na 8000) e **`start-server.bat`** (sobe o `node server.js` na 8755).

Opcional: a **memória com embeddings** (busca semântica em `/memory/*`) exige um dos dois
fora do `requirements.txt` — `sentence-transformers` (usa PyTorch) ou `chromadb` (reserva
ONNX MiniLM, leve). Sem nenhum dos dois, o backend sobe, mas a memória responde erro.

Depois, configure o provedor de IA (chave da Groq/NVIDIA NIM ou Ollama local — seção **Configuração**)
e abra `http://127.0.0.1:8755`.

## Configuração

Tudo fica em **`config.json`**, na raiz do projeto (no `.exe`, em
`%APPDATA%\JARVIS\config.json`). Chaves que o código lê hoje:

| Chave | O que é | Padrão |
|---|---|---|
| `provider` | provedor do chat: `groq`, `nvidia` (nuvem) ou `ollama` (local) | `groq` |
| `groqKey` | chave da API da Groq — obrigatória quando o provedor é `groq` | — |
| `groqModel` | modelo da Groq (a lista tem fallback interno) | vazio = modelos testados |
| `nvidiaKey` | chave da NVIDIA NIM (`nvapi-…`) — obrigatória quando o provedor é `nvidia` | — |
| `nvidiaModel` | id do modelo no catálogo da NVIDIA (ex.: `nvidia/nemotron-3.5-lightning-30b-a3b`); o nome de exibição também é convertido para o id | vazio = modelos testados |
| `ollamaUrl` | URL base do Ollama (compatível com OpenAI) | `http://127.0.0.1:11434/v1` |
| `ollamaModel` | modelo local (nome exato do `ollama list`) | `llama3` |
| `tts_engine` | motor de voz: `piper` ou `edge` | `piper` |
| `tts_voice` | voz: arquivo `.onnx` (Piper) ou ShortName (Edge) | `pt_BR-cadu-medium.onnx` |
| `googleClientId` | Client ID do cliente OAuth **Desktop app** do Google (Gmail + Agenda) | vazio = Google desligado |
| `googleClientSecret` | Client Secret do mesmo cliente OAuth — **segredo**, nunca vai para o HUD mascarado | vazio |
| `googleTimezone` | fuso usado ao criar eventos na Google Agenda | `America/Sao_Paulo` |
| `googleRedirectPort` | porta local que recebe o retorno da autorização do Google | `8899` |
| `obsidianVault` | pasta do vault do Obsidian (só se grava `.md` dentro dela) | vazio = Obsidian desligado |
| `logseqGraph` | pasta do grafo do Logseq (usa `journals/` e `pages/`) | vazio = Logseq desligado |
| `continuous_listen_minutes` | minutos de escuta contínua após o wake word (`0` = infinito) | `5` |
| `weather_city` | cidade do clima (⚙ → *Cidade do clima*) | vazio = detecta por IP |
| `weather_lat` · `weather_lon` | coordenadas resolvidas **uma vez** ao salvar a cidade (geocoding do open-meteo) | vazio = detecta por IP |
| `weather_source` | `manual` quando a cidade veio do campo nas configurações | vazio = `config` |

**Primeira vez (clone novo)**: copie o template versionado e preencha a chave:

```bash
cp config.json.example config.json   # Windows: copy config.json.example config.json
```

Depois cole a sua chave no campo **`groqKey`** do `config.json` novo. O
`config.json` real está no `.gitignore` e **nunca** vai para o repositório — só este
exemplo.

Como obter a chave: crie a conta em <https://console.groq.com>, gere a chave em
<https://console.groq.com/keys> — ou, para a NVIDIA, em <https://build.nvidia.com/settings>
— e cole na **engrenagem ⚙** das configurações do JARVIS (ou direto no `config.json`).
Detalhes dos modelos e da voz em **"Chave da Groq"**, **"Chave da NVIDIA NIM"** e
**"Voz (Piper e Edge TTS)"** abaixo.

## Uso

Com o backend (8000) e a UI (8755) no ar, abra `http://127.0.0.1:8755` — ou use o `.exe` /
app Electron, que sobem tudo sozinhos. O que dá pra fazer:

- **Chat** com streaming via Groq, NVIDIA NIM ou Ollama e agente com tool calling (engrenagem ⚙ para provedor/chave/modelo);
- **Voz pt-BR**: dizer "Jarvis" acorda o assistente (escuta contínua configurável), com Piper
  (voz local) ou Edge TTS (neural, precisa internet);
- **3D**: globo do núcleo (5.000 partículas; arrasto gira, com inércia e zoom), visualizador
  3D sob demanda ("me mostra um carro") e modo foco em tela cheia;
- **Programar**: o modo programador gera código a partir do chat;
- **Ferramentas reais** via backend: comandos, leitura de arquivos, clima, notícias,
  agenda/lembretes, memória persistente e controle de energia (com confirmação);
- **App desktop** (Electron) com janela própria e sem barra do sistema.

## Segurança

⚠️ **Uso local e pessoal.** O JARVIS executa ações reais na sua máquina:

- **NÃO exponha as portas 8000/8755 na internet.** O CORS está restrito a
  `127.0.0.1:8755`/`localhost:8755`, mas quem alcança a porta manda no app;
- **`/exec`** roda comandos no shell e **`/power`** desliga/reinicia o PC — os dois têm
  blacklist, confirmação e log, mas **não são um sandbox**: trate o modelo como não confiável;

> 🔴 **Estes endpoints são perigosos: NUNCA exponha o backend na internet. Só use
> localmente.**

- **`/exec` e `/power` exigem token (v1.0.16)**: as duas rotas têm autenticação
  obrigatória — só respondem quando a variável de ambiente `JARVIS_EXEC_TOKEN` está
  definida **e** a chamada traz o mesmo valor no header `X-Jarvis-Token`. Sem a env
  (ou com token ausente/errado) a resposta é **403** `{"detail": "<motivo>"}` e o
  bloqueio vai para o `security.log`. Para ativar:
  1. gere um valor: `python -c "import secrets;print(secrets.token_urlsafe(32))"`;
  2. defina no ambiente antes de subir o backend — PowerShell da sessão:
     `$env:JARVIS_EXEC_TOKEN="<valor>"` (ou `setx JARVIS_EXEC_TOKEN "<valor>"` para
     valer em novas janelas);
  3. envie `X-Jarvis-Token: <valor>` em cada chamada a `/exec` e `/power`.
  O template está em [`.env.example`](.env.example); o projeto **não** carrega `.env`
  automaticamente, a variável precisa estar no ambiente;
- **a sessão que faz o proxy também precisa da env**: o `server.js` e o `app.py` (que ligam
  a UI ao backend em `/exec` e `/power`) leem `JARVIS_EXEC_TOKEN` do **seu** ambiente e
  repassam o header automaticamente — **sem a env no ambiente deles, a UI recebe 403** no
  Shell e nos comandos de energia;
- a chave da Groq no `config.json` é **seu** segredo — não commite nem compartilhe o arquivo
  (por isso ele está fora do versionamento);
- **o `config.json` NÃO vai no `.exe` nem no instalador**: o `JARVIS.spec` exclui do build
  `config.json`, `*.env` (`jarvis.env`, `api groq jarvis.env`…), `security.log` e
  `exec_history.json` — quem instalar cria o próprio a partir do
  [`config.json.example`](config.json.example) e coloca a chave dele;
- **rotação da chave da Groq (v1.0.16)** — se a chave antiga foi exposta em conversas, logs
  ou commits, **troque-a antes de publicar o repo** (a troca é manual, nada é automático):
  1. gere uma nova chave em <https://console.groq.com/keys> — botão **Create API Key**; a
     chave (começa com `gsk_`) aparece **uma única vez**, copie na hora;
  2. revogue a antiga: na mesma página, **delete a chave antiga** — ela deixa de valer na
     hora;
  3. coloque a nova em `config.json` → campo **`groqKey`** (dev: na raiz do projeto;
     `.exe`: `%APPDATA%\JARVIS\config.json`) — ou na engrenagem ⚙ das configurações do
     JARVIS — e reinicie o backend.

Blacklist, rate limits, handler global de erros e exemplos de log: em
**[Segurança (detalhes técnicos)](#segurança-detalhes-técnicos)** e no
**[SECURITY.md](SECURITY.md)**.

## Licença

Este projeto está licenciado sob a licença MIT — veja o arquivo [LICENSE](LICENSE) para detalhes.

## Arquivos

```
jarvis/
├── launcher.py            # inicializador do app (vira JARVIS.exe)
├── JARVIS.spec            # configuração do PyInstaller (gera dist/JARVIS/)
├── installer.iss          # script do instalador (Inno Setup)
├── app.py                 # interface + chat + agente (porta 8755)
├── server.js              # alternativa em Node do app.py (porta 8755)
├── public/                # HUD (HTML/CSS/JS, sem build)
├── backend/
│   ├── main.py            # ferramentas + voz (porta 8000)
│   ├── memory.py          # memória persistente (chroma_db)
│   ├── requirements.txt
│   └── venv/
├── electron/              # app desktop (Electron) — janela própria 1280×800
│   ├── main.js            # cria a janela, sobe os dois serviços e encerra tudo
│   ├── preload.js         # ponte segura (só minimizar/maximizar/fechar)
│   └── icon.png           # ícone do JARVIS
├── experiments/           # protótipo de laboratório (ar_test.html e modelos 3D)
├── voices/                # vozes Piper (.onnx + .onnx.json, ~63 MB cada)
├── start-backend.bat      # sobe o backend (porta 8000)
├── start-server.bat       # sobe o servidor da UI em Node (porta 8755)
├── config.json.example    # modelo de configuração (copie para config.json)
├── config.json            # suas configurações e chaves (só neste computador)
├── agenda.json            # lembretes/agenda (criado no primeiro uso)
└── google_token.json      # tokens do Google (0600; criado ao conectar — nunca commitar)
```

No `.exe`, `config.json` e `agenda.json` ficam em `%APPDATA%\JARVIS\`.

## Jeito mais fácil: o executável

`dist/JARVIS/JARVIS.exe` (gerado pelo PyInstaller, ~260 MB na pasta). Dê dois cliques: ele
sobe os dois serviços (8000 e 8755), abre a janela do app e fica rodando. Para encerrar,
feche a janela preta do console ou pressione Ctrl+C nela.

Se o JARVIS já estiver rodando, rodar o `.exe` de novo **não abre outra janela**: um
mutex de instância única faz a nova execução **focar a janela já aberta** e sair. Se a
janela foi fechada mas o console continua no ar, o `.exe` reabre a interface apontando para
os serviços que já estão no ar (não duplica serviços). Mantenha a pasta `JARVIS` inteira
junto do `.exe` — o `_internal` faz parte do aplicativo.

Regenerar o executável (usa `JARVIS.spec`, que já inclui `public/`, `backend/main.py`,
`backend/memory.py`, `system_prompt.txt`, `SECURITY.md` e o ChromaDB com o ONNX MiniLM —
sem PyTorch):

```bash
cd jarvis
backend\venv\Scripts\pyinstaller.exe --noconfirm --clean JARVIS.spec
```

O `JARVIS.exe` procura o modelo de voz, nesta ordem: variável `PIPER_MODEL`, raiz do
projeto, `voices/`, a pasta do executável, `voices/` ao lado do executável e duas pastas
acima. Basta manter o `.onnx` em algum desses lugares.

### Instalador (Inno Setup)

Com `dist/JARVIS/JARVIS.exe` já gerado, o instalador é montado pelo [Inno Setup 6](https://jrsoftware.org/isinfo.php):

```bat
cd jarvis
"C:\Users\<usuario>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" /O"dist-installer" installer.iss
```

Isso gera **`dist-installer\JARVIS-Setup.exe`** (atalhos no Menu Iniciar e na área de
trabalho, desinstalador, e `config.json`/`agenda.json` do usuário preservados em
`%APPDATA%\JARVIS\`). O script `installer.iss` empacota a pasta `dist\JARVIS` inteira —
rode o PyInstaller **antes** de compilar o instalador.

## Rodando em modo desenvolvimento

```bash
# 1) ferramentas + voz
cd backend
venv\Scripts\activate
uvicorn main:app --port 8000

# 2) interface + chat (escolha um dos dois)
cd .. && backend\venv\Scripts\python.exe launcher.py     # sobe tudo e abre a janela
cd .. && node server.js                                  # ou só a UI, em Node
```

Atalhos: `start-backend.bat`, `start-server.bat`.

## Chave da Groq

Engrenagem ⚙ → cole a chave de https://console.groq.com/keys. Ela fica em `config.json`
(no `.exe`, em `%APPDATA%\JARVIS\config.json`).

Modelos testados com a chave atual (a lista tem fallback interno entre eles):
`openai/gpt-oss-120b` → `openai/gpt-oss-20b` → `qwen/qwen3.8-27b`.
Se `llama-3.3-70b-versatile` ainda existir na sua conta, escreva o nome dele no campo
"Modelo" nas configurações.

## Chave da NVIDIA NIM

Engrenagem ⚙ → **Provedor de IA → NVIDIA NIM (Nuvem)** → cole a chave (`nvapi-…`) e, se
quiser, o id do modelo. A chave fica em `config.json` com permissão **0600** (no `.exe`, em
`%APPDATA%\JARVIS\config.json`) e nunca é devolvida ao HUD — só a máscara.

Como obter:

1. entre em <https://build.nvidia.com> e faça login (conta de desenvolvedor da NVIDIA);
2. abra qualquer modelo do catálogo e clique em **Get API Key** — ou vá direto em
   <https://build.nvidia.com/settings>;
3. copie a chave (começa com `nvapi-`) e cole no JARVIS.

O endpoint usado é `https://integrate.api.nvidia.com/v1/chat/completions` — o mesmo protocolo
OpenAI do chat completions, com streaming e function calling. Modelos testados com a chave, nesta ordem, com fallback interno:

`nvidia/nemotron-3.5-lightning-30b-a3b` → `nvidia/nemotron-3-ultra-550b-a55b` → `google/gemma-4-31b-it`.

O JARVIS consulta o catálogo (`/v1/models`) e converte um nome de exibição (ex.: "Nemotron 3.5 Bolt E4B")
para o id real. Modelos descontinuados (como `meta/llama-3.3-70b-instruct`, que volta **410 Gone**)
são pulados automaticamente.

O modelo precisa aceitar **function calling**, porque é assim que o JARVIS executa as
ferramentas (comandos, clima, agenda…). Os três testados aceitam; se um modelo escolhido não
aceitar, a chamada volta 400 e o JARVIS tenta o próximo da lista.

> A NVIDIA dá uma cota gratuita de testes por conta de desenvolvedor, mas **o texto da
> conversa vai para os servidores dela** — como na Groq. Para nada sair da máquina, use o
> Ollama.

Erros comuns: **HTTP 401/403** = chave errada, expirada ou de outra conta (confira em
`build.nvidia.com/settings`); **HTTP 404/410** no modelo = id fora do catálogo ou descontinuado (o JARVIS pula para o próximo;
ajuste o campo **Modelo** ou deixe vazio para usar a lista testada); **HTTP 429** = cota/limite de requisições
atingido — espere um pouco ou troque de provedor.

**Também vale editar o `config.json` direto:**

```json
{
  "provider": "nvidia",
  "nvidiaKey": "nvapi-sua-chave-aqui",
  "nvidiaModel": "",
  "groqKey": "sua-chave-da-groq-continua-aqui"
}
```

## Rodando com Ollama (modelos locais)

O chat aceita três provedores, escolhidos na **engrenagem ⚙ → Provedor de IA**:

| Opção | Onde roda | Chave |
|---|---|---|
| **Groq (Nuvem)** | servidores da Groq | obrigatória (`groqKey`) |
| **NVIDIA NIM (Nuvem)** | servidores da NVIDIA | obrigatória (`nvidiaKey`, `nvapi-…`) |
| **Ollama (Local)** | na sua máquina, offline | nenhuma — a URL local basta |

> ⚠️ Modelos locais grandes precisam de RAM/VRAM à altura. Um modelo 8B (ex.: `llama3`)
> roda com ~8 GB de RAM; modelos de 70B+ exigem dezenas de GB. Confira o catálogo em
> <https://ollama.com/library> e baixe um modelo que caiba na sua máquina.

### Instalar e baixar um modelo

1. Instale o Ollama em <https://ollama.com/download> (Windows, macOS ou Linux);
2. Baixe um modelo no terminal:

   ```bash
   ollama pull llama3          # ~4,7 GB; roda com 8 GB de RAM
   # alternativas: ollama pull llama3.1:8b | qwen2.5:7b | mistral
   ```

3. Confirme que o serviço está no ar (ele sobe sozinho após a instalação):

   ```bash
   ollama list
   ```

O endpoint compatível com OpenAI fica em `http://127.0.0.1:11434/v1`. O JARVIS usa esse
endpoint para chat, streaming e tool calling — para as ferramentas funcionarem bem, prefira
modelos com suporte a tools (`llama3.1`, `qwen2.5`, `mistral`).

### Configurar o JARVIS

1. Abra as configurações (⚙) → **Provedor de IA** → **Ollama (Local)**;
2. **URL base**: `http://127.0.0.1:11434/v1` (padrão);
3. **Modelo local**: o nome exato que aparece no `ollama list` (ex.: `llama3` ou `llama3:8b`);
4. **Testar conexão** confirma o serviço no ar e lista os modelos baixados;
5. **Salvar**.

Também dá para editar direto no `config.json`:

```json
{
  "provider": "ollama",
  "ollamaUrl": "http://127.0.0.1:11434/v1",
  "ollamaModel": "llama3",
  "groqKey": "sua-chave-continua-aqui"
}
```

A chave da Groq continua guardada: voltar para **Groq (Nuvem)** não exige reconfigurar nada.
O TTS não muda — Piper (local) e Edge TTS continuam como estão, e as ferramentas seguem no
backend Python (porta 8000).

### Se o Ollama não estiver rodando

Nada quebra: o chat devolve um erro claro (*"Ollama falhou… Verifique se o Ollama está
rodando"*), as ferramentas locais continuam funcionando e o botão **Testar conexão** mostra o
motivo. Para subir o serviço manualmente: `ollama serve`.

## Personalidade (JARVIS autêntico)

Todas as respostas usam um system prompt fixo de personagem: **J.A.R.V.I.S.**, o mordomo
digital dos filmes — formalidade britânica elegante, sarcasmo sutil, lealdade incondicional,
parceria estratégica (pensa junto, discorda com respeito), calma em crise e humor seco na
medida, com tratamento por "Comandante"/"Senhor" e respostas curtas.

A personalidade vive em **`system_prompt.txt`** (fonte única): `app.py` e `server.js`
**leem o mesmo arquivo** em toda chamada ao modelo e descartam qualquer mensagem `system`
que o front envie. O arquivo vai empacotado no `.exe` (datas do PyInstaller). Junto dele,
cada runtime mantém as **regras operacionais** (anti-alucinação, ação só com ferramenta,
fala das notícias, clima) — personalidade e regras são aplicadas juntas
(`SYSTEM_PROMPT` + `SYSTEM_RULES`).

### Regra anti-alucinação (obrigatória)

O prompt traz uma seção **"REGRA CRÍTICA ANTI-ALUCINAÇÃO"** e uma **"AÇÃO SÓ EXISTE COM
FERRAMENTA"**. Elas obrigam o modelo a:

- chamar a ferramenta correspondente antes de falar de agenda, cotações, sistema, notícias
  ou arquivos;
- usar **apenas** o resultado retornado;
- dizer "Não há nada registrado, Comandante" quando o resultado vier vazio — nunca inventar
  reunião, cotação ou status;
- **nunca prometer uma ação** ("vou desligar", "já agendei", "abrindo o Chrome") sem um
  `[RESULTADO DA FERRAMENTA]` dizendo que ela aconteceu.

No backend, quando o resultado de uma ferramenta é vazio (ex.: agenda sem eventos), o contexto
injetado traz explicitamente `[RESULTADO VAZIO] a agenda está vazia — nenhum evento cadastrado.
NÃO invente nada.`

## Agente com tool calling (M7)

O chat **não depende mais de regex** quando há chave da Groq. O fluxo do `/api/chat` é:

1. o modelo recebe a mensagem **mais a lista de 19 ferramentas** (`exec`, `read_file`,
   `sysinfo`, `list_processes`, `kill`, `power`, `power_cancel`, `news`, `agenda_add`,
   `agenda_list`, `agenda_delete`, `agenda_check`, `stocks`, `currencies`, `weather` e as do
   Google: `gmail_list`, `gmail_read`, `calendar_list`, `calendar_add`, `calendar_delete`);
2. ele decide se precisa de alguma ferramenta (pode pedir várias de uma vez);
3. o backend executa cada uma e devolve o resultado real;
4. repete até o modelo responder — **máximo de 5 rodadas**;
5. só então a resposta final é emitida para a interface.

A UI recebe um evento SSE `tool` a cada execução (`{"name", "ok", "summary"}`), então cada
passo aparece no log de atividade do HUD. Sem chave da Groq, o caminho antigo (regex +
ferramenta) continua valendo como fallback.

### Segurança no agente

- **Desligar/reiniciar/hibernar/suspender**: a ferramenta `power` **não executa na hora** —
  ela só registra o pedido e devolve `AGUARDANDO CONFIRMAÇÃO`. Nada acontece até o Comandante
  responder **"sim"** (ou algo inequívoco) na próxima mensagem. Um **"não"/"cancela"** limpa
  o pedido, e o pedido **expira em 120 s**.
- A intenção de energia é **detectada deterministicamente** (antes do modelo), então o pedido
  fica registrado mesmo se o modelo tentar apenas narrar a ação.
- O modelo **não pode confirmar por conta própria**: o campo `confirmed` vindo dos argumentos
  do modelo é descartado; só o fluxo de confirmação o define. E uma mesma ordem executa **no
  máximo um** desligamento (rodadas seguintes recebem `já foi registrado — não chame de novo`).
- Para testar a cadeia inteira **sem desligar a máquina**, suba a interface com
  `JARVIS_POWER_DRY_RUN=1`: o desligamento confirmado devolve `MODO SIMULAÇÃO ... NÃO foi
  executado` e nada roda. (Nesse modo o modelo pode responder "desligamento agendado" — é
  só teste.)
- Fechar programa, rodar comando e consultar dados executam direto, e o resultado real é
  mostrado na hora.

## Escuta contínua (palavra-chave "Jarvis")

No painel lateral, botão **Escuta contínua** — vem **ligada por padrão**. O microfone fica
aberto e escutando. **O wake word "Jarvis" executa comandos em segundo plano e responde por
voz/toast. O chat só abre se você clicar em "Talk to Jarvis".**

- se você disser **"Jarvis" + o comando na mesma frase** (`"Jarvis, quanto está o dólar?"`):
  toca um bipe, o comando é processado **em segundo plano** (`/api/chat`) e a resposta chega
  por **voz (TTS)** e num **aviso discreto** (toast `Jarvis: ...`, curto e some sozinho).
  **O painel de chat nunca abre** — nem se ele já estiver aberto (o estado dele não muda).
- se você disser **só "Jarvis"** (sem comando): toca um bipe, o JARVIS responde por voz
  **"Sim, Comandante?"** e fica esperando o comando — **sem abrir o chat**. A próxima frase
  também é processada em segundo plano (voz + toast).

**O chat NUNCA abre sozinho.** Ele abre **apenas** por ação explícita do usuário: clique no
botão **"Talk to Jarvis"** (pílula de fala), em **"Conversas"** na navegação, no microfone,
comandos rápidos, ou digitação / atalho ⌘K / busca. No código existe a flag
**`chatManuallyOpened`** (`public/app.js`), que só vira `true` dentro de `userOpenChat()` —
chamada exclusivamente pelos cliques/digitação do usuário. O handler do wake word **nunca** a
altera nem chama `openChat()`. Se o chat já estiver aberto e você falar "Jarvis + comando",
ele **permanece aberto** (o comando roda em background, sem mexer no estado do chat).

### Escuta contínua depois do "Jarvis"

**Após dizer "Jarvis", o JARVIS fica escutando continuamente por 5 minutos
(configurável). Durante esse tempo, você pode falar comandos sem repetir "Jarvis".
Se ficar 5 min sem comando, a escuta pausa.**

- cada comando (dito sem o wake word) é processado **em segundo plano** — voz + toast — e
  **reinicia o relógio** dos 5 minutos;
- dizer **"Jarvis" de novo** durante a escuta apenas **reinicia o timer** (não reinicia nada);
- o reconhecimento **não para** entre comandos: se o motor cair/sair, ele é reerguido na hora
  (150 ms) enquanto a escuta contínua estiver ativa;
- passados os 5 min sem nenhum comando: `continuousListening = false`, toast
  **"Escuta pausada. Diga 'Jarvis' para ativar."** e volta ao modo "esperar wake word";
- o microfone **continua aberto enquanto o JARVIS fala** (TTS). Para ele não responder à
  própria voz, há um filtro anti-eco: se a transcrição for igual (ou parte de) **o que ele
  acabou de falar** nos últimos 20 s, ela é ignorada.

Configure em ⚙ → **Escuta contínua após "Jarvis" (minutos)** (padrão **5**).
O valor é salvo no `config.json` (chave **`continuous_listen_minutes`**) — `0` = **infinito**
(nunca pausa sozinha), teto de 1440 (24 h). Requer o backend de chat no ar (o valor lido do
`/api/status` no boot).

### Detecção da palavra-chave (anti falso positivo)

A detecção é **estrita** para o chat nunca abrir sozinho. Em `public/app.js`:

- **`WAKE_MIN_SCORE = 0.85`** (configurável) — similaridade mínima com `jarvis`
  (Levenshtein normalizado, 0..1). `1.0` = só a palavra exata `jarvis`. Um falso
  positivo como `harry` ou `carol` tem score `0`.
- **`WAKE_MIN_COMMON = 4`** — a palavra precisa ter pelo menos **4 letras em comum**
  com `jarvis` (isso elimina `harry`, `carol`, `notice` etc., antes mesmo do score).
- **`WAKE_COOLDOWN_MS = 3000`** — depois de disparar, novos disparos são ignorados por
  **3 s** (evita duplo disparo da mesma frase).

Como o wake word (com ou sem comando) **nunca** abre o chat, o `openChat()` só é chamado por
**ação explícita do usuário** (`userOpenChat()`). Não existe mais a opção "Abrir o chat ao
falar 'Jarvis'" nas configurações.

Se a sua voz for reconhecida como `jarves`/`járvis` e não disparar, diminua
`WAKE_MIN_SCORE` para `0.80` no topo da seção de escuta em `public/app.js`.

### Reconexão da escuta (erro `network`)

No `onerror` do `SpeechRecognition`, o erro `network` (o motor do navegador caiu/perdeu a
conexão com o serviço) agora é tratado assim:

- faz `recognition.stop()` para limpar o estado, espera **2 s** e chama `recognition.start()`
  de novo — sempre na **mesma instância** (nunca cria uma nova);
- um **contador de falhas seguidas** é mantido; a cada `start()`/resultado válido ele zera;
- após **5 falhas seguidas** a reconexão é **pausada por 30 s** (aviso `Reconexão pausada por
  30s` no feed e no toast) e só depois tenta de novo;
- o indicador da escuta é **verde** enquanto ouve OK e **vermelho** (`has-error` no botão do
  microfone) quando há erro, voltando a verde automaticamente ao reconectar.

Observações honestas:

- a escuta roda pelo motor de voz do navegador (Web Speech API, `pt-BR`) — a janela do
  JARVIS precisa ficar **aberta** (pode ficar atrás de outras janelas); se o motor parar,
  o app reinicia sozinho a escuta;
- na primeira vez o navegador pede permissão de microfone — autorize;
- sem internet, o ditado do navegador não funciona (a voz de resposta continua);
- logo após abrir, o navegador pode exigir um clique na página para liberar o microfone.

## Voz (Piper e Edge TTS)

A voz tem **dois motores**, escolhidos no modal de configurações (⚙ → *Motor de voz*):

> **O motor padrão é o Piper (voz cadu), que combina mais com a personalidade do JARVIS. O Edge
> TTS é uma alternativa mais natural, mas genérica.**

- **Piper (padrão, local)** — voz masculina brasileira **`pt_BR-cadu-medium`** (mais grave),
  100% offline: nada sai da máquina. Devolve **WAV**. O timbre grave é o que faz a voz soar
  como o JARVIS, e não como um assistente genérico.
- **Edge TTS (alternativa)** — vozes **neurais da Microsoft** (biblioteca `edge-tts`), mais
  naturais porém genéricas. Devolve **MP3** e o navegador toca direto. Vozes pt-BR: `Antonio`
  (padrão), `Nicolau`, `Francisca` e `Thalita` — listadas em `GET /voices-edge` (a lista do
  serviço varia por região; as conhecidas entram sempre). **Precisa de internet**: é o único
  ponto do JARVIS que envia a frase falada para fora — ver **[SECURITY.md](SECURITY.md)**.
  Exige **`edge-tts >= 7.3.0`** (`requirements.txt`): até a 7.2.x a biblioteca usava o host
  `speech.platform.bing.com`, desativado pela Microsoft, e o `/tts` voltava **HTTP 403**
  (fix upstream `rany2/edge-tts#490`). O `.exe` só herda a correção se for **regerado**, porque
  a biblioteca é empacotada dentro dele.

**Reserva automática nos dois sentidos** (a ordem foi invertida na v1.0.13): o `/tts` tenta o
motor escolhido e, se ele falhar, sintetiza na hora com o outro — Piper sem a voz baixada (ou
com o modelo corrompido) cai para o **Edge TTS**; Edge sem internet cai para o **Piper local**.
A falha fica no `security.log` e o front ainda tenta de novo pelo endpoint, então o JARVIS
**nunca fica mudo**.

Cada motor guarda a própria voz: trocar de motor aplica a voz padrão dele
(`pt-BR-AntonioNeural` no Edge, `pt_BR-cadu-medium.onnx` no Piper). O tom (semitons) vale só
para o Piper — o slider fica desabilitado no Edge, e a velocidade vale nos dois (`rate > 1`
→ fala mais lenta, tanto no `length_scale` do Piper quanto no `rate` do Edge).

### Piper

- **Velocidade**: slider de 0,80× a 1,80× (padrão **1,35×** — mais lento e claro).
  Internamente é o `length_scale` do Piper (`> 1` = mais devagar).
- **Tom**: slider de −5 a +5 semitons (padrão **−2** = mais grave). Como o Piper não tem
  ajuste de pitch, o WAV é reamostrado no backend (numpy puro, sem ffmpeg) e o
  `length_scale` é compensado para a duração não encolher.
- **Vozes**: a padrão é a **`pt_BR-cadu-medium`** (voz masculina brasileira, mais grave).
  Também existem `pt_BR-faber-medium` e `pt-BR-razo-medium`; todas são listadas em
  `GET /voices` e dá para escolher no modal de configurações ou baixar em
  `POST /voices/download`.
- **No `.exe`**: a voz **padrão vai empacotada** em `_internal/voices/` (`datas` do
  `JARVIS.spec`) — sem isso o Piper não existe na máquina de quem instala. As outras vozes
  (~63 MB cada) ficam de fora e continuam disponíveis em `POST /voices/download`. O backend
  procura os `.onnx` também em `sys._MEIPASS`/`_internal/voices` e só aceita como voz o
  arquivo que tenha o `.onnx.json` ao lado (era assim que ele confundia o dataset de teste
  `onnxruntime/datasets/logreg_iris.onnx` com uma voz).
- **Fala mais limpa**: o texto passa por normalização antes do Piper —
  palavras coladas separadas (`"olá.Como"` → `"olá. Como"`), markdown/emojis/símbolos
  removidos, abreviações expandidas (`vc` → `você`, `tá` → `está`, `obg` → `obrigado`),
  dinheiro por extenso (`R$ 4,99` → `"quatro reais e noventa e nove centavos"`),
  porcentagem falada (`42%` → `"quarenta e dois por cento"`, `-0,52%` → `"menos zero vírgula
  cinquenta e dois por cento"`) e pontuação normalizada para dar pausas naturais.
- **Textos longos**: acima de ~500 caracteres o texto é quebrado em **chunks de ~200
  caracteres** nas fronteiras de frase, cada um é sintetizado separadamente e os WAVs são
  concatenados — o Piper não "perde o fôlego". Um texto de 640 caracteres sai em 4 chunks
  (60 s de áudio).

Para ajustar a voz: Configurações ⚙ → **Motor de voz** (Piper / Edge TTS), **Voz do JARVIS**,
**Velocidade** e **Tom** (Piper). O botão **“Testar voz”** fala uma frase de exemplo com a
escolha atual, sem salvar. O backend aceita tudo em `POST /tts`:
`{ "text", "engine": "piper", "rate": 1.35, "pitch": -2, "voice": "pt_BR-cadu-medium.onnx" }`
(`engine` ausente ou inválido = `piper`). O motor e a voz ficam em `config.json`
(`tts_engine` / `tts_voice`) — o padrão de fábrica é `"piper"` +
`"pt_BR-cadu-medium.onnx"` — lidos e gravados por `GET`/`POST /api/config`.

## Fala das notícias

Quando o Comandante pede notícias, o JARVIS **não lê os títulos crus** — ele **resume** em
2-3 frases naturais de âncora, sem URLs, fontes (G1/UOL) nem datas. Três camadas garantem isso:

1. **System prompt** (`app.py` e `server.js`) tem a seção **"COMO FALAR AS NOTÍCIAS"** com o
   formato esperado ("Comandante, as principais notícias de hoje: …"), a proibição de URLs/
   fontes/datas/emojis e exemplos **BOM** e **RUIM**.
2. **`GET /news`** (`backend/main.py`) devolve só `{ "titulo", "fonte", "resumo" }` — **sem
   link**. Os textos passam por `_clean_news_text()`: HTML, emojis, hashtags e URLs removidos,
   sufixo de fonte (` - G1`, ` | UOL`) cortado e título truncado em **100 caracteres** na
   fronteira da palavra. Os dois backends de chat (`app.py`/`server.js`) usam `titulo` na
   hora de montar o contexto da ferramenta.
3. **`_speech_text()`** (normalização do TTS) também remove URLs e emojis, corta sufixo de
   fonte no fim do texto e converte `...` em uma **pausa natural** — então nem um texto que
   escape chega à voz com link, emoji ou nome de veículo.

## Ferramentas reais (backend, porta 8000)

| Rota | Uso |
|---|---|
| `POST /exec` | `{ "cmd": "start chrome" }` |
| `POST /kill` | `{ "name": "chrome", "force": true }` → `taskkill` |
| `GET /processes?limit=10` | top processos por RAM (`psutil`) |
| `POST /power` | `{ "action": "shutdown"\|"restart"\|"hibernate"\|"sleep", "delay": 30 }` |
| `POST /power/cancel` | `shutdown /a` (aborta desligamento agendado) |
| `GET /news?topic=geral&limit=5` | títulos + link + data + fonte (RSS, sem chave) |
| `GET /news/brasil?source=g1\|thenews&topic=geral&limit=5` | G1 ou The News (fonte/tópico em whitelist, 30 req/min) |
| `POST /agenda/add` | `{ "title", "datetime", "description" }` → `agenda.json` |
| `GET /agenda/list` | eventos futuros |
| `DELETE /agenda/{id}` | remove por **id** ou pelo **título** |
| `POST /agenda/check?window=5` | eventos nos próximos N minutos (para avisar por voz) |
| `POST /read-file` | `{ "path": "C:\\..." }` |
| `GET /sysinfo` | CPU, RAM, disco, uptime, host real |
| `POST /tts` | `{ "text", "engine", "rate", "pitch", "voice" }` → MP3 (Edge) ou WAV (Piper) |
| `GET /stocks?symbols=PETR4,AAPL` | brapi.dev (BR) + Yahoo (US) |
| `GET /currencies` | USD/BRL, EUR/BRL, USD/EUR |
| `GET /weather` | clima + previsão de hoje da cidade configurada (`config.json`) ou detectada por IP (open-meteo primário; wttr.in reserva) |
| `GET /weather/location` · `POST /weather/location` | cidade do clima em uso · grava `{ "city" }` resolvendo lat/lon uma vez (geocoding do open-meteo) |
| `POST /memory/add` | `{ "text", "source" }` → memória persistente (sanitizada) |
| `GET /memory/search?q=...&n=5` | busca semântica nas memórias |
| `GET /memory/list?limit=100` | memórias mais recentes primeiro |
| `DELETE /memory/{id}` · `DELETE /memory/all` | esquecer uma / resetar tudo |
| `POST /memory/archive?days=90` | arquiva (sem apagar) memórias antigas nunca usadas |
| `GET /memory/stats` | total, arquivadas, categorias, datas e embedder |
| `GET /voices` · `POST /voices/download` | vozes locais (Piper) e download |
| `GET /voices-edge` | vozes pt-BR do Edge TTS (com a lista local de reserva) |
| `GET /google/status` | estado da conexão Google (conectado, email, escopos, etapa do OAuth) |
| `POST /google/connect?port=8899` | abre o servidor local do OAuth e devolve a URL de autorização |
| `POST /google/disconnect` | apaga o `google_token.json` (desconecta a conta) |
| `GET /gmail/messages?q=is:unread&max_results=8` | lista emails (busca do Gmail: `is:important`, `from:…`, `newer_than:2d`) |
| `GET /gmail/message/{id}` | corpo de um email em texto puro |
| `GET /calendar/events?days=7&max_results=10&q=` | eventos da **Google Agenda** na janela pedida |
| `POST /calendar/events` | `{ "summary", "start", "end"\|"duration_min", "description", "location" }` |
| `DELETE /calendar/events/{id}` | remove um evento da Google Agenda |
| `GET /obsidian/status` | pasta do vault, se é válida e quantas notas existem |
| `POST /obsidian/notes` | `{ "title", "content", "folder" }` → grava/anexa `.md` no vault |
| `GET /obsidian/notes?q=&max_results=10` | busca por texto nas notas |
| `GET /logseq/status` | pasta do grafo, páginas e o caminho do journal de hoje |
| `POST /logseq/journal` | `{ "content" }` → bloco no journal do dia |
| `POST /logseq/pages` | `{ "title", "content", "folder" }` → página em `pages/` |
| `GET /logseq/search?q=&max_results=10` | busca por texto no grafo |
| `GET /health` | status do backend, do Piper, do Edge TTS e nº de eventos da agenda |

### Energia (desligar / reiniciar / hibernar / suspender)

`POST /power` **sempre** usa uma carência de **30 s** (padrão) para `shutdown` e `restart` —
tempo para cancelar com `POST /power/cancel` ou dizendo *"cancela o desligamento"*.

- `shutdown` → `shutdown /s /t 30`
- `restart` → `shutdown /r /t 30`
- `hibernate` → `shutdown /h`
- `sleep` → `rundll32.exe powrprof.dll,SetSuspendState 0,1,0`

Para **testar sem desligar nada**, mande `"dry_run": true`: a rota devolve o comando que
seria executado e não faz nada.

### Fechar programas e processos

`POST /kill` encerra pelo nome (`chrome` → `chrome.exe`); `force: true` usa `/F`. Nomes de
apps conhecidos são traduzidos para o processo real (`"bloco de notas"` → `notepad.exe`).
`GET /processes` devolve os 10 que mais consomem RAM.

### Notícias

`GET /news?topic=...` lê RSS (sem chave): **geral, brasil, tecnologia, esportes, economia,
mundo, politica, ciencia** vêm do G1; qualquer outro tópico é buscado no Google News.
Devolve título, link, data e fonte.

`GET /news/brasil?source=g1|thenews&topic=...&limit=5` é a versão com **duas fontes**:

| Fonte | Tópicos | Feed |
|---|---|---|
| **g1** | geral, tecnologia, economia, esportes, mundo, politica, ciencia | `g1.globo.com/rss/g1/...` |
| **thenews** | geral, mercado, tecnologia, mundo | `rss.beehiiv.com/feeds/j9teVW9Qmi.xml` |

O **The News** publica tudo num feed único: o tópico virou um **filtro por palavra-chave**
sobre título e resumo (o resto entra como complemento). Os títulos do The News são nomes de
edição em caixa alta ("NIGHT", "10/10/2026"), então quando o título não tem minúscula o
**resumo** é que vai para o modelo — é ele que informa. Se o feed do Beehiiv mudar de
endereço, o backend tenta `thenewscc.beehiiv.com/feed` e `thenews.com.br/feed` e, por fim,
**descobre o link `rss.beehiiv.com/feeds/*.xml` dentro do portal**; se nada responder,
devolve `ok:false` com o erro (o G1 continua funcionando normalmente).

Cada item sai com `titulo`, `link`, `data` (pubDate), `resumo` (**200 caracteres**, sem HTML,
emojis, hashtags ou URL) e `fonte` — o link passa por uma validação que só aceita `http(s)`.
A resposta é `{ "ok": true, "source", "topic", "count", "feed", "items" }`.

**No chat**, *"notícias de hoje"*, *"o que está acontecendo"*, *"g1"* ou *"the news"*
(e também o tópico detectado — tecnologia, economia/mercado, esportes, mundo, política ou
ciência) fazem o `app.py` chamar a ferramenta **`news`** antes do modelo e injetar
`DADOS REAIS DE NOTÍCIAS: [...]`, com a instrução de resumir as 3 principais em 2-3 frases de
âncora — sem URL, sem nome de veículo e sem data. Se a fonte cair, ele usa o `/news` antigo
como reserva; sem chave da Groq, responde com os títulos crus, sem inventar nada.

**No HUD**, o botão **"📰 Notícias"** abre um seletor de **fonte** (G1 / the news) e
**tópico** (a lista muda conforme a fonte), lista os 5 títulos com data e link e tem
**🔈 Ouvir** (fala as 3 primeiras) e **Atualizar**.

**Segurança**: `source` e `topic` estão em **whitelist** (nada de URL vinda do cliente —
fonte desconhecida → **HTTP 400**), o RSS passa pela mesma sanitização do `/news`, há
**rate limit de 30 chamadas/minuto** (**HTTP 429**) e tudo é registrado no `security.log`
(`news-brasil`).

### Saudação (bom dia)

Dizer **"bom dia"**, **"bom dia, Jarvis"** ou **"bom dia járvis"** dispara um briefing de
âncora — detectado por `detect_greeting_morning()` **antes** do modelo, sem depender de ele
lembrar de chamar ferramenta. Mensagens com mais de **60 caracteres** e comandos (`!`/`/`)
são ignorados, então *"bom dia, preciso de ajuda com o relatório…"* não vira briefing.

O backend então chama o **clima** de São João do Paraíso e as **3 principais notícias do G1**
(geral), injeta tudo no prompt como
`DADOS REAIS DA MANHÃ: clima=[...], notícias=[...]` **junto do formato exato da resposta**
(com a máxima/mínima e o lembrete do guarda-chuva quando há chuva) e proíbe inventar dados.
O texto final vai para a voz como qualquer resposta.

| Você diz | O JARVIS faz |
|---|---|
| **bom dia** | cumprimenta + clima + 3 notícias |
| **boa tarde** | cumprimenta + clima + 3 notícias |
| **boa noite** | cumprimenta + clima (sem notícias) |
| **boa madrugada** | só cumprimenta e comenta o horário, com humor seco |

O formato também está no **[system_prompt.txt](system_prompt.txt)** (seção "QUANDO O
COMANDANTE DISSER BOM DIA"), que é a fonte única do prompt de personalidade.

**Sem chave da Groq** o briefing não morre: `app.py` monta a resposta sozinho —
*"Bom dia, Comandante. Agora em São João do Paraíso faz 27 graus, ensolarado. A máxima hoje é
36 e a mínima 14. As principais notícias de hoje: …"* — e não chama o LLM nenhuma vez.

### Clima

`GET /weather` devolve o clima real da cidade **configurada**, sem chave. A ordem das fontes
foi **invertida na v1.0.12**:

| Ordem | Fonte | Frescor da medição |
|---|---|---|
| **1º (primária)** | **open-meteo** (códigos WMO traduzidos) | medição de **~10-15 min** |
| 2º (reserva) | wttr.in (`format=j1&lang=pt`) | **1-3 h** atrasado (World Weather Online) |

O wttr.in era primário e chegava a **4 °C e 8% de umidade de diferença** por causa desse
atraso — agora ele só entra se o open-meteo falhar. O JSON tem `temp`, `sensacao`, `descricao`,
`umidade`, `vento` ("ESE 12km/h"), `max`, `min`, **`medido_em`** (open-meteo:
`"2026-10-11T09:45"`; wttr.in: `"12:14 PM"`), `city` (e `cidade`, por compatibilidade),
`location_source` e `fonte`.

#### Cidade do clima (v1.0.19)

Até a v1.0.18 a cidade era **fixa** em São João do Paraíso - MG (`-15.377, -42.006`) para
todo mundo. Agora o `/weather` resolve a cidade nesta ordem:

| Ordem | De onde vem | `location_source` |
|---|---|---|
| **1º** | `weather_city` + `weather_lat` + `weather_lon` salvas pelo campo **"Cidade do clima"** (⚙) | `manual` |
| 2º | as mesmas chaves escritas à mão no `config.json` | `config` |
| 3º | **geolocalização por IP** (`ipwho.is`, sem chave) — com **prazo de 4 s**; VPN/CGNAT/sem internet → segue | `ip` |
| 4º | nada disso: **não inventa** — devolve `needs_city: true` e o JARVIS pergunta *"Qual é a sua cidade?"* | `none` |

- O **geocoding do open-meteo** (`geocoding-api.open-meteo.com`, sem chave) é chamado **uma
  única vez**, quando a cidade é salva (`POST /weather/location`); o nome resolvido (com
  acento) e o lat/lon vão para o `config.json` (**0600**, a mesma regra do app.py) e o
  `/weather` só lê o arquivo — nada de geocodificar a cada clique.
- A ideia da geolocalização por IP roda numa thread com **prazo de 4 s** (sucesso fica 30 min
  em cache, falha não fica): o clima nunca fica pendurado esperando a rede.
- **Corrigido na v1.0.20** — `geopy` e `whereismyip` não existiam no `.exe` (o PyInstaller
  não analisa o `backend/main.py`, que entra como dado), então a cidade digitada respondia
  `"não consegui consultar a cidade agora: No module named 'geopy'"` e o clima por IP caía em
  `needs_city`. As duas coisas agora são **HTTP direto** no `requests`, sem pacote extra. Ver
  **"Mudanças recentes (v1.0.20)"**.
- **Privacidade**: o `security.log` registra só `cidade=..., origem=...` — **nunca** lat/lon.
- Quem já usava o app **não quebra**: o `config.json` existente foi semeado com as coordenadas
  antigas e continua em São João do Paraíso (`location_source: config`) até a cidade ser
  trocada nas configurações. O `config.json.example` (instalação nova) sai com os campos
  **vazios**, então o primeiro clima já vem por IP.
- A frase por voz também fala a cidade: *"Comandante, em São Paulo, faz 22 graus, …"*.

O horário da medição vai para a **voz** — *"…A máxima hoje é 33 e a mínima 17. (Dados de
09:45.)"*, e `(Dados de 12:14, via wttr.in.)` quando veio da reserva — e para o **rodapé do
botão 🌤️ Clima** no HUD (*"09:45 · open-meteo"*), para deixar claro de quando é o dado.

No chat, mensagens como **"como tá o tempo?"**, "clima", "previsão", "temperatura", "chuva"
ou "vai chover" fazem o `app.py` chamar a ferramenta **`weather`** ANTES do modelo e injetar
`DADOS REAIS DO CLIMA: {...}` no prompt — o JARVIS responde com os números reais, por voz
(no modo sem chave da Groq a resposta já vem pronta: *"Comandante, agora em São João do
Paraíso faz 22 graus..."*). Se houver chuva na previsão, ele acrescenta o aviso do
guarda-chuva. O botão **"🌤️ Clima"** na barra lateral mostra a mesma previsão no HUD.

### Memória persistente

O JARVIS aprende automaticamente com as conversas. Os dados ficam **só no computador**:

- **Banco**: ChromaDB persistente em `%APPDATA%\JARVIS\chroma_db` (ajustável por
  `JARVIS_MEMORY_DIR`).
- **Embeddings**: `all-MiniLM-L6-v2` via **sentence-transformers** em dev; no `.exe` vale a
  reserva **ONNX MiniLM do próprio ChromaDB** — o **mesmo modelo**, sem PyTorch, para o
  instalador não crescer GBs. O modelo é baixado uma única vez, na primeira memória.
- **No chat** (`/api/chat`): antes do LLM o JARVIS busca até 5 memórias relevantes
  (`GET /memory/search`) e injeta `MEMÓRIAS SOBRE O COMANDANTE: …` no prompt; a mensagem do
  usuário é salva em segundo plano quando tem **mais de 20 caracteres** (comandos `!`/`/`
  não são salvos). Ex.: *"Jarvis, quero um café"* → *"Sem leite, certo?"*.
- **Só o que vale a pena é lembrado** — antes de gravar, `memory.py` passa a mensagem por um
  filtro de relevância: conversa fiada (`oi`, `tudo bem`, `ok`, `valeu`…), perguntas
  passageiras (`que horas são?`, `como tá o tempo?`), textos de menos de **30 caracteres sem
  verbo de afirmação** (`sou`, `tenho`, `gosto`, `odeio`, `faço`, `moro`, `estou`…) e
  informações sensíveis ficam de fora. O que passa vira memória.
- **Categorias** — cada memória recebe uma categoria por heurística de palavras:
  `pessoal` (nome, idade, família, moradia), `preferencias` (gosto/odeio/prefiro),
  `tecnico` (linguagens e ferramentas), `rotina` (acorda/treina/dorme) e `projetos`
  (JARVIS, app, startup) — ou `outros`. O **HUD mostra a categoria** em cada memória.
- **Busca priorizada** — a busca é semântica e continua mandando no resultado, mas
  `pessoal` e `preferencias` ganham preferência sobre `tecnico`/`outros` quando a relevância
  é parecida. As memórias que entram numa resposta são marcadas como **usadas** (`last_used`).
- **Expiração** — memórias com mais de **90 dias** que **nunca** foram usadas em resposta são
  **arquivadas** (campo `archived`): somem da busca e ficam riscadas no HUD, mas **não são
  apagadas** — o Comandante pode desfazer. O arquivamento roda no start do backend e em
  `POST /memory/archive?days=90`. `GET /memory/stats` mostra `total`, `active`, `archived` e
  a contagem por categoria.
- **Personalidade aprendida**: além dos fatos, cada memória alimenta um bloco
  `DIRETRIZES DE PERSONALIDADE DINÂMICA` (`MEMORY_PERSONALITY_GUIDE` em `app.py`) enviado em
  toda resposta: o JARVIS ajusta tom, vocabulário e interesses ao Comandante (academia,
  xadrez, jiu-jitsu, gírias, preferências como *sem leite*), adapta a formalidade ao jeito
  dele falar e mantém o `Senhor`/`Comandante` e a elegância britânica — como um parceiro que
  o conhece há anos. A diretriz proíbe inventar memórias: usa só o que está na lista.
- **HUD**: botão **"🧠 Memórias"** → total, 20 mais recentes com data, **Esquecer** em cada
  uma e **Resetar tudo**.
- **Limites e segurança** (ver **[SECURITY.md](SECURITY.md)**): texto sanitizado (sem
  HTML/scripts), **1000 caracteres** por memória, **10.000** no total (as mais antigas são
  podadas) e **chaves de API/senhas/credenciais nunca são salvas**. Os endpoints respondem
  apenas em `127.0.0.1:8000`.

### Agenda / lembretes

Salvos em `agenda.json` (dev) ou `%APPDATA%\JARVIS\agenda.json` (`.exe`). Datas aceitas:
`AAAA-MM-DD HH:MM`, `DD/MM/AAAA HH:MM` e `DD/MM HH:MM`. `POST /agenda/check` devolve os
eventos que começam nos próximos minutos — é o gancho para o JARVIS avisar por voz.

## Exemplos no chat

- `abra o chrome`, `!ipconfig`, `preço da PETR4 e da AAPL`, `quanto está o dólar?`,
  `como está a CPU e a memória?`, `/stocks vale3,msft`
- `desliga o PC`, `reinicia o computador`, `hibernar`, `suspender o pc`, `cancela o desligamento`
- `fecha o chrome`, `quais processos estão consumindo memória?`
- `quais as últimas notícias?`, `o que está acontecendo no mundo?`, `como tá o tempo?`,
  `vai chover hoje?`, `qual a previsão do tempo?`
- `me lembra de pagar o boleto amanhã às 15h`, `o que tenho na agenda?`,
  `cancela o evento dentista`
- `ocultar painel`, `modo foco`, `só a bola` (e `mostrar painel` para voltar)

## Interface: globo 3D e modo foco

**Globo 3D (M4)** — a esfera central é uma cena **Three.js** de verdade (CDN, sem build):
núcleo brilhante, malha wireframe girando, campo de **5.000 partículas** e **três anéis
orbitais concêntricos** (interno ciano `#3fd0ff` girando rápido, médio azul `#4d8dff` e
externo âmbar `#ffb648` mais lento), nas cores ciano/azul/âmbar. Dá para **arrastar com o
mouse** (com inércia — solta e continua girando), **rolar para dar zoom**, e ele volta ao
centro após 3 s parado. O nome `J.A.R.V.I.S.` fica no centro (HTML sobreposto ao canvas) e
**brilha bem mais quando o TTS está falando**.

**Sem deformação elástica (v1.0.14)** — o arrasto **gira** o globo (com inércia) e **não
estica/achata** mais nada: a camada de "slime"/mola que havia sido adicionada foi removida
por inteiro (ver **"Mudanças recentes (v1.0.14)"**). O `vertexShader` das partículas cuida
**só do pulso** (respiração e voz) — nenhuma deformação de vértice, em shader nenhum. As
**5.000 partículas**, suas posições de repouso (`BufferGeometry` + `aPhase`), a rotação, a
inércia, o zoom, os três anéis e a explosão do wake word ficaram **intactos**.

**Desempenho (v1.0.20)** — o globo não engasga mais quando ele fala: o `filter: drop-shadow` do
canvas (e a `transition: filter`) saiu, o pixel ratio caiu para no máximo **1.5** com degrau
adaptativo, todo amortecimento virou `k60(dt)` e o wobble da fala tem relógio próprio. Detalhes
e as medições em **"Mudanças recentes (v1.0.20)"**.

**Cinema (v1.0.10)** — dois efeitos novos, ambos ligados ao contexto:

- **Explosão do wake word**: ao ouvir *"Jarvis"* o globo dispara um **flash radial de 100
  partículas** que saem do centro e desaparecem em ~800 ms (`window.__jarvisGlobeBurst()`,
  chamado pelo reconhecedor junto com o beep).
- **Cor do núcleo por contexto** (`setCoreMode()`): **ciano** em repouso, **âmbar** enquanto
  o LLM responde (chat ou comando por voz) e **vermelho** quando algo falha ou o backend
  está fora do ar — o vermelho volta sozinho ao ciano em 2,5 s.

**Tamanho do globo** — o `resize()` usa o **tamanho real do container**
(`clientWidth × clientHeight`) com **`camera.aspect = largura / altura`**, então o canvas
preenche a célula. No **modo foco** o container vira `100vw × 100vh` (`z-index: 100`) e o
canvas ocupa a **tela inteira** — em telas widescreen a esfera fica **levemente oval**, o que
é intencional. O canvas é reajustado ao entrar/sair do modo foco (via `requestAnimationFrame`,
depois do CSS aplicar) e também por um `ResizeObserver` no container.

**Voz → bola (v1.0.7)** — o campo de partículas reage ao áudio em tempo real: com o
**microfone** ligado (escuta contínua/wake word ou clique no mic) ele **pulsa** (escala
`1 + volume × 0.3`), **gira mais rápido**, **brilha** mais (núcleo, malha e partículas) e
**oscila** partícula a partícula. Quando o **TTS do JARVIS** fala, o mesmo efeito é
sincronizado com o áudio da voz (o `Audio` do Piper passa pelo mesmo analisador) e termina
quando o áudio acaba. Usa um único `AudioContext` com dois `AnalyserNode` (mic e TTS);
`window.isSpeaking`/`window.isListening` escolhem a fonte e, sem analisador disponível, o
loop usa uma oscilação senoidal de reserva. O AudioContext é liberado no primeiro
clique/tecla na página (`resume()`).

**Modo foco (M5)** — por voz ("Jarvis, ocultar painel", "esconder painel", "modo foco",
"só a bola") a interface esconde tudo (topo, barra lateral, painéis e campo de fala), deixa
só o globo ocupando a tela inteira, escurece o fundo e aumenta o brilho. Sai com **ESC**,
com o botão discreto **"▢ Mostrar painéis"** ou por voz ("mostrar painel"). A transição é
com CSS (400 ms) via `body.focus-mode-active`. Essas intenções são tratadas **localmente** —
não chamam a API — e são respondidas por voz.

## Visualizador 3D sob demanda

Diga **"Jarvis, me mostra um carro"** (ou *visualiza*, *renderiza*, *desenha* + o objeto,
com ou sem "em 3D") e o JARVIS gera um **HTML autocontido com Three.js** que renderiza o
objeto em **milhares de partículas**, salva em `%TEMP%\jarvis-3d-{uuid}.html` e **abre no
navegador padrão**. Ele responde por voz — *"Abrindo o carro no navegador, Comandante."* —
sem abrir o chat.

- **Backend**: `POST /visualize-3d` (`backend/main.py`) pede o HTML à Groq (mesma chave do
  `config.json`, `max_tokens: 16384` — sem isso o gpt-oss corta a resposta no meio). O modelo é
  instruído a usar **Three.js 0.160.0 (unpkg)**, gerar **300.000 partículas** com 
  THREE.Points + BufferGeometry e PointsMaterial com `vertexColors`, `sizeAttenuation` e
  `AdditiveBlending`, escalar o objeto para ocupar boa parte da tela, adicionar logs
  `JARVIS 3D: cena iniciando` e `JARVIS 3D: primeira renderização OK`, além de **fallback
  visual** (mensagem em caso de falha ao carregar Three.js). O backend valida que o HTML está
  **completo** (`<!DOCTYPE html`/`<html` **e** `</html>` + `renderer.render`/`requestAnimationFrame`
  e menciona ~300k partículas ou estrutura BufferGeometry correspondente, senão tenta de novo,
  até 2 tentativas), injeta um **CSP restritivo** e limita o arquivo a 500 KB.
- **Fechar**: o HTML manda um `navigator.sendBeacon` para
  `POST /visualize-3d/close/{id}` no botão fechar e no `beforeunload` — o arquivo é apagado
  na hora. O backend **reescreve a URL do beacon com o id real** do arquivo antes de gravar
  (o modelo não conhece o id: ele escreve `{id}` ou `crypto.randomUUID()`, e sem a reescrita
  o beacon apagaria nada). Além disso, uma **thread de limpeza** roda a cada 60 s e apaga o
  que passar de 10 minutos.
- **Detecção da intenção** é determinística (não depende do modelo) em `app.py` e `server.js`,
  e ignora pedidos de outras coisas ("me mostra **as notícias**", "mostra **a agenda**",
  "status do **sistema**" continuam indo pelo caminho normal).
- **No HUD**: botão **"▣ Visualizar em 3D"** no painel de voz abre um campo para digitar o
  objeto e chama o mesmo endpoint (voz + toast, sem abrir o chat).

Proteções (prompt sanitizado, CSP, limite de tamanho, logs) estão em
[SECURITY.md](SECURITY.md#9-visualizador-3d--post-visualize-3d-backendmainpy).

## Modo AR (webcam + modelo 3D na mão)

O botão **"📷 Ativar AR"** — no painel de voz, logo abaixo de *Visualizar em 3D* — abre a página
**`public/ar.html`** em nova aba. Se o navegador bloquear o pop-up, ela abre na mesma aba e o
**"← Voltar"** da própria página traz o HUD de volta. Com a câmera liberada, um **modelo 3D fica
grudado na palma da mão**, em tempo real, sem tirar o HUD da tela.

- **Como funciona**: `getUserMedia` (640×480; prefere a câmera "Source 2"/DroidCam se existirem)
  → **MediaPipe Hands** (CDN, `maxNumHands: 1`, `minTrackingConfidence: 0.7`,
  `minDetectionConfidence: 0.5`) → **Three.js r128** com **câmera ortográfica** (1 unidade de
  mundo = 1 px de tela), o que coloca o modelo no lugar exato da palma e na escala da mão sem
  distorção de perspectiva.
- **Modelos**: 11 GLB **CC0 do Kenney** — 4 carros (sedan, truck, hatchback-sports, van),
  personagem, espada, escudo, nave, astronauta, árvore e hamburger — em `public/models/`,
  **1,13 MB no total**, cada pack com as suas texturas em subpasta própria e a licença
  (`LICENSE-*.txt`) ao lado (os `colormap.png` de packs diferentes são arquivos diferentes e
  colidiriam se ficassem no mesmo diretório).
- **Teclas**: `1`-`9`, `0` e `-` trocam direto; **`P`** avança e **`Shift+P`** volta (ciclo pelos
  11 modelos); **`R`** zera tudo e volta ao sedan; **`ESC`** limpa a cena sem parar o
  rastreamento. No rodapé da página as teclas e os gestos ficam sempre à vista.
- **Gestos**: **punho esconde** pelo critério de **dedo dobrado** (a ponta fica mais perto do
  pulso do que a articulação PIP — não depende do tamanho da mão nem da distância à câmera),
  **mão aberta mostra** e **verso da mão esconde** (o MediaPipe é treinado com a palma visível e
  "estima" os pontos quando vê o verso; o teste é um produto vetorial 2D combinado com o label
  `Left`/`Right` do MediaPipe, para funcionar com as duas mãos). Mão de **perfil** não esconde
  (ambígua de propósito, para não piscar). O gesto de **pinça foi removido**: fechar a mão
  aproxima os dedos e ele trocava o modelo sem querer.
- **Estabilidade**: os 21 pontos passam por **suavização EMA** (o modelo e o esqueleto saem do
  mesmo estado suavizado), a posição é **clampada** dentro do canvas, perdas curtas de detecção
  têm **grace period** (segura a última pose antes de esconder) e cada frame é validado por
  **confiança** e por **geometria relativa ao tamanho da mão** (o limite absoluto antigo
  descartava mão válida só por estar longe).
- **Abrir já num modelo**: `ar.html?modelo=carro` (nome parcial) ou `ar.html?modelo=3` (1 a 11).
- **Requisitos**: câmera funcionando, navegador moderno e **internet** — o MediaPipe Hands e o
  `GLTFLoader` vêm de CDN (os modelos são locais). O Three.js do globo também tem cópia local em
  `public/vendor/`, mas esta página usa a versão de CDN por causa do loader.
- **Voz**: diga *"Jarvis, me mostra um carro na mão"* (ou *espada*, *hambúrguer*, *nave*,
  *árvore*, *robô*…, ou só *"ativa o modo AR"*) e o JARVIS **abre a AR já no modelo certo** e
  responde por voz *"Abrindo o sedan no Modo AR, Comandante."* — sem abrir o chat. Quem manda em
  quê: *"na mão"* é o gatilho (o pedido **sem** ele continua indo para o visualizador 3D, que
  desenha na **tela**); o objeto é casado com os 11 modelos por **mapa de sinônimos**
  (*carro* → sedan, *caminhão* → truck, *carro esportivo* → hatchback-sports, *adaga*/*arma* →
  espada…) e, se o nome não estiver no mapa, por **match parcial em `GET /ar-models`**.
  Mapa e detecção vivem nos dois backends (`app.py` e `server.js`) com a mesma tabela — há teste
  de paridade entre eles.
- **Backend**: `POST /ar-open` (`backend/main.py`, porta 8000) abre
  `http://127.0.0.1:8755/ar.html?modelo=<nome>` no navegador e devolve a frase falada; o nome passa
  por **sanitização** (`[a-z0-9-]`, até 24 caracteres) e um valor desconhecido apenas faz a página
  cair no modelo padrão. `GET /ar-models` devolve a lista do que existe em `public/models`
  (`name`, `path`, `url`, `size` + `page: /ar.html`) — só leitura, verificada com `TestClient`.

O protótipo de laboratório que originou tudo continua em `experiments/ar_test.html` (é onde os
limiares de gesto foram medidos).

## Modo programador (gera código)

Diga **"Jarvis, me cria um site de portfólio"** (ou *crie*, *programa*, *faz*, *gera*,
*escreve*, *desenvolve*, *monta* + site, página, script, app, HTML, CSS, JS, Python, código,
arquivo…) e o JARVIS gera o código, salva em `%TEMP%\jarvis-code-{uuid}.{ext}` e **abre no
navegador** (HTML) ou no **editor padrão** (`.py`, `.js`, `.md`, `.txt`, `.css`, `.json`,
`.sql`). A resposta vem por voz — *"Pronto, Comandante. Gerei o código e abri no seu
editor."* — sem abrir o chat e **sem chamar o modelo para responder** (economiza tokens).

- **Backend**: `POST /generate-code` (`backend/main.py`) pede o código à Groq (mesma chave do
  `config.json`, `max_tokens: 16384`) com o prompt de requisitos: código completo e funcional,
  HTML autocontido com CSS/JS inline, comentários em português, sem bibliotecas externas e
  site responsivo. A linguagem é **detectada pelo pedido** (site/página → `html`,
  script/python/automação → `py`, javascript/node/react → `js`, markdown/documentação → `md`,
  css → `css`…), ou fixada no campo opcional `language`.
- **Validação**: cercas markdown e explicações são removidas (`_gcode_extract`) e o resultado
  precisa ter pelo menos **100 caracteres**; HTML tem de começar em `<!DOCTYPE html>`/`<html>`
  e é cortado em `</html>`. Se nada válido vier, tenta outro modelo (até 2 tentativas).
- **Fechar**: o HTML gerado recebe um beacon (`navigator.sendBeacon` em `beforeunload` e
  `pagehide`) para `POST /generate-code/close/{id}` — o arquivo é apagado quando a aba fecha;
  uma **thread de limpeza** roda a cada 60 s e apaga o que passar de **10 minutos**.
- **No HUD**: botão **"💻 Programar"** abre um campo curto (500 caracteres) que chama o mesmo
  endpoint, com toast e voz, sem abrir o chat.

Proteções (prompt sanitizado em 500 caracteres, código limitado a 200 KB, apenas extensões de
código-fonte — nada de `.exe`/`.bat`/`.cmd`/`.ps1` — e registro em `security.log`) estão em
[SECURITY.md](SECURITY.md).

## App desktop (Electron, M6)

Além do `JARVIS.exe` (PyInstaller), o mesmo JARVIS vira um **app desktop**: janela própria
1280×800, sem barra do sistema (`frame: false`), com botões de minimizar/maximizar/fechar
feitos no HTML (`public/index.html` + `preload.js`).

```bash
cd electron
npm install                # electron + electron-builder
npm start                  # desenvolvimento (usa dist/JARVIS ou o venv)
npm run build              # gera o instalador em ../dist-electron/
```

O `main.js` sobe os serviços reaproveitando o `dist/JARVIS/JARVIS.exe` em modo sem janela
(`JARVIS_NO_WINDOW=1`), espera a interface responder na 8755 e só então abre a janela. O
app é de **instância única** (`requestSingleInstanceLock`): um segundo atalho/exe aberto
**não cria outra janela** — a primeira é restaurada e focada, e a segunda execução encerra
(`electron/main.js`). Ao fechar a janela, todo o processo do backend é encerrado
(`taskkill /T /F` na árvore). Links externos abrem no navegador padrão, nunca dentro do
app.

## Só dados reais no HUD (enxuto desde a v1.0.14)

Tudo o que aparece na tela vem de medição de verdade — nenhum número é de exemplo. Desde a
**v1.0.14** o HUD mostra **só a barra lateral + o globo** (mais o topo e o rodapé):

- **Barra lateral**: logo, nav, **status de voz** (mic, nível, escuta contínua), os botões
  **Visualizar em 3D / Clima / Memórias / Programar / Notícias** e o rodapé com **Host,
  Ligado há e Rede** (`psutil`, a cada 4 s);
- **Topo**: chip de **Sistema** (`/health`), relógio real e **modelo/provedor** da Groq;
- **Rodapé**: os mesmos Host/Uptime/Rede + a pílula **"Fale com o JARVIS"**;
- **Globo**: núcleo, 5.000 partículas, três anéis e a **cor por contexto** (ciano/âmbar/vermelho).

Os painéis **Estado do núcleo**, **Eventos reais**, **Módulos ativos**, **Atividade**,
**Sessão & histórico** (com o gráfico de CPU/RAM) e **Provedor de IA** foram **removidos do
HTML/CSS** na v1.0.14. O backend continua entregando os mesmos dados (`/health`, `/tools`,
`/exec_history`), mas eles não têm mais célula onde aparecer: as funções do front que os
desenhavam seguem no `app.js` com **guarda de elemento ausente** (`if (!el) return;`) e os
itens de navegação correspondentes ficam **desabilitados** (opacidade 0.4, sem ação no clique).

## Segurança (detalhes técnicos)

O JARVIS executa ações reais na máquina, então o modelo é tratado como **não confiável**
e tudo passa por validação no backend. Resumo do que foi endurecido:

- **`/exec`**: blacklist de comandos destrutivos/de sistema (403), timeout de **30 s**,
  saída limitada a **10 KB**, histórico em `exec_history.json`;
- **`/exec` — furos fechados na v1.0.16**: além das regras antigas (`rm -rf`, `del /f`,
  `format C:`, `diskpart`, `shutdown`, `poweroff`, `reboot`, `bcdedit`, `takeown`,
  `reg delete`, `Remove-Item -Recurse`, `cipher /w:`, `vssadmin`, `wevtutil cl`,
  `net user`/`net localgroup`, `icacls /grant`, `mklink`, `sc delete`, `schtasks /create`,
  `netsh firewall`, `wmic … delete`, `dd if=`, `mkfs`/`fdisk` e fork bomb), a blacklist passou
  a cobrir: **`powershell|pwsh` com `-e`/`-enc`/`-encodedcommand`** (bypass por base64),
  **`rd /s /q`** e **`rmdir /s /q`**, **`Remove-Item … -Force`** (mesmo sem `-Recurse`),
  **`Format-Volume`** e **`Clear-Disk`** (PowerShell Storage), **`net stop`** (parar
  serviços) e **`taskkill /F /IM`** (em qualquer ordem dos flags). Teste de regressão: 55
  casos (26 bloqueados antigos + 14 novos bloqueados + 15 permitidos como `dir`,
  `python --version`, `powershell -Command …`) — todos corretos. ⚠️ **Limitação honesta**:
  blacklist por regex **não substitui um sandbox real** — ainda passam, por exemplo,
  `taskkill /F /PID …`, `rd /s` (sem `/q`) e `powershell -c` com
  `[Convert]::FromBase64String` inline;
- **`/read-file`**: bloqueio de arquivos sensíveis (`.key`, `.pem`, `SAM`, `/etc/shadow`,
  `.ssh`, `config.json`…), leitura restrita a **Documents/Downloads/Desktop** + pasta do app,
  máximo de **1 MB**;
- **`/power`**: o `confirmed` do **modelo é descartado** (só o "sim" do Comandante executa),
  **TTL de 120 s**, carência de 30 s, e log de pedidos registrados/confirmados/cancelados/expirados;
- **`/exec` e `/power` protegidos por token (v1.0.16)**: a dependência
  `require_exec_token` (via `Depends` em `POST /exec` e `POST /power`) exige o header
  `X-Jarvis-Token` igual à env `JARVIS_EXEC_TOKEN`, comparado em tempo constante
  (`secrets.compare_digest`). Sem a env configurada **toda** chamada é negada antes de
  chegar à rota; com a env mas token ausente/errado, também. Nos dois casos: **403**
  `{"detail": "<motivo>"}` (handler padrão do `HTTPException`, sem stacktrace) e registro
  no `security.log` com `[auth] BLOQUEADO …`. `/power/cancel` segue sem token (só
  cancela um desligamento pendente via `shutdown /a`). Template: `.env.example`;
- **`/tts`**: máximo de **2000 caracteres** e sanitização (sem caracteres de controle nem SSML);
- **`/api/chat`**: **rate limit de 30/min**, entrada de **5000** e saída de **10000** caracteres,
  respostas sanitizadas (sem HTML/scripts);
- **config**: `config.json` com permissão **0600** e `GET /api/config/masked` (chave mascarada);
  um valor mascarado nunca sobrescreve a chave real;
- **CORS** restrito a `http://127.0.0.1:8755` / `http://localhost:8755` (nunca `*`) e headers
  `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`;
- **logs**: `security.log` em `%APPDATA%\JARVIS\` com comandos, leituras, tentativas de
  desligamento, bloqueios e uso do visualizador 3D;
- **erros inesperados (v1.0.16)**: `@app.exception_handler(Exception)` global em
  `backend/main.py` e `app.py` — qualquer exceção não tratada vira **500 JSON**
  `{"error": "internal_server_error", "detail": "<tipo>: <mensagem>"}` (sem stacktrace na
  resposta) e é registrada no `security.log` com **timestamp, método, path, tipo e mensagem**
  (ex.: `2026-10-11T17:50:40 [erro] POST /__boom -> 500 RuntimeError: boom de teste`). É
  camada extra: os `try/except` existentes seguem intactos e `HTTPException` (404/403/…)
  continua sendo tratado normalmente.

Detalhes completos, exemplos de log e as variáveis de ambiente para estender as proteções
estão em **[SECURITY.md](SECURITY.md)**.

## Google — Gmail e Google Agenda (v1.0.22)

O JARVIS agora **lê os seus emails** e **mexe na sua agenda de verdade**. Você fala, ele
consulta e age:

```
“Jarvis, quais são os meus emails?”          → lê os não lidos e resume só os importantes
“Jarvis, tem algo importante no meu email?”  → busca is:important e destaca o que exige ação
“Jarvis, lê o email do banco”                → abre o email e resume
“Jarvis, o que eu tenho na agenda amanhã?”   → lista os eventos da Google Agenda
“Jarvis, põe na minha agenda uma reunião    → cria o evento (calendar_add) e confirma
 dia 12 às 15h com o financeiro”
“Jarvis, cancela a reunião de sexta”         → localiza o id e apaga o evento
```

São **cinco ferramentas novas** no agente: `gmail_list`, `gmail_read`, `calendar_list`,
`calendar_add` e `calendar_delete`. O modelo só responde depois do resultado real da
ferramenta; sem resultado, ele diz “Não há nada, Comandante” (mesma regra anti-alucinação das
outras ferramentas). Os **lembretes locais** (`agenda*.json`) continuam separados — a Google
Agenda é a agenda da conta Google.

### Como conectar (uma vez)

1. entre em <https://console.cloud.google.com/> e crie (ou escolha) um projeto;
2. **APIs e serviços → Biblioteca**: ative **Gmail API** e **Google Calendar API**;
3. **APIs e serviços → Tela de consentimento OAuth**: tipo **Externo**, preencha nome/email e,
   em **Usuários de teste**, adicione o seu próprio email (o app fica em modo de teste — sem
   verificação do Google);
4. **APIs e serviços → Credenciais → Criar credenciais → ID do cliente OAuth** → tipo
   **App para computador (Desktop app)**;
5. copie o **Client ID** e o **Client Secret**, abra o JARVIS → **engrenagem ⚙ → Google**, cole
   nos dois campos e clique em **Conectar Google**;
6. o navegador abre a autorização do Google; autorize e a aba mostra
   “JARVIS conectado ao Google”. O status na engrenagem passa a `conectado · seu@email.com`.

O **redirect** `http://127.0.0.1:8899/google/callback` já está embutido — clientes do tipo
*Desktop app* aceitam loopback com qualquer porta, então não precisa cadastrar URI nenhuma.
Se a porta 8899 estiver ocupada, troque em `config.json` (**`googleRedirectPort`**).

### Escopos e segurança

| Escopo | Para quê |
|---|---|
| `gmail.readonly` | **só ler** emails — o JARVIS não envia, não apaga e não marca como lido |
| `calendar` | ler, criar e apagar eventos na agenda |
| `openid email profile` | mostrar qual conta está conectada |

- O **refresh token** fica em `google_token.json` na pasta de dados (`%APPDATA%\JARVIS\` no
  `.exe`), com permissão **0600**, e é **excluído do build** (`JARVIS.spec` filtra o arquivo).
  Ele **nunca** é devolvido para a interface: `GET /google/status` responde apenas
  conectado/email/escopos;
- o **Client Secret** é gravado no `config.json` com 0600, aparece **mascarado** em
  `GET /api/config/masked` e um placeholder mascarado nunca sobrescreve o valor real;
- **Desconectar** apaga o token na hora (`POST /google/disconnect`); para revogar o acesso de
  vez, remova o app em <https://myaccount.google.com/permissions>;
- as chamadas ao Google saem do backend local (`127.0.0.1:8000`) direto para
  `googleapis.com` por HTTPS — nenhum intermediário. O `security.log` registra
  `google: conta conectada`, `agenda-google: evento criado/removido` e desconexões.

### Detalhes técnicos

- **OAuth 2.0 escrito à mão** (sem SDK): `POST /google/connect` gera `state`, sobe um
  `HTTPServer` local em `127.0.0.1:8899`, devolve a URL de consentimento e espera até **5 min**;
  `_GoogleCallbackHandler` valida o `state`, mostra uma página “JARVIS conectado” e o código é
  trocado por tokens em `oauth2.googleapis.com/token` (`access_type=offline` + `prompt=consent`
  para receber o refresh token);
- **renovação automática**: `_google_access_token()` renova com o refresh token quando faltam
  menos de 60 s para expirar e regrava o arquivo — se o Google recusar, a resposta é **409** com
  “conecte de novo em Configurações → Google”;
- **Gmail**: `messages.list` + `messages.get(format=metadata)` para a lista (remetente, assunto,
  data, snippet, `unread`/`important`) e `format=full` para ler, escolhendo `text/plain` e caindo
  para o HTML convertido em texto;
- **Agenda**: `events.list` com `singleEvents=true&orderBy=startTime` na janela pedida e
  `events.insert`/`events.delete` no calendário `primary`. Datas aceitam `AAAA-MM-DD HH:MM`,
  `DD/MM/AAAA HH:MM` e `DD/MM HH:MM` (o mesmo `_parse_dt` da agenda local) e o evento sai com
  `timeZone` de `googleTimezone`; sem `end`, a duração padrão é **60 min**;
- **sem conexão, nada quebra**: as rotas respondem **409** com uma frase clara, o chat continua
  com as ferramentas locais e o `GET /health` informa `google_connected: false`.

Testado localmente (backend em 8011-8013): `/google/status`, `/google/connect` sem credenciais
(**400**), com credenciais falsas (URL gerada e listener em 8899 respondendo **200**), callback com
`state` errado, `/gmail/messages` e `/calendar/events` sem conexão (**409**), `masked` preservando
o Client Secret e `POST /google/disconnect`. **Não** foi possível validar a leitura real de emails
nem a criação de eventos sem uma conta Google autorizada — o fluxo completo depende do passo
“Conectar Google” com credenciais reais.

## Notas — Obsidian e Logseq (v1.0.23)

Destinos de "anota isso para mim" controlados por voz, tudo local e sem conta. **Google Keep ficou de
fora**: a API dele só existe para contas Google Workspace administradas — uma conta Gmail comum não
consegue autorizar. O JARVIS não finge: se o Comandante pedir Keep, ele explica em uma frase e oferece
Obsidian ou Logseq.

### Ferramentas do agente

| Fala | Ferramenta | O que acontece |
|---|---|---|
| "grava uma nota no Obsidian" | `obsidian_add` | grava/anexa um `.md` dentro do vault |
| "procura no meu vault por reunião" | `obsidian_search` | busca texto nas notas |
| "anota no journal do Logseq" | `logseq_add` | bloco no journal do dia (ou em `page`) |
| "procura no Logseq por projeto" | `logseq_search` | busca texto nas páginas do grafo |

### Como configurar

- **Obsidian**: ⚙ → **Pasta do vault Obsidian** (ex.: `C:\Users\voce\Documents\MeuVault`) → **Salvar**.
- **Logseq**: ⚙ → **Pasta do grafo Logseq** (ex.: `C:\Users\voce\Documents\notes`) → **Salvar**.
- O backend valida que a pasta existe e **só grava `.md` dentro dela**: qualquer caminho que tente
  sair é normalizado e contido (`_safe_note_path` + `resolve()`) e o título vira nome de arquivo
  sanitizado. Pasta inexistente ou caminho inválido → **400** com uma frase clara.

### Detalhes técnicos

- **Obsidian/Logseq**: tudo local, sem rede. `NOTE_MAX_CHARS` limita o texto por nota e a busca é
  por substring (sem índice, com limite de arquivos por consulta);
- **sem configuração, nada quebra**: as rotas respondem **409** com "configure em Configurações" e as
  ferramentas devolvem `ok: false` com a mesma frase.

**Testado localmente**: criação e anexação de nota no Obsidian em pasta temporária, tentativa de
path traversal (`../../fora` fica contida no vault), journal e página do Logseq, e busca nos dois.

## Mudanças recentes (v1.0.22)

**Integração Google: Gmail + Google Agenda por voz.**

1. **Cinco ferramentas novas no agente** — `gmail_list`, `gmail_read`, `calendar_list`,
   `calendar_add`, `calendar_delete` (`TOOLS_SCHEMA`/`TOOL_ALIASES`/`run_tool` no `app.py`, rotas
   `/gmail/*` e `/calendar/*` no `backend/main.py`). O prompt de personalidade ganhou a seção
   **GMAIL E GOOGLE AGENDA**: ler antes de falar, resumir só o que importa, conferir o horário
   antes de criar e nunca inventar email/evento.
2. **OAuth 2.0 completo sem SDK** — `POST /google/connect` + `GET /google/status` +
   `POST /google/disconnect`, com servidor local em `127.0.0.1:8899`, validação de `state`,
   refresh automático e token em `google_token.json` (**0600**, fora do build).
3. **Configurações** — bloco **Google** na engrenagem: status ao vivo
   (`conectado · email`), Client ID/Secret, **Conectar** (abre a autorização e acompanha o
   resultado) e **Desconectar**. As chaves `googleClientId`, `googleClientSecret`,
   `googleTimezone` e `googleRedirectPort` entraram no `load_config`/`POST /api/config` — sem
   isso, salvar as configurações apagaria as credenciais já cadastradas.
4. **Privacidade** — escopo de leitura no Gmail (`gmail.readonly`, sem envio/exclusão), Client
   Secret mascarado em `/api/config/masked` e nenhum token devolvido ao HUD.

## Mudanças recentes (v1.0.27)

- **Interface redesenhada (visual)**: rótulos de voz e metadados das mensagens deixaram de usar
  caixa-alta com espaçamento largo, e o botão do microfone ganhou transição de sombra. Layout,
  cores e comportamento seguem os mesmos.

`v1.0.27` — `JARVIS.exe` e instalador `JARVIS-Setup.exe` regerados.

## Mudanças recentes (v1.0.26)

- **Salvar NVIDIA não volta mais para Groq**: o `server.js` (alternativa Node, `start-server.bat`)
  não reconhecia o provedor `nvidia` e gravava `groq` no lugar. Agora aceita `nvidia`, grava e
  devolve a chave e o modelo da NVIDIA. (O `.exe` usa o `app.py`, que já funcionava.)

`v1.0.26` — instalador `JARVIS-Setup.exe` regerado.

## Mudanças recentes (v1.0.25)

### NVIDIA NIM e Ollama

- **404 no modelo da NVIDIA corrigido**: o campo "Modelo" podia ter o nome de exibição
  ("Nemotron 3.5 Bolt E4B") em vez do id. Agora o JARVIS resolve o nome para o id do catálogo;
  um id que não existe mais é descartado e a lista testada assume;
- **410 Gone** (`meta/llama-3.3-70b-instruct` descontinuado) agora passa para o próximo modelo
  em vez de parar; só 401/403 são tratados como erro fatal de chave;
- padrões NVIDIA atualizados para `nvidia/nemotron-3.5-lightning-30b-a3b`,
  `nvidia/nemotron-3-ultra-550b-a55b` e `google/gemma-4-31b-it` (testados com a chave, com tools);
- **Ollama "não responde"**: quase sempre o servidor não está rodando. Antes de usar, abra o
  Ollama (ou rode `ollama serve`) e confira `http://127.0.0.1:11434/api/tags`.

### Versão

`v1.0.25` — instalador `JARVIS-Setup.exe` regerado com as correções acima.

## Mudanças recentes (v1.0.21)

### Logo no app e no executável

- o `logo.jpg` entrou no projeto: aparece no topo da barra lateral do HUD (`public/logo.jpg`,
  30×30 com cantos arredondados e `object-fit: cover` — sem distorcer) e aqui no README;
- o mesmo desenho virou ícone do `.exe` e do instalador (`assets/jarvis.ico`, gerado do
  `logo.jpg` em 16 → 256 px): barra de tarefas, atalho da área de trabalho e "Adicionar ou
  remover programas" deixam de mostrar o ícone genérico;
- a marca em SVG que existia antes saiu do HTML; nada mais mudou no layout do HUD.

### Provedor NVIDIA NIM (além de Groq e Ollama)

- **Provedor de IA** na engrenagem ⚙ ganhou a opção **NVIDIA NIM (Nuvem)**, com campo de chave
  (`nvapi-…`), campo de modelo opcional e o mesmo streaming/tool calling dos outros provedores;
- endpoint `https://integrate.api.nvidia.com/v1` (OpenAI-compatível), com fallback
  `meta/llama-3.3-70b-instruct` → `openai/gpt-oss-120b` → `meta/llama-3.1-8b-instruct`;
- duas chaves novas no `config.json`: `nvidiaKey` e `nvidiaModel` (gravadas com 0600; o
  `/config/masked` devolve só a máscara e o POST ignora placeholder mascarado, igual à Groq);
- erro de provedor agora tem dica própria: 401/403 apontam para `build.nvidia.com/settings` e
  a mensagem sugere conferir o modelo no catálogo.

### Versão

`v1.0.21` — instalador `JARVIS-Setup.exe` regerado com o ícone novo; o `.exe` continua
autocontido (não precisa de Python instalado) e o clima da v1.0.20 segue valendo.

## Mudanças recentes (v1.0.20)

Duas frentes: o **globo que engasgava enquanto ele falava** e o **clima que não achava a
cidade** no `.exe`.

### 1. Globo mais leve (o travamento ao falar)

A causa raiz estava no CSS, não no Three.js:

- **`filter: drop-shadow` no canvas** (`#globe.speaking`, com `transition: filter 500ms`): um
  filtro CSS num canvas WebGL animado obriga o navegador a re-rasterizar e re-borrar o canvas
  **inteiro a cada quadro** — e ele ligava justo quando o JARVIS começava a falar, ou seja, no
  momento em que o quadro já estava mais pesado (voz → partículas pulsando). O filtro saiu e o
  brilho da fala agora vem do **halo aditivo da própria cena**: visual igual, sem custo de
  composição.
- **`PR_CAP = 1.5`** (era 2) + **degrau adaptativo** `prScale`: a nuvem são pontos aditivos
  grandes que se sobrepõem, então o custo de GPU cresce ~com o **quadrado** do pixel ratio. Em
  tela HiDPI o limite 2 dobrava o trabalho sem ganho visível. O `prScale` cai sozinho quando o
  quadro pesa (piso 0,75) e volta devagar.
- **`k60()` — tudo em função do `dt`**: todo amortecimento (brilho do núcleo, zoom, retorno ao
  centro) usa `1 - (1 - k)^(dt × 60)`. Antes o valor era fixo por quadro, então a velocidade do
  movimento mudava com o fps (60/144/240 Hz); agora é a mesma em qualquer taxa.
- **`uDentOn` no shader**: o laço de covas (deformação) rodava o raio inteiro para depois
  descobrir que não havia cova nenhuma; o uniforme agora corta o laço
  (`if (i >= uDentOn) break;`).
- **`uTalkTime` separado de `uTime`**: a fase do wobble da fala vivia no relógio da cena, então
  começar/parar de falar reiniciava a ondulação. Agora tem acumulador próprio e é
  **proporcional a `uVoice`** (sem voz, sem wobble).
- **hover com limite**: o raycast do `pointermove` roda no máximo a cada **90 ms**
  (`lastHoverCheck`), em vez de a cada evento do mouse.
- **CSS das barras de voz**: a animação `barPulse` rodava em todas as barras do HUD, paradas ou
  não, e passou para `.eq i` (só as da voz, com a altura vinda do áudio real); `.wave` ganhou
  `flex: 0 0 24px` porque o flex do painel esmagava a barra para 0 px.

**Medido** no Edge real (AMD RX 580 / D3D11, janela 1280×800, medição por CDP): **~178 fps**
com p95 de **5,7 ms** e **nenhum quadro acima de 33 ms**, tanto em repouso quanto falando;
`globo ok: true` e console sem erros. O ganho visual do filtro só se confirma no app
instalado — a janela `--app=` do Edge usada na medição não compõe da mesma forma.

### 2. Clima: previsão e cidade de volta no `.exe`

O HUD mostrava literalmente
`{"error":"não consegui consultar a cidade agora: No module named 'geopy'"}` e o `/weather`
respondia `needs_city`, porque `import whereismyip` também falhava. Os dois pacotes estavam no
`requirements.txt`, mas **não no build** — e o `JARVIS.spec` precisava declará-los à mão porque
`backend/main.py` entra como **dado** (o PyInstaller não lê os imports dele).

Troca por **HTTP direto**, sem chave e sem pacote novo:

| Antes | Agora | Cliente |
|---|---|---|
| `geopy` + Nominatim (cidade → lat/lon) | **geocoding do open-meteo** (`/v1/search`) | `requests` |
| `whereismyip` (IP → cidade) | **ipwho.is** (`?fields=success,city,region,country,latitude,longitude`) | `requests` |

- `POST /weather/location` devolve o **nome resolvido**: `sao paulo, sp` → **São Paulo**
  (`-23.5475, -46.6361`); cidade inexistente → **404** com dica (*"não encontrei 'xkcdqwzz' —
  tente \"cidade, estado\""*); campo vazio → **400** (*"informe a cidade"*). A busca usa só o
  nome antes da vírgula, então o sufixo do estado não atrapalha o índice.
- A detecção por IP **corrige o nome**: o IP devolve `Sao Joao do Paraiso` (sem acento) e o
  geocoding devolve **São João do Paraíso, Minas Gerais** com o centro da cidade — o `/weather`
  responde `location_source: "ip"` e o HUD mostra o nome certo. Se o geocoding falhar, o nome
  do IP é usado como está.
- **`timezone=auto`** no forecast do open-meteo (era `America/Sao_Paulo` fixo): fora do Brasil o
  `medido_em`, a máxima e a mínima vinham no fuso errado.
- `backend/requirements.txt` e `JARVIS.spec` **não citam mais** `geopy`/`whereismyip`: o próximo
  build não depende de pacote que não esteja instalado.

Testado no servidor real (porta 8765): `GET /weather` com cidade do config, com cidade manual e
**por IP**; `GET /weather/location` nos dois estados (`config`/`manual` e `ip`); e os três casos
de erro do `POST`.

## Mudanças recentes (v1.0.19)

Três correções de **causa raiz** — voz no `.exe` e clima de verdade:

1. **Edge TTS voltou (HTTP 403)** — a versão empacotada (`edge-tts` 7.2.8) falava com o host
   `speech.platform.bing.com`, desativado pela Microsoft. O `backend/requirements.txt` agora pede
   **`edge-tts>=7.3.0,<8`** (fix `rany2/edge-tts#490`) e o `.exe` foi regerado com a 7.3.1:
   `POST /tts` com `engine: "edge"` volta a devolver **MP3** (testado: 200, `audio/mpeg`,
   cabeçalho ID3). O fallback Edge↔Piper e os registros no `security.log` continuam iguais.
2. **Piper no `.exe` ("logreg_iris.onnx.json")** — o erro não era do ONNX: o `find_model()`
   caía num glob de último recurso e pegava o **dataset de teste** do onnxruntime
   (`onnxruntime/datasets/logreg_iris.onnx`, que não tem `.json`) como se fosse a voz, porque
   **nenhuma voz ia para o build**. Agora: (a) o `JARVIS.spec` empacota a voz padrão
   (`voices/pt_BR-cadu-medium.onnx` + `.json`) em `datas`; (b) o backend procura voz em
   `sys._MEIPASS`/`_internal/voices`; (c) o último recurso só aceita `.onnx` com o `.onnx.json`
   ao lado; (d) faltando o json, o erro é claro (`falta a configuração X ao lado de Y`) em vez
   do `FileNotFoundError` cru. `GET /voices` volta a listar as vozes no `.exe`.
3. **Clima de outra pessoa** — a cidade era fixa em São João do Paraíso - MG. Agora vem do
   `config.json` (`weather_city`/`weather_lat`/`weather_lon`), com **geolocalização por IP**
   (`whereismyip`, prazo de 2 s) como reserva e o campo **"Cidade do clima"** nas configurações
   (lat/lon resolvidos **uma vez** com geopy/Nominatim). Sem config e sem IP ele **pergunta a
   cidade** (`needs_city`) em vez de mostrar a errada. A resposta ganhou `city` e
   `location_source`; a voz fala *"em <cidade>"* e o `security.log` registra só a cidade e a
   origem — nunca lat/lon. Detalhes na seção **[Clima](#clima)**.

### Anteriores (v1.0.18)

Modo AR por voz — a última peça que faltava: *"Jarvis, me mostra uma espada na mão"*.

1. **Detecção de intenção** (`app.py` e `server.js`, os dois backends de chat): "na mão" /
   "na minha mão" é o gatilho principal; *"ativa o modo AR"*, *"abre a AR"*, *"liga a AR"*,
   *"modo AR"*, *"realidade aumentada"* e *"câmera AR"* abrem sem objeto. *"Me mostra um carro"*
   (sem "na mão") **não** é AR: continua indo para o visualizador 3D normal — e o bloqueio
   *"na mão"* foi somado ao filtro do visualizador, para os dois caminhos nunca disputarem.
2. **Extração do objeto** por regex a partir dos verbos *mostra/mostre/exibe/põe/coloca/traz/
   abre/ver/visualiza* (+ artigo opcional): *"um carro"*, *"a espada"*, *"um carro esportivo"*.
3. **Mapa objeto → modelo** (37 sinônimos, nomes iguais aos `MODEL_NAMES` de `public/ar.html`):
   carro→sedan, caminhão→truck, carro esportivo→hatchback-sports, furgão→van, robô→character,
   espada/arma/adaga→espada, escudo→escudo, nave/foguete→nave, astronauta, árvore→arvore,
   hambúrguer/comida→hamburger. Sem acerto no mapa, **match parcial em `GET /ar-models`**
   (ex.: *speeder* → `craft_speederA`). Sem acerto nenhum: abre no modelo padrão.
4. **`POST /ar-open`** em `backend/main.py`: abre `/ar.html?modelo=<nome>` (ou sem parâmetro) no
   navegador e devolve *"Abrindo o/a <modelo> no Modo AR, Comandante."* — a frase vai por voz e o
   **chat não é aberto**. O nome é sanitizado (`[a-z0-9-]`, 24 caracteres) antes de virar URL.
5. **Rede de segurança**: se o backend estiver fora do ar, a resposta é *"Não consegui abrir o
   Modo AR, Comandante. …"* em vez de silêncio.
6. **Sobra da FASE B removida**: `public/models/test.glb` era uma cópia byte-a-byte do `sedan.glb`
   (mesmo md5, citada em nenhum arquivo) e aparecia como 12º modelo no `/ar-models`; com ela fora,
   o endpoint lista os **11** modelos documentados.

### Anteriores (v1.0.17)

Modo AR integrado ao HUD — a câmera com um modelo 3D na mão virou recurso do JARVIS:

1. **Página `public/ar.html`** (isolada, não mexe no HUD): webcam + MediaPipe Hands + Three.js
   ortográfico, com o status (câmera, MediaPipe, modelo, gesto, palma, FPS, qualidade, confiança)
   no visual do JARVIS (ciano/âmbar/azul, fundo `#05070c`, Consolas). Botão **"← Voltar"** para a
   câmera e volta ao HUD.
2. **Botão "📷 Ativar AR"** no painel de voz (acima de *Clima*, ao lado de *Visualizar em 3D*):
   abre `/ar.html` em nova aba e, se o pop-up estiver bloqueado, cai para a mesma aba.
3. **11 modelos CC0 do Kenney** copiados para `public/models/` (**1,13 MB**, com licenças e
   texturas por pack): `1`-`9`/`0`/`-` trocam direto, `P`/`Shift+P` ciclam, `R` reseta, `ESC`
   limpa a cena.
4. **Gestos**: punho esconde (dedo dobrado, igual nas duas distâncias), mão aberta mostra, verso
   da mão esconde (produto vetorial + label do MediaPipe, calibrado para mão esquerda e direita) e
   perfil não esconde. O gesto de pinça **saiu**.
5. **`ar.html?modelo=<nome|número>`** abre já no modelo pedido e **`GET /ar-models`**
   (`backend/main.py`, só leitura) lista o que existe em `public/models` — os dois ganchos do
   *"Jarvis, me mostra um carro na mão"* (endpoint verificado com `TestClient`: 200 JSON,
   12 arquivos, todos no disco). Essa foi a versão em que a **ligação por voz ainda era TODO** —
   ela entrou na **v1.0.18**, junto com a remoção do `test.glb` (12 → 11 modelos).
6. **Verificado com webcam real**: 11/11 modelos carregando, modelo aparecendo com a palma
   visível, verso e punho escondendo, todas as teclas e o "← Voltar" parando a câmera
   (track da câmera encerrado) e voltando ao HUD.

### Anteriores (v1.0.16)

Preparação para open source — 9 itens de polimento:

1. **Three.js local** — `public/vendor/three.min.js` (r128, 603 KB, licença MIT) baixado da
   cdnjs e servido por `/vendor/three.min.js` (era `<script>` de CDN no `index.html`): sem
   internet o globo 3D não cai mais no fallback 2D. O PyInstaller embute a pasta `public/`
   inteira, então o vendor entra no `.exe` no próximo build.
2. **Blacklist do `/exec` fechada** — novos padrões em `_EXEC_BLOCK_RE` (`backend/main.py`):
   `powershell|pwsh` com `-e`/`-enc`/`-encodedcommand` (bypass por base64), `rd /s /q`,
   `rmdir /s /q`, `Remove-Item … -Force` (mesmo sem `-Recurse`), `Format-Volume`, `Clear-Disk`,
   `net stop` e `taskkill /F /IM` (em qualquer ordem dos flags). Regressão de **55 casos**
   (26 antigas bloqueadas + 14 novas bloqueadas + 15 permitidas) sem nenhuma falha.
   Limitação documentada: regex **não substitui sandbox**.
3. **Exception handler global** — `@app.exception_handler(Exception)` em `backend/main.py` e
   `app.py`: qualquer exceção não tratada vira **500 JSON**
   `{"error": "internal_server_error", "detail": "<tipo>: <mensagem>"}` (sem stacktrace na
   resposta) e é gravada no `security.log` com timestamp, método, path, tipo e mensagem.
   Camada extra: `try/except` existentes intactos e `HTTPException` (404/403…) normal.
   Verificado com `TestClient` nos dois apps (16/16 checks).
4. **README completo** — seções novas no topo (**O que é o JARVIS**, **Arquitetura** com o
   diagrama das portas 8755 → 8000 → serviços, **Requisitos**, **Instalação**, **Configuração**,
   **Uso**, **Segurança** e **Licença**); o changelog e os detalhes técnicos seguem abaixo.
5. **Autenticação obrigatória em `/exec` e `/power`** — `require_exec_token` (dependência
   `Depends` em `backend/main.py`) exige o header `X-Jarvis-Token` igual à env
   `JARVIS_EXEC_TOKEN` (comparação em tempo constante). Deny-by-default: sem a env, **403**
   `{"detail": "<motivo>"}` antes de chegar à rota, com `[auth] BLOQUEADO` no `security.log`.
   Template em `.env.example`; documentado na seção **Segurança** do README e no
   `SECURITY.md` (seção 15). Verificado com `TestClient` (16/16 checks).
6. **`server.js` e `app.py` repassam o token** — `backendCall()` e `_backend()` leem
   `JARVIS_EXEC_TOKEN` da própria sessão e enviam `X-Jarvis-Token` automaticamente; sem a
   env no ambiente do proxy, a UI recebe 403 no Shell e nos comandos de energia
   (comportamento correto). Testes comportamentais das duas funções (8/8 checks cada).
7. **`config.json.example` criado (template sem segredos)** — mesma estrutura do
   `config.json` real com `groqKey` vazio, exceção `!config.json.example` no `.gitignore` e
   instrução de cópia na seção **Configuração**; a rotação da chave Groq entrou na seção
   **Segurança**.
8. **LICENSE MIT** — arquivo `LICENSE` na raiz (`Copyright (c) 2026 Heitor Miranda`); a
   seção **Licença** do README agora aponta para ele.
9. **Fim das janelas múltiplas (instância única)** — o `JARVIS.exe` abria uma janela nova
   **toda vez** que era executado (mesmo com o app aberto) e o Electron abria outra janela
   + outro backend a cada atalho. Agora os dois têm trava: `launcher.py` usa um **mutex
   nomeado** no Windows — a segunda execução **foca a janela existente** (via
   `EnumWindows`/`SetForegroundWindow`, ignorando consoles e janelas ocultas) e encerra;
   se a interface estiver no ar sem janela, reabre uma apontando para os serviços
   existentes. O `electron/main.js` ganhou `requestSingleInstanceLock()` + handler
   `second-instance` (restaura + foca). O wake word **não** foi mexido: ele nunca abriu
   janela (o `openChat()` só é chamado por clique); o que o usuário via era o relançamento
   do `.exe`. Verificado com testes de processo real (mutex 1º/2º/3º), enumeração de
   janelas Win32 e integração do `main()` no ramo de segunda instância.

### Anteriores (v1.0.15)

Em `public/app.js` — correção de dois erros de runtime do globo 3D (só aparecem em execução;
o `node --check` não os enxerga):

1. **`sw` órfão (linha 482, removida)** — `sw.style('color', 'rgba(160,235,255,0.65)')` era
   resto de um protótipo em **D3** (API `.style()` não existe em `THREE.Mesh`, que só tem
   `.material.color`), e `sw` **não tinha declaração em nenhuma versão do arquivo**: o único
   commit que toca `public/app.js` (`91bd87d checkpoint…`) já trazia só o uso, e varredura por
   `\bsw\b` em todo o projeto acha apenas essa linha (mais um `sw` de *sample width* em
   Python, sem relação). Com `'use strict'`, em runtime ela lançava
   `ReferenceError: sw is not defined` no meio da construção do globo 3D — **depois** que
   `new THREE.WebGLRenderer({ canvas: c })` já tinha consumido o canvas `#globe`. O wireframe
   `wire` já nasce com a cor dele (`0x3fd0ff`, opacidade 0.3), então a remoção não altera o render.
2. **Guarda no globo 2D de reserva** — pelo erro acima, o `catch` da IIFE `globe()` caía no
   fallback com o canvas **já ocupado** pela WebGL; `c.getContext('2d')` devolve `null` (um
   canvas só aceita um tipo de contexto) e o `init()` estourava `Cannot read properties of null
   (reading 'setTransform')`. A guarda `if (!ctx) return;` ficou **logo após o `getContext`**,
   antes do `init()`/`loop` — se ela entrasse só dentro do `init()`, o `loop()` logo abaixo ainda
   chamaria `ctx.clearRect(...)` com `ctx` null (verificado por leitura + execução). Na origem,
   o reserva nem começa: sem listener de resize e sem `requestAnimationFrame`. O HTML continua
   com `<canvas id="globe">` (nada foi removido dele) e o fallback 2D segue íntegro no caso para
   o qual ele existe (Three.js não carregado, ex.: sem internet).

**Verificação** — `node --check public/app.js` limpo; `grep` confirma **zero** ocorrências de
`\bsw\b`; e os dois caminhos executaram de verdade no Node (funções extraídas do próprio
arquivo, sandbox `vm`, sem navegador): **A)** `globeThree()` real: 5 frames, 6 chamadas de
`render()`, buffers de **15.000** (5.000 partículas), 5.000 (fase) e 300 (explosão de 100),
**nenhuma exceção** (o `ReferenceError` sumiu); **B)** cenário do console de vocês (3D falhando
*depois* de o `WebGLRenderer` consumir o canvas → `getContext('2d')` null): **nenhuma exceção**,
o loop 2D não chega a iniciar; **C)** fallback 2D legítimo (sem `THREE`): 3 frames desenhando
normal. Nenhum servidor foi reiniciado e nada foi observado na tela (como solicitado) —
recomendável abrir o app e conferir o F12 antes do rebuild.

### Anteriores (v1.0.14)

Em `public/app.js`, `public/index.html` e `public/styles.css` — duas fases:

**Fase 1 — reverter o globo elástico (a camada de "slime" saiu, o globo base ficou).**
O estado anterior estava **quebrado**, e não só visualmente: o bloco de deformação escrevia
em um `shell` que **não existia em nenhum lugar do arquivo** (`ReferenceError` no primeiro
frame, que o `try/catch` da IIFE `globe()` engolia e jogava o app para o **globo 2D de
reserva**), e ainda mexia em `uni.uDeform`, um uniform que **não estava declarado** no
`ShaderMaterial` (segundo erro, em potencial). A remoção foi cirúrgica:

1. o estado da mola `jelly {target, vel, pos}` e as constantes `JELLY_K`, `JELLY_DAMP`,
   `MAX_DEFORM`, mais os vetores `tmpVec`, `shellDir`, `X_AXIS` e `Y_AXIS`;
2. a coleta da deformação no `pointermove` (o arrasto agora **só gira** o globo) e o
   `jelly.target.set(0, 0, 0)` do `pointerup` — `dragging` e o cursor ficaram;
3. a integração da mola e o bloco do `shell` (quaternion/escala/posição) dentro do loop;
4. a linha `uni.uDeform.value…` e o hook de debug `window.__jarvisGlobeJelly`;
5. o `console.log` que mentia (`"camada de elasticidade removida"`, com a camada ainda lá).

O que **ficou intacto**: as **5.000 partículas** (`N = 5000`) e suas posições de repouso no
`BufferGeometry` (+ `aPhase`), o `ShaderMaterial` próprio delas, o pulso/respiração do
`vertexShader` (`uPulse`/`uVoice`), a rotação com inércia, o zoom, a volta ao centro após 3 s,
os três anéis, a cor do núcleo por contexto e a explosão do wake word.

**Verificação da Fase 1** — `node --check public/app.js` limpo; `grep` da lista de termos da
elasticidade sem nenhuma ocorrência no código de execução (só restou o rótulo "Shell" de uma
ferramenta, sem relação); e **execução headless do `globeThree()` real** (função extraída do
arquivo e rodada no Node com stub do Three.js): **5 frames, 5 chamadas de `render()`, nenhuma
exceção**, `uniforms = uColor, uTime, uSize, uHalfHeight, uOpacity, uPulse, uVoice` (sem
`uDeform`), buffers de **5.000** e **100** pontos.

**Fase 2 — HUD enxuto: só a barra lateral + o globo.** O `.grid` ficou com uma única célula
(`cell-globe`), que já ocupava o espaço restante ao lado da sidebar fixa de **320 px**
(`.app` é flex, `.sidebar { width: 320px; flex-shrink: 0 }`, `.main { flex: 1 }`), com
`grid-template-columns: minmax(0, 1fr)` e `grid-template-areas: "globe"`. Saíram as células
dos painéis (núcleo, eventos, módulos, atividade, sessão/gráfico e provedor). O CSS que
desenha esses painéis (`.feed`, `.tl-item`, `.agent-grid`, `.llm-grid`, `.cell-head`…)
**continua no `styles.css`, mas inerte** — nenhum elemento o usa; ficou de propósito, para não
mexer em regras compartilhadas (`.cell`, `.panel-line`, gráfico) que o globo e os modais ainda
usam. Os itens de nav **Sistema, Módulos, Mercado e Atividade** ganharam
`class="nav-item disabled"` (+ `aria-disabled` e `title`) com **opacidade 0.4** e
`cursor: not-allowed`, e o clique é ignorado (`if (btn.classList.contains('disabled')) return;`);
**Painel, Conversas e Configurações** seguem ativos. As funções que atualizavam os painéis
removidos continuam no `app.js` protegidas por guarda: varredura estática mostra **13 IDs**
citados no JS que não existem mais no HTML (`#feed`, `#activity`, `#coreList`, `#memChart`,
`#modules`, `#modChip`, `#msTurns`/`#msMsgs`/`#msTools`,
`#llmGroq`/`#llmGroqState`/`#llmChip`/`#llmInfo`) e **todos** com `if (!el) return;` ou
`if (el) …`/`if (chip) …`, então nada quebra por elemento ausente. O **modo foco** continua
funcionando (a regra que esconde as outras células simplesmente não casa com nada).

**Instalador** — regerado com `pyinstaller --noconfirm --clean JARVIS.spec` e
`ISCC.exe installer.iss` → `dist-installer/JARVIS-Setup.exe`. O `public/app.js` empacotado em
`dist/JARVIS/_internal/public/` é **idêntico** ao do repositório (mesmo MD5), e o
`index.html` empacotado já traz os **4 itens de nav `disabled`**.

### Anteriores (v1.0.13)

Em `config.json`, `app.py`, `backend/main.py` e `public/app.js`:

1. **Piper é o motor de voz padrão** — o Comandante testou os dois motores e preferiu o
   **Piper com a voz cadu**: mais grave e mais "JARVIS" do que o Edge TTS, que é tecnicamente
   mais natural, mas soa genérico. O padrão passou a `"tts_engine": "piper"` +
   `"tts_voice": "pt_BR-cadu-medium.onnx"` no `config.json` e no `load_config()` do `app.py`;
   o Edge TTS continua no seletor de motor. Ver **"Voz (Piper e Edge TTS)"**.
2. **Reserva invertida** — o `/tts` agora tenta o **Piper primeiro** e cai para o **Edge TTS**
   quando ele falha (antes era Edge primeiro); o front faz a mesma inversão em caso de erro
   HTTP. O JARVIS continua sem ficar mudo em nenhum dos sentidos.

### Anteriores (v1.0.12)

Em `backend/main.py`, `app.py`, `public/index.html`, `public/app.js` e `public/styles.css`:

1. **Clima atualizado de verdade** — o **open-meteo** virou a fonte **primária** (medição de
   ~10-15 min) e o **wttr.in** ficou como reserva (medição de 1-3 h atrás): a diferença chegava
   a 4 °C e 8% de umidade. O `/weather` agora devolve **`medido_em`**, o JARVIS **fala** o
   horário da medição e o HUD mostra no rodapé da caixa de clima. Ver **"Clima"**.

### Anteriores (v1.0.11)

Em `backend/main.py`, `app.py`, `system_prompt.txt`, `public/index.html`, `public/app.js` e
`public/styles.css`:

1. **Notícias com duas fontes** — `GET /news/brasil` traz **G1** e **The News** (RSS), com
   fonte/tópico em whitelist, rate limit e novo botão **"📰 Notícias"** no HUD. Ver
   **"Notícias"**.
2. **Saudação com briefing** — *"bom dia"* responde com clima + 3 notícias reais (e o mesmo
   vale para *boa tarde*; *boa noite* só clima; *boa madrugada* só o cumprimento), com
   fallback local quando não há chave da Groq. Ver **"Saudação (bom dia)"**.

### Anteriores (v1.0.10)

Em `backend/main.py`, `backend/memory.py`, `app.py`, `public/app.js`, `public/index.html`,
`public/styles.css`, `launcher.py` e `JARVIS.spec`:

1. **Voz neural (Edge TTS)** — o JARVIS passa a falar com as vozes **neurais da Microsoft**,
   com o Piper local como reserva automática, e ganha o seletor de **motor + voz** nas
   configurações. Ver **"Voz (Edge TTS e Piper)"**.
2. **Globo cinematográfico** — 2.500 partículas, três anéis concêntricos, **explosão** de
   partículas na palavra-chave e **cor do núcleo por contexto** (ciano/âmbar/vermelho).
   Ver **"Interface: globo 3D e modo foco"**.
3. **Personalidade por contexto** — `detect_context()` lê o **horário** e o **tom** da
   mensagem e injeta um bloco `CONTEXTO ATUAL` antes do LLM, com quatro modos: **trabalho**
   (técnico e direto), **descontraído** (solto), **preocupado** (atencioso, sugere pausa) e
   **empolgado** (comemora). Na madrugada ele lembra de sugerir uma pausa. O tom muda o jeito
   de falar, nunca os fatos.
4. **Memória mais inteligente** — filtro de relevância, **categorias**, busca priorizada por
   categoria e **expiração** em 90 dias para o que nunca foi usado. Ver **"Memória
   persistente"**.

### Anteriores (v1.0.9)

Em `app.py`, `backend/main.py`, `public/index.html` e `public/app.js`:

1. **Personalidade aprendida** — as memórias do Comandante não servem só de contexto: elas
   alimentam um bloco `DIRETRIZES DE PERSONALIDADE DINÂMICA` em cada resposta, para o tom, o
   vocabulário e os interesses acompanharem quem ele é (com a diretriz de nunca inventar
   memórias). Ver **"Memória persistente"**.
2. **Modo programador** — *"Jarvis, me cria um site de portfólio"* gera o código via Groq,
   salva em `%TEMP%`, abre no navegador/editor e apaga ao fechar a aba (ou em 10 min). Botão
   **"💻 Programar"** no HUD. Ver **"Modo programador"**.

### Anteriores (v1.0.8)

Em `system_prompt.txt` (novo), `backend/memory.py` (novo), `backend/main.py`, `app.py`,
`server.js`, `public/app.js`, `public/styles.css` e `public/index.html`:

1. **Personalidade do JARVIS reforçada** — o system prompt passa a ser o texto de
   `system_prompt.txt`, lido por `app.py` e `server.js` (fonte única), com foco nos 6 pilares:
   formalidade britânica, sarcasmo sutil, lealdade, parceria estratégica, calma em crise e
   humor seco. As regras operacionais continuam logo abaixo do texto. Ver **"Personalidade"**.
2. **Memória persistente** — cada conversa enriquece a memória: antes do LLM o JARVIS busca
   as memórias relevantes (`all-MiniLM-L6-v2` via ChromaDB) e injeta
   `MEMÓRIAS SOBRE O COMANDANTE: …`; mensagens do usuário com mais de 20 caracteres são
   salvas (`source="chat"`). Botão **"🧠 Memórias"** no HUD lista, permite esquecer e
   resetar. Tudo sanitizado (1000 caracteres/memória, 10.000 no total, sem chaves/senhas).
   Ver **"Memória persistente"**.

### Anteriores (v1.0.7)

Em `public/app.js`, `public/styles.css`, `public/index.html`, `backend/main.py` e `app.py`:

1. **Previsão do tempo real** — `GET /weather` no backend (wttr.in com reserva open-meteo)
   para São João do Paraíso - MG; o chat detecta "tempo", "clima", "previsão", "temperatura",
   "chuva", "vai chover" e "como tá o dia", consulta a ferramenta `weather` e injeta os dados
   reais no prompt, respondendo por voz no estilo JARVIS (com aviso de guarda-chuva quando há
   chuva). Botão **"🌤️ Clima"** no HUD mostra temperatura, sensação, umidade, vento e
   máxima/mínima. Ver **"Clima"**.
2. **Globo 3D reativo à voz** — o campo de partículas pulsa, gira, brilha e oscila em tempo
   real com o **microfone** (quando a escuta está ativa) e com a **voz do próprio JARVIS**
   (TTS), via AudioContext/AnalyserNode, com oscilação senoidal de reserva e `resume()` no
   primeiro clique. Ver **"Voz → bola"**.

### Anteriores (v1.0.6)

Em `public/app.js`, `public/styles.css`, `backend/main.py`, `app.py` e `server.js`:

1. **Escuta contínua depois do wake word** — dizer "Jarvis" liga `continuousListening` por
   **5 min** (configurável, `0` = infinito) e os comandos seguintes não precisam repetir a
   palavra-chave; cada comando reinicia o timer e, sem comando, a escuta pausa com toast.
   Ver **"Escuta contínua depois do 'Jarvis'"**.
2. **Auditoria de segurança** — blacklist do `/exec`, restrição do `/read-file`, rate limit e
   limites do chat, sanitização do TTS, CORS/headers, `config.json` 0600, `/api/config/masked`
   e `security.log`. Ver **[SECURITY.md](SECURITY.md)**.
3. **Visualizador 3D sob demanda** — "Jarvis, me mostra um carro" gera um HTML de partículas
   com Three.js, abre no navegador e se apaga ao fechar a aba. Ver **"Visualizador 3D sob demanda"**.

### Anteriores (v1.0.5)

- **Chat nunca abre sozinho** — o wake word nunca chama `openChat()`: tudo passa por
  `userOpenChat()`, o único lugar que liga `chatManuallyOpened`.
- **Fala das notícias** — instruções no system prompt + limpeza no `GET /news`
  (`titulo`/`fonte`/`resumo`, sem link).
- **Bola em modo foco ocupa a tela inteira** — container `100vw × 100vh` (`z-index: 100`),
  canvas em `100%`, `camera.aspect = largura / altura` (levemente oval em widescreen).

### Correções anteriores (v1.0.3)

- **Erro de escuta `network`** — `stop()` + espera de 2 s + `start()` na **mesma instância**,
  contador de falhas seguidas, **pausa de 30 s após 5 falhas** e indicador **verde/vermelho**
  que volta a verde sozinho ao reconectar.
- **Chat abria sozinho (falso positivo)** — detecção estrita da palavra-chave:
  **`WAKE_MIN_SCORE = 0.85`**, mínimo de **4 letras em comum** com `jarvis` e
  **cooldown de 3 s** entre disparos.

Depois de qualquer mudança na interface, **rebuilde**: PyInstaller (`dist/JARVIS/JARVIS.exe`)
e, em seguida, Inno Setup (`dist-installer/JARVIS-Setup.exe`).
