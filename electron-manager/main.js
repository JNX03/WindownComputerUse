// Win:Computer Use — Electron manager (main process)
// - Single instance.
// - Tray icon with Open / Toggle Bypass / Quit.
// - Auto-launch via setLoginItemSettings (the user opts in from inside the app).
// - File-based IPC: reads/writes %USERPROFILE%\.win_computer_use\config.json and tails activity.log.
//   No HTTP, no native ports.

const { app, BrowserWindow, Tray, Menu, nativeImage, ipcMain, shell, dialog, clipboard } = require('electron');
const fs = require('fs');
const path = require('path');
const os = require('os');
const child_process = require('child_process');

const CONFIG_DIR = path.join(os.homedir(), '.win_computer_use');
const CONFIG_PATH = path.join(CONFIG_DIR, 'config.json');
const STATE_PATH = path.join(CONFIG_DIR, 'state.json');
const ACTIVITY_PATH = path.join(CONFIG_DIR, 'activity.log');

// The repo root is the parent of electron-manager/.
const REPO_ROOT = path.resolve(__dirname, '..');
const SERVER_PY = path.join(REPO_ROOT, 'server.py');
const REQUIREMENTS_TXT = path.join(REPO_ROOT, 'requirements.txt');

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

// ----- setup helpers --------------------------------------------------------

function runCommand(cmd, args, opts = {}) {
  return new Promise((resolve) => {
    let stdout = '';
    let stderr = '';
    let proc;
    try {
      proc = child_process.spawn(cmd, args, { windowsHide: true, ...opts });
    } catch (e) {
      resolve({ ok: false, exitCode: -1, stdout: '', stderr: String(e) });
      return;
    }
    proc.stdout && proc.stdout.on('data', (b) => { stdout += b.toString(); });
    proc.stderr && proc.stderr.on('data', (b) => { stderr += b.toString(); });
    proc.on('error', (e) => {
      resolve({ ok: false, exitCode: -1, stdout, stderr: stderr + String(e) });
    });
    proc.on('close', (code) => {
      resolve({ ok: code === 0, exitCode: code, stdout, stderr });
    });
  });
}

async function detectPython() {
  // Try (in order): py -3.12, py -3, python.
  const candidates = [
    { cmd: 'py', args: ['-3.12', '--version'], spawnCmd: 'py', spawnArgs: ['-3.12'] },
    { cmd: 'py', args: ['-3', '--version'], spawnCmd: 'py', spawnArgs: ['-3'] },
    { cmd: 'python', args: ['--version'], spawnCmd: 'python', spawnArgs: [] },
    { cmd: 'python3', args: ['--version'], spawnCmd: 'python3', spawnArgs: [] },
  ];
  for (const c of candidates) {
    const r = await runCommand(c.cmd, c.args);
    const out = (r.stdout + r.stderr).trim();
    const m = out.match(/Python (\d+)\.(\d+)\.(\d+)/);
    if (r.ok && m) {
      const major = +m[1], minor = +m[2];
      if (major === 3 && minor >= 10) {
        // Resolve absolute interpreter path.
        const which = await runCommand(c.spawnCmd, [...c.spawnArgs, '-c', 'import sys; print(sys.executable)']);
        const exe = which.stdout.trim();
        return {
          ok: true,
          found: true,
          launcher: c.spawnCmd,
          launcherArgs: c.spawnArgs,
          version: `${m[1]}.${m[2]}.${m[3]}`,
          exe: exe || null,
        };
      }
    }
  }
  return { ok: true, found: false };
}

async function detectDeps(pythonExe) {
  if (!pythonExe) return { ok: false, error: 'no python' };
  const r = await runCommand(pythonExe, ['-c', "import mcp, pyautogui, mss, pygetwindow, pyperclip; print('ok')"]);
  return { ok: true, installed: r.ok && r.stdout.trim() === 'ok', stderr: r.stderr.slice(0, 400) };
}

