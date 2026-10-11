# JARVIS — Command Center

Assistente pessoal com HUD animado, voz pt-BR (Piper), ferramentas locais reais e chat
com streaming via **Groq**. Sem fallback: só Groq.

> Nada aqui usa o backend do OpenJarvis. Só o modelo de voz vem de lá
> (`pt-BR-razo-medium.onnx`, na raiz do projeto).

## O que é o JARVIS

Assistente pessoal **local** para Windows, com HUD animado, globo 3D, voz pt-BR (Piper/Edge
TTS), chat com streaming via **Groq** e ferramentas de verdade na máquina (comandos, leitura
de arquivos, clima, notícias, agenda, memória persistente). Roda 100% no seu computador: os
únicos serviços externos são a API da **Groq** (texto) e, se você escolher o Edge TTS, a da
Microsoft (vozes neurais). Não é o OpenJarvis — projeto próprio, sem backend remoto.

## Arquitetura

```
┌─────────────────────────┐
│ Frontend  public/       │  HUD + globo 3D (Three.js r128, servido localmente em
│ HTML/CSS/JS, sem build  │  /vendor/three.min.js — funciona sem internet)
└───────────┬─────────────┘
            │ fetch (mesma origem)
            ▼
┌─────────────────────────┐      ┌──────────────────────────┐
│ Servidor da UI :8755    │ ───▶ │ API da Groq (chat com    │
│ app.py (Python)         │      │ streaming, tool calling) │
│  ou server.js (Node)    │      └──────────────────────────┘
└───────────┬─────────────┘
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
<!-- TODO: requisitos mínimos de hardware (RAM/disco) ainda não medidos -->

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

Depois, configure a chave da Groq (seção **Configuração**) e abra `http://127.0.0.1:8755`.

## Configuração

Tudo fica em **`config.json`**, na raiz do projeto (no `.exe`, em
`%APPDATA%\JARVIS\config.json`). Chaves que o código lê hoje:

| Chave | O que é | Padrão |
|---|---|---|
| `groqKey` | chave da API da Groq — obrigatória para o chat | — |
| `groqModel` | modelo do chat (a lista tem fallback interno) | vazio = modelos testados |
| `tts_engine` | motor de voz: `piper` ou `edge` | `piper` |
| `tts_voice` | voz: arquivo `.onnx` (Piper) ou ShortName (Edge) | `pt_BR-cadu-medium.onnx` |
| `continuous_listen_minutes` | minutos de escuta contínua após o wake word (`0` = infinito) | `5` |

Como obter a chave: crie a conta em <https://console.groq.com>, gere a chave em
<https://console.groq.com/keys> e cole na **engrenagem ⚙** das configurações do JARVIS (ou
direto no `config.json`). Detalhes dos modelos e da voz em **"Chave da Groq"** e **"Voz
(Piper e Edge TTS)"** abaixo.

## Uso

Com o backend (8000) e a UI (8755) no ar, abra `http://127.0.0.1:8755` — ou use o `.exe` /
app Electron, que sobem tudo sozinhos. O que dá pra fazer:

- **Chat** com streaming via Groq e agente com tool calling (engrenagem ⚙ para chave/modelo);
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
- a chave da Groq no `config.json` é **seu** segredo — não commite nem compartilhe o arquivo
  (por isso ele está fora do versionamento).

