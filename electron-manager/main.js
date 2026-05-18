// Win:Computer Use — Electron manager (main process)
// - Single instance.
// - Tray icon with Open / Toggle Bypass / Quit.
// - Auto-launch via setLoginItemSettings (the user opts in from inside the app).
// - File-based IPC: reads/writes %USERPROFILE%\.win_computer_use\config.json and tails activity.log.
//   No HTTP, no native ports.

const { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, shell, dialog } = require('electron');
const fs = require('fs');
const path = require('path');
const os = require('os');

const CONFIG_DIR = path.join(os.homedir(), '.win_computer_use');
const CONFIG_PATH = path.join(CONFIG_DIR, 'config.json');
const STATE_PATH = path.join(CONFIG_DIR, 'state.json');
const ACTIVITY_PATH = path.join(CONFIG_DIR, 'activity.log');

const STARTED_HIDDEN = process.argv.includes('--hidden');

let mainWindow = null;
let tray = null;
let activityWatcher = null;
let activityOffset = 0;

// ----- single instance ------------------------------------------------------
const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

// ----- file helpers ---------------------------------------------------------
function readJson(p, fallback) {
  try {
    return JSON.parse(fs.readFileSync(p, 'utf-8'));
  } catch (e) {
    return fallback;
  }
}

function writeJsonAtomic(p, obj) {
  fs.mkdirSync(path.dirname(p), { recursive: true });
  const tmp = p + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(obj, null, 2), 'utf-8');
  fs.renameSync(tmp, p);
}

// ----- window ---------------------------------------------------------------
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 920,
    height: 640,
    minWidth: 760,
    minHeight: 520,
    show: !STARTED_HIDDEN,
    title: 'Win:Computer Use — Manager',
    backgroundColor: '#0F172A',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  mainWindow.loadFile(path.join(__dirname, 'renderer', 'index.html'));

  mainWindow.on('close', (e) => {
    if (!app.isQuitting) {
      e.preventDefault();
      mainWindow.hide();
    }
  });
}

// ----- tray -----------------------------------------------------------------
function buildTrayIcon() {
  // Generate a simple blue dot icon at runtime so we don't ship a PNG.
  const img = nativeImage.createEmpty();
  const ICON_PATH = path.join(__dirname, 'assets', 'tray.png');
  if (fs.existsSync(ICON_PATH)) return nativeImage.createFromPath(ICON_PATH);
  // 16x16 BGRA bitmap, blue filled circle on transparent — embedded as PNG.
  const base64Png =
    'iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAYUlEQVR4nO3SsQ0AIAwDQYj' +
    'a/2c2ARyaQwVxNk5kT0xvgPCb1A2sBqQGpAakBqQGpAakBqQGpAakBqQGpAakBqQGpAakB' +
    'qQGpAakBqQGpAakBqQGpAakBqQGpAakBqQGpAakBl0AvGEC1mZWvBwAAAABJRU5ErkJggg==';
  return nativeImage.createFromBuffer(Buffer.from(base64Png, 'base64'));
}

function setupTray() {
  tray = new Tray(buildTrayIcon());
  tray.setToolTip('Win:Computer Use Manager');
  const refreshMenu = () => {
    const cfg = readJson(CONFIG_PATH, { bypass: false });
    const menu = Menu.buildFromTemplate([
      { label: 'Open Manager', click: () => { if (mainWindow) { mainWindow.show(); mainWindow.focus(); } } },
      { type: 'separator' },
      {
        label: cfg.bypass ? 'Bypass: ON  (click to disable)' : 'Bypass: OFF  (click to enable)',
        click: () => {
          const c = readJson(CONFIG_PATH, { bypass: false });
          c.bypass = !c.bypass;
          writeJsonAtomic(CONFIG_PATH, c);
          refreshMenu();
        },
      },
      { label: 'Open Config Folder', click: () => shell.openPath(CONFIG_DIR) },
      { type: 'separator' },
      { label: 'Quit', click: () => { app.isQuitting = true; app.quit(); } },
    ]);
    tray.setContextMenu(menu);
  };
  refreshMenu();
  tray.on('click', () => {
    if (!mainWindow) return;
    if (mainWindow.isVisible()) mainWindow.hide();
    else { mainWindow.show(); mainWindow.focus(); }
  });
  setInterval(refreshMenu, 3000);
}

// ----- IPC handlers ---------------------------------------------------------
ipcMain.handle('config:read', () => readJson(CONFIG_PATH, {}));
ipcMain.handle('state:read', () => readJson(STATE_PATH, {}));

ipcMain.handle('config:write', (_e, patch) => {
  const cur = readJson(CONFIG_PATH, {});
  const next = Object.assign({}, cur, patch);
  writeJsonAtomic(CONFIG_PATH, next);
  return next;
});

ipcMain.handle('autolaunch:get', () => app.getLoginItemSettings());
ipcMain.handle('autolaunch:set', (_e, enabled) => {
  if (process.platform !== 'win32') return { ok: false, error: 'windows only' };
  if (enabled) {
    app.setLoginItemSettings({
      openAtLogin: true,
      path: process.execPath,
      args: ['--hidden'],
    });
  } else {
    app.setLoginItemSettings({ openAtLogin: false });
  }
  return app.getLoginItemSettings();
});

ipcMain.handle('activity:tail', (event, fromOffset) => {
  try {
    if (!fs.existsSync(ACTIVITY_PATH)) return { offset: 0, lines: [] };
    const stat = fs.statSync(ACTIVITY_PATH);
    let start = typeof fromOffset === 'number' ? fromOffset : 0;
    if (start > stat.size) start = 0; // rotated
    const fd = fs.openSync(ACTIVITY_PATH, 'r');
    const len = stat.size - start;
    const buf = Buffer.alloc(len);
    fs.readSync(fd, buf, 0, len, start);
    fs.closeSync(fd);
    const text = buf.toString('utf-8');
    const lines = text.split('\n').filter(Boolean);
    return { offset: stat.size, lines };
  } catch (e) {
    return { offset: 0, lines: [], error: String(e) };
  }
});

ipcMain.handle('shell:openConfigFolder', () => shell.openPath(CONFIG_DIR));
ipcMain.handle('shell:openExternal', (_e, url) => shell.openExternal(url));

ipcMain.handle('emergencyStop:set', (_e, on) => {
  const s = readJson(STATE_PATH, {});
  s.emergency_stopped = !!on;
  writeJsonAtomic(STATE_PATH, s);
  return s;
});

// ----- lifecycle ------------------------------------------------------------
app.whenReady().then(() => {
  createWindow();
  setupTray();
});

app.on('window-all-closed', (e) => {
  // Keep running in tray; only quit explicitly via tray menu.
});

app.on('before-quit', () => { app.isQuitting = true; });
