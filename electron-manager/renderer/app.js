// Renderer logic for the Win:Computer Use manager.
// All file IO goes through window.api (preload) -> ipcMain.

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

let activityOffset = 0;
let activityPaused = false;
let activityFilter = '';
let cfgCache = {};
let lastConfigJSON = '';

// ---------- Theme ----------
function applyTheme(theme) {
  let effective = theme;
  if (theme === 'system') {
    effective = window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  }
  document.documentElement.setAttribute('data-theme', effective);
  localStorage.setItem('wincu_theme', theme);
  $$('#theme-segmented button').forEach((b) => b.classList.toggle('active', b.dataset.theme === theme));
}

function loadTheme() {
  const saved = localStorage.getItem('wincu_theme') || 'dark';
  applyTheme(saved);
}
loadTheme();

window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', () => {
  const t = localStorage.getItem('wincu_theme') || 'dark';
  if (t === 'system') applyTheme('system');
});

$('#theme-toggle').addEventListener('click', () => {
  const cur = localStorage.getItem('wincu_theme') || 'dark';
  const next = cur === 'dark' ? 'light' : 'dark';
  applyTheme(next);
});

$$('#theme-segmented button').forEach((btn) => {
  btn.addEventListener('click', () => applyTheme(btn.dataset.theme));
});

// ---------- Nav ----------
$$('.navlink').forEach((btn) => {
  btn.addEventListener('click', () => navigate(btn.dataset.page));
});

function navigate(page) {
  $$('.navlink').forEach((b) => b.classList.toggle('active', b.dataset.page === page));
  $$('.page').forEach((p) => p.classList.toggle('active', p.dataset.page === page));
}

// ---------- Config / status loop ----------
async function refresh() {
  const cfg = (await window.api.readConfig()) || {};
  const state = (await window.api.readState()) || {};
  cfgCache = cfg;
  const cfgJSON = JSON.stringify(cfg);
  if (cfgJSON !== lastConfigJSON) {
    renderConfig(cfg);
    lastConfigJSON = cfgJSON;
  }
  renderState(cfg, state);
}
setInterval(refresh, 800);
refresh();

function renderState(cfg, state) {
  const hb = state.heartbeat_at;
  let alive = false;
  if (hb) {
    const ts = Date.parse(hb);
    alive = !isNaN(ts) && (Date.now() - ts) < 8000;
  }
  // Top bar pills
  const dot = $('#topbar-server-dot');
  dot.classList.remove('dot-ok', 'dot-bad');
  dot.classList.add(alive ? 'dot-ok' : 'dot-bad');
  $('#topbar-server-text').textContent = alive ? 'server live' : 'server offline';
  $('#topbar-bypass-text').textContent = `bypass: ${cfg.bypass ? 'on' : 'off'}`;
  const bdot = $('#topbar-bypass-pill .status-dot');
  bdot.classList.remove('dot-ok', 'dot-bad', 'dot-warn');
  bdot.classList.add(cfg.bypass ? 'dot-warn' : 'dot-ok');

  // Status page
  $('#server-status-big') && ($('#server-status-big').textContent = alive ? 'alive' : 'offline');
  $('#server-heartbeat') && ($('#server-heartbeat').textContent = hb ? `heartbeat ${hb}` : 'no heartbeat yet');
  $('#bypass-big') && ($('#bypass-big').textContent = cfg.bypass ? 'ON' : 'OFF');
  $('#agent-big') && ($('#agent-big').textContent = state.agent_name || cfg.agent_name || 'Claude');
  $('#last-action-meta') && ($('#last-action-meta').textContent = state.last_action
    ? `last: ${state.last_action} @ ${state.last_action_at || ''}`
    : 'no action yet');
}

function renderConfig(cfg) {
  // Permissions
  $('#bypass-toggle').checked = !!cfg.bypass;
  renderList($('#allowed-list'), cfg.allowed_apps || [], 'allowed_apps');
  renderList($('#blocked-list'), cfg.blocked_apps || [], 'blocked_apps');

  // Cursor & Agent
  $('#agent-input').value = cfg.agent_name || 'Claude';
  const cc = cfg.cursor_color || '#FE6E58';
  $('#color-input').value = cc;
  $('#color-hex').textContent = cc;
  $('#overlay-toggle').checked = !!cfg.overlay_enabled;
  $('#showcase-toggle').checked = !!cfg.showcase_mode;
  $('#speed-slider').value = cfg.mouse_move_duration_s ?? 0.6;
  $('#speed-value').textContent = (cfg.mouse_move_duration_s ?? 0.6).toFixed(2) + ' s';
  const ah = cfg.cursor_auto_hide_after_s ?? 5;
  $('#autohide-slider').value = ah;
  $('#autohide-value').textContent = ah === 0 ? 'never' : `${ah} s`;

  // Settings
  $('#default-page-select').value = cfg.app_default_page || 'setup';
}

