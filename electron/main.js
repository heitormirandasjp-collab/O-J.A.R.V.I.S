/**
 * JARVIS — processo principal do Electron (app desktop).
 *
 * Sobe os serviços do JARVIS (ferramentas na 8000 + interface na 8755) reaproveitando
 * o executável do PyInstaller (JARVIS.exe) em modo "sem janela", espera a interface
 * responder e então abre a janela própria do app (sem barra do sistema).
 *
 * Ao fechar, encerra todo o processo do backend.
 */
'use strict';

const { app, BrowserWindow, ipcMain, shell } = require('electron');
const { spawn } = require('child_process');
const http = require('http');
const path = require('path');
const fs = require('fs');

const UI_PORT = Number(process.env.JARVIS_UI_PORT || 8755);
const UI_URL = `http://127.0.0.1:${UI_PORT}`;
let backend = null;
let win = null;

/** Descobre como subir o backend: .exe empacotado, .exe local ou python do venv. */
function backendCommand() {
  const root = path.join(__dirname, '..');
  const candidates = [
    app.isPackaged ? path.join(process.resourcesPath, 'jarvis', 'JARVIS.exe') : null,
    app.isPackaged ? path.join(process.resourcesPath, 'jarvis', 'JARVIS') : null,
    path.join(root, 'dist', 'JARVIS', 'JARVIS.exe'),
  ].filter(Boolean);

  for (const exe of candidates) {
    if (fs.existsSync(exe)) return { cmd: exe, args: [] };
  }
  const py = process.platform === 'win32'
    ? path.join(root, 'backend', 'venv', 'Scripts', 'python.exe')
    : path.join(root, 'backend', 'venv', 'bin', 'python');
  if (fs.existsSync(py)) return { cmd: py, args: [path.join(root, 'launcher.py')] };
  return null;
}

function startBackend() {
  const spec = backendCommand();
  if (!spec) {
    console.warn('[jarvis] backend não encontrado — abrindo só a interface');
    return;
  }
  backend = spawn(spec.cmd, spec.args, {
    cwd: path.dirname(spec.cmd),
    env: Object.assign({}, process.env, { JARVIS_NO_WINDOW: '1' }),
    stdio: 'ignore',
    windowsHide: true,
    detached: false,
  });
  backend.on('exit', () => { backend = null; });
}

function stopBackend() {
  if (!backend || backend.killed) return;
  try {
    if (process.platform === 'win32') {
      spawn('taskkill', ['/PID', String(backend.pid), '/T', '/F'], { windowsHide: true });
    } else {
      backend.kill('SIGTERM');
    }
  } catch (_) { /* já saiu */ }
  backend = null;
}

/** Espera a interface responder (evita tela em branco no boot). */
function waitForUI(timeoutMs = 90000) {
  const end = Date.now() + timeoutMs;
  return new Promise((resolve) => {
    const attempt = () => {
      const req = http.get(UI_URL, (res) => {
        res.resume();
        if (res.statusCode === 200) return resolve(true);
        retry();
      });
      req.on('error', retry);
      req.setTimeout(2000, () => req.destroy());
    };
    const retry = () => {
      if (Date.now() > end) return resolve(false);
      setTimeout(attempt, 500);
    };
    attempt();
  });
}

function createWindow() {
  win = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 900,
    minHeight: 600,
    frame: false,
    transparent: false,
    backgroundColor: '#060a12',
    resizable: true,
    show: false,
    title: 'JARVIS',
    icon: path.join(__dirname, 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  win.once('ready-to-show', () => win.show());
  win.on('closed', () => { win = null; });

  // links externos abrem no navegador padrão, nunca dentro do app
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (/^https?:/i.test(url)) shell.openExternal(url);
    return { action: 'deny' };
  });

  win.loadURL(UI_URL);
}

ipcMain.on('win:minimize', () => win && win.minimize());
ipcMain.on('win:toggleMaximize', () => {
  if (!win) return;
  win.isMaximized() ? win.unmaximize() : win.maximize();
});
ipcMain.on('win:close', () => win && win.close());

app.whenReady().then(async () => {
  startBackend();
  await waitForUI();
  createWindow();
  app.on('activate', () => { if (BrowserWindow.getAllWindows().length === 0) createWindow(); });
});

app.on('window-all-closed', () => {
  stopBackend();
  if (process.platform !== 'darwin') app.quit();
});
app.on('before-quit', stopBackend);
process.on('exit', stopBackend);