function paths() {
  return {
    repoRoot: REPO_ROOT,
    serverPy: SERVER_PY,
    requirementsTxt: REQUIREMENTS_TXT,
    configDir: CONFIG_DIR,
    configPath: CONFIG_PATH,
    statePath: STATE_PATH,
    activityPath: ACTIVITY_PATH,
    home: os.homedir(),
    claudeJsonPath: path.join(os.homedir(), '.claude.json'),
    claudeDesktopConfigPath: path.join(
      os.homedir(),
      'AppData', 'Roaming', 'Claude', 'claude_desktop_config.json'
    ),
    codexConfigPath: path.join(os.homedir(), '.codex', 'config.toml'),
    opencodeConfigPath: path.join(os.homedir(), '.config', 'opencode', 'opencode.json'),
  };
}

ipcMain.handle('setup:paths', () => paths());

ipcMain.handle('setup:detectPython', detectPython);

ipcMain.handle('setup:detectDeps', async (_e, pythonExe) => detectDeps(pythonExe));

ipcMain.handle('setup:installDeps', async (event, pythonExe) => {
  if (!pythonExe || !fs.existsSync(pythonExe)) {
    return { ok: false, error: 'invalid python interpreter path' };
  }
  if (!fs.existsSync(REQUIREMENTS_TXT)) {
    return { ok: false, error: `requirements.txt not found at ${REQUIREMENTS_TXT}` };
  }
  // Stream output back to the renderer.
  return await new Promise((resolve) => {
    const proc = child_process.spawn(
      pythonExe,
      ['-m', 'pip', 'install', '-r', REQUIREMENTS_TXT, '--disable-pip-version-check'],
      { windowsHide: true }
    );
    let stderr = '';
    proc.stdout.on('data', (b) => {
      event.sender.send('setup:installLog', b.toString());
    });
    proc.stderr.on('data', (b) => {
      stderr += b.toString();
      event.sender.send('setup:installLog', b.toString());
    });
    proc.on('close', (code) => {
      resolve({ ok: code === 0, exitCode: code, stderr: stderr.slice(0, 800) });
    });
    proc.on('error', (e) => {
      resolve({ ok: false, exitCode: -1, error: String(e) });
    });
  });
});

ipcMain.handle('setup:detectClaudeCli', async () => {
  const r = await runCommand('claude', ['--version']);
  return { ok: true, found: r.ok, version: (r.stdout + r.stderr).trim().slice(0, 200) };
});

ipcMain.handle('setup:registerClaudeCode', async (event, pythonExe) => {
  if (!pythonExe) return { ok: false, error: 'no python interpreter' };
  if (!fs.existsSync(SERVER_PY)) return { ok: false, error: 'server.py missing' };
  return await new Promise((resolve) => {
    const proc = child_process.spawn(
      'claude',
      ['mcp', 'add', 'win-computer-use', '--scope', 'user', '--', pythonExe, SERVER_PY],
      { windowsHide: true, shell: true }
    );
    let stdout = '', stderr = '';
    proc.stdout.on('data', (b) => {
      stdout += b.toString();
      event.sender.send('setup:installLog', b.toString());
    });
    proc.stderr.on('data', (b) => {
      stderr += b.toString();
      event.sender.send('setup:installLog', b.toString());
    });
    proc.on('close', (code) => {
      resolve({ ok: code === 0, exitCode: code, stdout, stderr });
    });
    proc.on('error', (e) => {
      resolve({ ok: false, exitCode: -1, error: String(e) });
    });
  });
});

ipcMain.handle('setup:launchOverlay', async (_e, pythonExe) => {
  if (!pythonExe) return { ok: false, error: 'no python interpreter' };
  try {
    const proc = child_process.spawn(
      pythonExe,
      ['-m', 'win_computer_use.overlay', '--standalone'],
      {
        cwd: REPO_ROOT,
        detached: true,
        stdio: 'ignore',
        windowsHide: true,
      }
    );
    proc.unref();
    return { ok: true, pid: proc.pid };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
});

ipcMain.handle('setup:writeFile', async (_e, filePath, content) => {
  try {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content, 'utf-8');
    return { ok: true, path: filePath, bytes: Buffer.byteLength(content, 'utf-8') };
  } catch (e) {
    return { ok: false, error: String(e) };
  }
});

ipcMain.handle('setup:pathExists', (_e, p) => ({ exists: fs.existsSync(p) }));

ipcMain.handle('setup:copyToClipboard', (_e, text) => {
  clipboard.writeText(text || '');
  return { ok: true };
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