function renderList(ul, items, key) {
  ul.innerHTML = '';
  for (const item of items) {
    const li = document.createElement('li');
    li.innerHTML = `<span>${escapeHtml(item)}</span><button class="remove" title="remove">✕</button>`;
    li.querySelector('.remove').addEventListener('click', async () => {
      const cfg = await window.api.readConfig();
      cfg[key] = (cfg[key] || []).filter((x) => x !== item);
      await window.api.writeConfig(cfg);
      refresh();
    });
    ul.appendChild(li);
  }
}

// ---------- Field handlers ----------
$('#bypass-toggle').addEventListener('change', async (e) => {
  if (e.target.checked) {
    const ok = confirm('Bypass mode lets the AI launch ANY app without your approval. Enable?');
    if (!ok) { e.target.checked = false; return; }
  }
  await window.api.writeConfig({ bypass: !!e.target.checked });
  refresh();
});

$('#agent-input').addEventListener('change', async (e) => {
  await window.api.writeConfig({ agent_name: e.target.value || 'Agent' });
});
$('#color-input').addEventListener('change', async (e) => {
  $('#color-hex').textContent = e.target.value;
  await window.api.writeConfig({ cursor_color: e.target.value });
});
$('#overlay-toggle').addEventListener('change', async (e) => {
  await window.api.writeConfig({ overlay_enabled: !!e.target.checked });
});
$('#showcase-toggle').addEventListener('change', async (e) => {
  await window.api.writeConfig({ showcase_mode: !!e.target.checked });
});
$('#speed-slider').addEventListener('input', (e) => {
  $('#speed-value').textContent = parseFloat(e.target.value).toFixed(2) + ' s';
});
$('#speed-slider').addEventListener('change', async (e) => {
  await window.api.writeConfig({ mouse_move_duration_s: parseFloat(e.target.value) });
});
$('#autohide-slider').addEventListener('input', (e) => {
  const v = parseInt(e.target.value, 10);
  $('#autohide-value').textContent = v === 0 ? 'never' : `${v} s`;
});
$('#autohide-slider').addEventListener('change', async (e) => {
  await window.api.writeConfig({ cursor_auto_hide_after_s: parseInt(e.target.value, 10) });
});

$('#autolaunch-toggle').addEventListener('change', async (e) => {
  await window.api.setAutoLaunch(e.target.checked);
});
window.api.getAutoLaunch().then((s) => {
  $('#autolaunch-toggle').checked = !!(s && s.openAtLogin);
});

$('#default-page-select').addEventListener('change', async (e) => {
  await window.api.writeConfig({ app_default_page: e.target.value });
});

$('#reset-defaults').addEventListener('click', async () => {
  if (!confirm('Reset all settings to defaults? Allowlist and blocklist are also reset.')) return;
  await window.api.writeConfig({
    bypass: false,
    allowed_apps: ['mspaint.exe', 'msedge.exe', 'calc.exe', 'calculator.exe', 'explorer.exe', 'notepad.exe'],
    blocked_apps: [],
    mouse_move_duration_s: 0.6,
    agent_name: 'Claude',
    cursor_color: '#FE6E58',
    overlay_enabled: true,
    showcase_mode: true,
    cursor_auto_hide_after_s: 5.0,
    app_theme: 'dark',
    app_default_page: 'setup',
  });
  applyTheme('dark');
  refresh();
});

$('#allowed-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const v = $('#allowed-input').value.trim().toLowerCase();
  if (!v) return;
  const cfg = await window.api.readConfig();
  cfg.allowed_apps = cfg.allowed_apps || [];
  if (!cfg.allowed_apps.includes(v)) cfg.allowed_apps.push(v);
  await window.api.writeConfig(cfg);
  $('#allowed-input').value = '';
  refresh();
});
$('#blocked-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const v = $('#blocked-input').value.trim().toLowerCase();
  if (!v) return;
  const cfg = await window.api.readConfig();
  cfg.blocked_apps = cfg.blocked_apps || [];
  if (!cfg.blocked_apps.includes(v)) cfg.blocked_apps.push(v);
  await window.api.writeConfig(cfg);
  $('#blocked-input').value = '';
  refresh();
});

// ---------- Emergency stop ----------
$('#emergency-stop').addEventListener('click', async () => {
  await window.api.setEmergencyStop(true);
  refresh();
});
$('#emergency-resume').addEventListener('click', async () => {
  await window.api.setEmergencyStop(false);
  refresh();
});

// ---------- Activity ----------
$('#activity-pause').addEventListener('click', (e) => {
  activityPaused = !activityPaused;
  e.target.textContent = activityPaused ? 'Resume' : 'Pause';
});
$('#activity-clear').addEventListener('click', () => {
  $('#activity-list').innerHTML = '';
});
$('#activity-search').addEventListener('input', (e) => {
  activityFilter = e.target.value.trim().toLowerCase();
});

