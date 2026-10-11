# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules
from PyInstaller.utils.hooks import collect_all

datas = [('public', 'public'), ('backend/main.py', 'backend'), ('backend/memory.py', 'backend'),
         ('system_prompt.txt', '.'), ('SECURITY.md', '.')]
binaries = []
hiddenimports = ['uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto', 'uvicorn.lifespan.on']
hiddenimports += collect_submodules('uvicorn')
tmp_ret = collect_all('piper')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('onnxruntime')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('chromadb')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
# Edge TTS (vozes neurais da Microsoft): precisa do aiohttp, que é importado
# dinamicamente por dentro dele.
tmp_ret = collect_all('edge_tts')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
hiddenimports += collect_submodules('aiohttp')
# o embedder ONNX do chroma importa estes módulos DINAMICAMENTE (importlib),
# então o PyInstaller não os enxerga sozinho:
tmp_ret = collect_all('tokenizers')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
hiddenimports += collect_submodules('tqdm')

# ── segredos NUNCA entram no build (v1.0.16) ─────────────────────────────
# O JARVIS-Setup.exe é distribuído publicamente: o config.json (chave da Groq),
# qualquer *.env e os logs/histórico locais ficam de fora mesmo que um add-data
# de pasta inteira os puxe. Quem instalar cria o próprio config.json a partir
# do config.json.example.
_SENSITIVE_NAMES = {'config.json', 'security.log', 'exec_history.json'}


def _is_sensitive(src):
    s = str(src).replace('\\', '/').lower()
    name = s.rsplit('/', 1)[-1]
    return name in _SENSITIVE_NAMES or name.endswith('.env')


datas = [d for d in datas if not _is_sensitive(d[0])]





a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # O .exe usa o ONNX MiniLM do chromadb (mesmo modelo all-MiniLM-L6-v2) e NÃO o
    # PyTorch/sentence-transformers — sem esses excludes o instalador cresceria GBs.
    # memory.py detecta a ausência e cai para o ONNX automaticamente.
    excludes=['torch', 'torchvision', 'torchaudio', 'sentence_transformers', 'transformers',
              'sklearn', 'scipy', 'pandas', 'matplotlib'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='JARVIS',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='JARVIS',
)
