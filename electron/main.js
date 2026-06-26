'use strict';

const { app, BrowserWindow, ipcMain, Tray, Menu, nativeImage, shell } = require('electron');
const path = require('path');
const fs = require('fs');

const logger = require('./logger');
const paths = require('./paths');
const { PythonBridge } = require('./python-bridge');

let AutoLaunch = null;
try { AutoLaunch = require('auto-launch'); } catch (_) { /* optional */ }

let autoLauncher = null;
function applyAutoLaunch(enabled) {
  if (!AutoLaunch) return;
  try {
    if (!autoLauncher) {
      autoLauncher = new AutoLaunch({ name: 'AFK', isHidden: true });
    }
    autoLauncher.isEnabled().then((isOn) => {
      if (enabled && !isOn) autoLauncher.enable();
      else if (!enabled && isOn) autoLauncher.disable();
    }).catch(() => {});
  } catch (e) {
    logger.warn(`auto-launch failed: ${e.message}`);
  }
}

// Single-instance lock — AFK is a tray app; never run twice.
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
}

let mainWindow = null;
let tray = null;
let bridge = null;
let isQuitting = false;

const DEV = !!process.env.AFK_DEV;

function createWindow() {
  if (mainWindow) {
    mainWindow.show();
    mainWindow.focus();
    return;
  }

  mainWindow = new BrowserWindow({
    width: 980,
    height: 680,
    minWidth: 820,
    minHeight: 560,
    show: false,
    backgroundColor: '#0f1115',
    title: 'AFK',
    icon: path.join(__dirname, '..', 'assets', 'icon.png'),
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    }
  });

  mainWindow.loadFile(path.join(__dirname, '..', 'ui', 'index.html'));

  mainWindow.once('ready-to-show', () => {
    const launchMinimized = process.argv.includes('--minimized');
    if (!launchMinimized) mainWindow.show();
  });

  // Close to tray instead of quitting.
  mainWindow.on('close', (e) => {
    if (!isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  // External links open in the default browser, never in-app.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  if (DEV) mainWindow.webContents.openDevTools({ mode: 'detach' });
}

function createTray() {
  const iconPath = path.join(__dirname, '..', 'assets', 'tray.png');
  let image;
  try {
    image = nativeImage.createFromPath(iconPath);
    if (image.isEmpty()) image = nativeImage.createEmpty();
  } catch (_) {
    image = nativeImage.createEmpty();
  }

  tray = new Tray(image);
  tray.setToolTip('AFK — local speech-to-text');

  const menu = Menu.buildFromTemplate([
    { label: 'Open AFK', click: () => createWindow() },
    { type: 'separator' },
    {
      label: 'Backend status',
      enabled: false,
      id: 'status'
    },
    { type: 'separator' },
    {
      label: 'Quit AFK',
      click: () => {
        isQuitting = true;
        app.quit();
      }
    }
  ]);
  tray.setContextMenu(menu);
  tray.on('double-click', () => createWindow());
}

function broadcast(channel, payload) {
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.webContents.send(channel, payload);
  }
}

function startBackend() {
  bridge = new PythonBridge({ dataDir: paths.dataDir() });

  bridge.on('log', ({ level, msg }) => logger[level] ? logger[level](msg) : logger.info(msg));

  bridge.on('ready', (info) => {
    logger.info(`Backend ready: ${JSON.stringify(info)}`);
    broadcast('backend:status', { ready: true, info });
    // Apply OS-level preferences from saved settings.
    bridge.call('get_settings', {}).then((cfg) => {
      applyAutoLaunch(!!(cfg && cfg.startup_on_login));
    }).catch(() => {});
  });

  // React to settings changes for OS-level behaviors (auto-launch).
  bridge.on('event:settings_updated', (cfg) => {
    applyAutoLaunch(!!(cfg && cfg.startup_on_login));
  });

  bridge.on('exit', () => broadcast('backend:status', { ready: false }));

  // Forward all backend events to the renderer under a single channel.
  bridge.on('event', (event, data) => broadcast('backend:event', { event, data }));

  bridge.start();
}

// ---- IPC: renderer <-> main <-> python ----

function registerIpc() {
  // Generic pass-through to the Python backend.
  ipcMain.handle('afk:call', async (_evt, { method, params }) => {
    if (!bridge) throw new Error('Backend not initialised');
    return bridge.call(method, params || {});
  });

  ipcMain.handle('afk:backendReady', () => (bridge ? bridge.isReady : false));

  ipcMain.handle('app:getInfo', () => ({
    version: app.getVersion(),
    name: app.getName(),
    dev: DEV,
    platform: process.platform,
    electron: process.versions.electron,
    node: process.versions.node
  }));

  ipcMain.handle('window:minimize', () => mainWindow && mainWindow.minimize());
  ipcMain.handle('window:hide', () => mainWindow && mainWindow.hide());
  ipcMain.handle('app:quit', () => {
    isQuitting = true;
    app.quit();
  });

  ipcMain.handle('shell:openExternal', (_e, url) => shell.openExternal(url));
}

// ---- App lifecycle ----

app.on('second-instance', () => {
  createWindow();
});

app.whenReady().then(() => {
  logger.init(paths.logsDir());
  logger.info('AFK starting up');

  registerIpc();
  createTray();
  startBackend();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

// Keep running in the tray when all windows are closed.
app.on('window-all-closed', (e) => {
  // do not quit — AFK lives in the tray
});

app.on('before-quit', () => {
  isQuitting = true;
  if (bridge) bridge.stop();
});

process.on('uncaughtException', (err) => {
  logger.error(`Uncaught exception: ${err && err.stack ? err.stack : err}`);
});