async function pollActivity() {
  if (!activityPaused) {
    const res = await window.api.tailActivity(activityOffset);
    activityOffset = res.offset || activityOffset;
    for (const line of res.lines || []) {
      let entry;
      try { entry = JSON.parse(line); } catch { continue; }
      if (activityFilter && !entry.tool.toLowerCase().includes(activityFilter)) continue;
      appendActivityRow(entry);
    }
  }
  setTimeout(pollActivity, 600);
}
pollActivity();

function appendActivityRow(entry) {
  const list = $('#activity-list');
  const row = document.createElement('div');
  row.className = 'activity-row ' + (entry.ok ? 'ok' : 'fail');
  const ts = (entry.ts || '').slice(11, 19);
  const args = entry.args ? JSON.stringify(entry.args) : '';
  row.innerHTML = `
    <span class="ts">${ts}</span>
    <span><span class="tool">${escapeHtml(entry.tool)}</span> <span class="args">${escapeHtml(args)}</span></span>
    <span class="ms">${entry.elapsed_ms || 0} ms</span>
  `;
  list.appendChild(row);
  if (list.childElementCount > 600) list.removeChild(list.firstChild);
  list.scrollTop = list.scrollHeight;
}

// ---------- About ----------
$('#open-config').addEventListener('click', (e) => {
  e.preventDefault();
  window.api.openConfigFolder();
});
$('#github-link').addEventListener('click', (e) => {
  e.preventDefault();
  window.api.openExternal('https://github.com/JNX03/win-computer-use');
});
$('#oss-badge').addEventListener('click', (e) => {
  e.preventDefault();
  window.api.openExternal('https://github.com/JNX03/win-computer-use');
});

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}


// ============================================================================
// Setup wizard
// ============================================================================

let SETUP = {
  paths: null,
  python: null,
  depsInstalled: false,
  claudeCliFound: false,
};

async function initSetup() {
  SETUP.paths = await window.api.setupPaths();

  $('#claude-json-path').textContent = SETUP.paths.claudeJsonPath;
  $('#claude-desktop-path').textContent = SETUP.paths.claudeDesktopConfigPath;
  $('#codex-path').textContent = SETUP.paths.codexConfigPath;
  $('#opencode-path').textContent = SETUP.paths.opencodeConfigPath;
  const cdisp = $('#config-path-disp');
  if (cdisp) cdisp.textContent = SETUP.paths.configDir;

  window.api.onSetupInstallLog((line) => {
    const pre = $('#install-log');
    pre.textContent += line;
    pre.scrollTop = pre.scrollHeight;
  });

  await refreshPython();
  await refreshClaudeCli();

  // Honor default page preference once on startup.
  const def = (cfgCache && cfgCache.app_default_page) || 'setup';
  if (def !== 'setup') navigate(def);
}

async function refreshPython() {
  setStepState('step1', 'checking…', 'pending');
  const r = await window.api.setupDetectPython();
  if (!r || !r.found) {
    SETUP.python = null;
    $('#python-exe').textContent = 'not found';
    $('#python-version').textContent = '—';
    setStepState('step1', 'install Python 3.10+', 'bad');
    $('#install-deps').disabled = true;
    rebuildSnippets();
    return;
  }
  SETUP.python = r;
  $('#python-exe').textContent = r.exe || `${r.launcher} ${r.launcherArgs.join(' ')}`;
  $('#python-version').textContent = r.version;
  setStepState('step1', 'ready', 'good');
  $('#install-deps').disabled = false;
  await refreshDeps();
  rebuildSnippets();
}

async function refreshDeps() {
  if (!SETUP.python || !SETUP.python.exe) {
    setStepState('step2', '—', 'pending');
    return;
  }
  const r = await window.api.setupDetectDeps(SETUP.python.exe);
  SETUP.depsInstalled = !!r.installed;
  setStepState('step2', r.installed ? 'installed' : 'not installed', r.installed ? 'good' : 'bad');
}

function setStepState(stepId, text, kind) {
  const el = $(`#${stepId}-state`);
  if (el) {
    el.textContent = text;
    el.classList.remove('state-good', 'state-bad', 'state-pending');
    if (kind === 'good') el.classList.add('state-good');
    else if (kind === 'bad') el.classList.add('state-bad');
    else el.classList.add('state-pending');
  }
  const num = $(`#${stepId}-no`);
  if (num) {
    num.classList.remove('num-good', 'num-bad', 'num-pending');
    if (kind === 'good') num.classList.add('num-good');
    else if (kind === 'bad') num.classList.add('num-bad');
    else num.classList.add('num-pending');
  }
}