Blacklist, rate limits, handler global de erros e exemplos de log: em
**[Segurança (detalhes técnicos)](#segurança-detalhes-técnicos)** e no
**[SECURITY.md](SECURITY.md)**.

## Licença

**TBD — a definir.** O `electron/package.json` já declara `MIT`, mas a licença do repositório
ainda não foi escolhida; um arquivo `LICENSE` na raiz é o próximo passo antes de abrir o
projeto como open source.

## Arquivos

```
jarvis/
├── launcher.py            # inicializador do app (vira JARVIS.exe)
├── app.py                 # interface + chat + agente (porta 8755)
├── server.js              # alternativa em Node do app.py (porta 8755)
├── public/                # HUD (HTML/CSS/JS, sem build)
├── backend/
│   ├── main.py            # ferramentas + voz (porta 8000)
│   ├── requirements.txt
│   └── venv/
├── electron/              # app desktop (Electron) — janela própria 1280×800
│   ├── main.js            # cria a janela, sobe os dois serviços e encerra tudo
│   ├── preload.js         # ponte segura (só minimizar/maximizar/fechar)
│   └── icon.png           # ícone do JARVIS
├── voices/                # vozes baixadas (faber/cadu, 60 MB cada)
├── config.json            # chave da Groq (só neste computador)
└── agenda.json            # lembretes/agenda (criado no primeiro uso)
```

No `.exe`, `config.json` e `agenda.json` ficam em `%APPDATA%\JARVIS\`.

## Jeito mais fácil: o executável

`dist/JARVIS/JARVIS.exe` (gerado pelo PyInstaller, ~260 MB na pasta). Dê dois cliques: ele
sobe os dois serviços (8000 e 8755), abre a janela do app e fica rodando. Para encerrar,
feche a janela preta do console ou pressione Ctrl+C nela.

Se o JARVIS já estiver rodando, rodar o `.exe` de novo só abre a janela apontando para a
instância que já está no ar (não duplica serviços). Mantenha a pasta `JARVIS` inteira junto
do `.exe` — o `_internal` faz parte do aplicativo.

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

1. o modelo recebe a mensagem **mais a lista de 14 ferramentas** (`exec`, `read_file`,
   `sysinfo`, `list_processes`, `kill`, `power`, `power_cancel`, `news`, `agenda_add`,
   `agenda_list`, `agenda_delete`, `agenda_check`, `stocks`, `currencies`);
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
| `GET /weather` | clima + previsão de hoje de São João do Paraíso - MG (wttr.in; open-meteo de reserva) |
| `POST /memory/add` | `{ "text", "source" }` → memória persistente (sanitizada) |
| `GET /memory/search?q=...&n=5` | busca semântica nas memórias |
| `GET /memory/list?limit=100` | memórias mais recentes primeiro |
| `DELETE /memory/{id}` · `DELETE /memory/all` | esquecer uma / resetar tudo |
| `POST /memory/archive?days=90` | arquiva (sem apagar) memórias antigas nunca usadas |
| `GET /memory/stats` | total, arquivadas, categorias, datas e embedder |
| `GET /voices` · `POST /voices/download` | vozes locais (Piper) e download |
| `GET /voices-edge` | vozes pt-BR do Edge TTS (com a lista local de reserva) |
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

`GET /weather` devolve o clima real de **São João do Paraíso - MG** (`-15.377, -42.006`),
sem chave. A ordem das fontes foi **invertida na v1.0.12**:

| Ordem | Fonte | Frescor da medição |
|---|---|---|
| **1º (primária)** | **open-meteo** (códigos WMO traduzidos) | medição de **~10-15 min** |
| 2º (reserva) | wttr.in (`format=j1&lang=pt`) | **1-3 h** atrasado (World Weather Online) |

O wttr.in era primário e chegava a **4 °C e 8% de umidade de diferença** por causa desse
atraso — agora ele só entra se o open-meteo falhar. O JSON tem `temp`, `sensacao`, `descricao`,
`umidade`, `vento` ("ESE 12km/h"), `max`, `min`, **`medido_em`** (open-meteo:
`"2026-10-11T09:45"`; wttr.in: `"12:14 PM"`) e `fonte`.

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
(`JARVIS_NO_WINDOW=1`), espera a interface responder na 8755 e só então abre a janela. Ao
fechar a janela, todo o processo do backend é encerrado (`taskkill /T /F` na árvore). Links
externos abrem no navegador padrão, nunca dentro do app.

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

## Mudanças recentes (v1.0.16)

Preparação para open source — 4 itens de polimento:

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
   Licença ainda **TBD**.

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