async function refreshClaudeCli() {
  const r = await window.api.setupDetectClaudeCli();
  SETUP.claudeCliFound = !!(r && r.found);
  const el = $('#claude-cli-status');
  if (SETUP.claudeCliFound) {
    el.innerHTML = `<code>claude</code> CLI detected · ${escapeHtml(r.version.split('\n')[0])}`;
    $('#register-claude-code').disabled = false;
  } else {
    el.innerHTML = '<code>claude</code> CLI not on PATH — use the snippet below instead.';
    $('#register-claude-code').disabled = true;
  }
}

function rebuildSnippets() {
  if (!SETUP.paths) return;
  const py = (SETUP.python && SETUP.python.exe) || 'python';
  const server = SETUP.paths.serverPy;
  const pyJson = py.replace(/\\/g, '\\\\');
  const serverJson = server.replace(/\\/g, '\\\\');

  const serverEntry = `"win-computer-use": {\n      "command": "${pyJson}",\n      "args": ["${serverJson}"]\n    }`;
  const claudeJson = `{\n  "mcpServers": {\n    ${serverEntry}\n  }\n}`;

  $('#snippet-claude-code').textContent = claudeJson;
  $('#snippet-claude-desktop').textContent = claudeJson;
  $('#snippet-generic').textContent = claudeJson;

  const codexToml =
    `[mcp_servers.win-computer-use]\n` +
    `command = "${pyJson}"\n` +
    `args = ["${serverJson}"]\n`;
  $('#snippet-codex').textContent = codexToml;

  const opencodeJson = JSON.stringify({
    $schema: 'https://opencode.ai/config.json',
    mcp: {
      'win-computer-use': {
        type: 'local',
        command: [py, server],
        enabled: true,
      },
    },
  }, null, 2);
  $('#snippet-opencode').textContent = opencodeJson;
}

// Setup wiring
$('#install-deps').addEventListener('click', async () => {
  if (!SETUP.python || !SETUP.python.exe) return;
  $('#install-deps').disabled = true;
  $('#install-log').textContent = '';
  setStepState('step2', 'installing…', 'pending');
  const r = await window.api.setupInstallDeps(SETUP.python.exe);
  setStepState('step2', r.ok ? 'installed' : `failed (exit ${r.exitCode})`, r.ok ? 'good' : 'bad');
  $('#install-deps').disabled = false;
  await refreshDeps();
});

$('#recheck-deps').addEventListener('click', refreshDeps);

$('#register-claude-code').addEventListener('click', async () => {
  if (!SETUP.python || !SETUP.python.exe) { alert('Detect Python first.'); return; }
  $('#register-claude-code').disabled = true;
  $('#install-log').textContent = '';
  const r = await window.api.setupRegisterClaudeCode(SETUP.python.exe);
  if (r.ok) {
    alert('Registered with Claude Code. Restart Claude Code to pick up win-computer-use.');
  } else {
    alert('Registration failed:\n' + (r.error || r.stderr || `exit ${r.exitCode}`));
  }
  await refreshClaudeCli();
});

$('#launch-overlay').addEventListener('click', async () => {
  if (!SETUP.python || !SETUP.python.exe) { alert('Detect Python first.'); return; }
  const r = await window.api.setupLaunchOverlay(SETUP.python.exe);
  if (r.ok) {
    const orig = $('#launch-overlay').textContent;
    $('#launch-overlay').textContent = `Overlay running (pid ${r.pid})`;
    setTimeout(() => { $('#launch-overlay').textContent = orig; }, 4000);
  } else {
    alert('Overlay launch failed: ' + (r.error || 'unknown'));
  }
});

// Client tabs
$$('.tab').forEach((tab) => {
  tab.addEventListener('click', () => {
    $$('.tab').forEach((t) => t.classList.remove('active'));
    tab.classList.add('active');
    const which = tab.dataset.client;
    $$('.panel').forEach((p) => p.classList.toggle('hidden', p.dataset.client !== which));
  });
});

// Copy buttons
$$('.copy-btn').forEach((b) => {
  b.addEventListener('click', async () => {
    const target = $('#' + b.dataset.target);
    if (!target) return;
    await window.api.setupCopyToClipboard(target.textContent);
    const orig = b.textContent;
    b.textContent = 'Copied ✓';
    setTimeout(() => { b.textContent = orig; }, 1500);
  });
});

const openConfigBtn = $('#open-claude-desktop-config');
if (openConfigBtn) {
  openConfigBtn.addEventListener('click', () => {
    if (!SETUP.paths) return;
    const folder = SETUP.paths.claudeDesktopConfigPath.replace(/\\/g, '/').replace(/\/[^\/]+$/, '/');
    window.api.openExternal('file://' + folder);
  });
}

// Kick off
initSetup();
