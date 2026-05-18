// Renderer logic for the Win:Computer Use manager.
// All file IO goes through window.api (preload) -> ipcMain.

const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

let activityOffset = 0;
let activityPaused = false;
let activityFilter = '';
let cfgCache = {};
let lastConfigJSON = '';

// ---------- Nav -----------
$$('.nav-item').forEach((btn) => {
  btn.addEventListener('click', () => {
    $$('.nav-item').forEach((b) => b.classList.remove('active'));
    btn.classList.add('active');
    const target = btn.dataset.page;
    $$('.page').forEach((p) => p.classList.toggle('active', p.dataset.page === target));
  });
});

// ---------- Config / status loop -----------
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
  $('#server-dot').className = 'dot ' + (alive ? 'dot-green' : 'dot-red');
  $('#server-state-text').textContent = alive ? 'server alive' : 'server idle/offline';
  $('#server-status-big').textContent = alive ? 'ALIVE' : 'OFFLINE';
  $('#server-heartbeat').textContent = hb ? 'heartbeat ' + hb : 'no heartbeat yet';
  $('#bypass-big').textContent = cfg.bypass ? 'ON' : 'OFF';
  $('#agent-big').textContent = state.agent_name || cfg.agent_name || 'Claude';
  $('#last-action-meta').textContent = state.last_action
    ? `last: ${state.last_action} @ ${state.last_action_at || ''}`
    : 'no action yet';
}

function renderConfig(cfg) {
  $('#bypass-toggle').checked = !!cfg.bypass;
  renderList($('#allowed-list'), cfg.allowed_apps || [], 'allowed_apps');
  renderList($('#blocked-list'), cfg.blocked_apps || [], 'blocked_apps');
  $('#agent-input').value = cfg.agent_name || 'Claude';
  $('#color-input').value = cfg.cursor_color || '#3B82F6';
  $('#color-hex').textContent = cfg.cursor_color || '#3B82F6';
  $('#overlay-toggle').checked = !!cfg.overlay_enabled;
  $('#showcase-toggle').checked = !!cfg.showcase_mode;
  $('#speed-slider').value = cfg.mouse_move_duration_s ?? 0.6;
  $('#speed-value').textContent = (cfg.mouse_move_duration_s ?? 0.6).toFixed(2) + ' s';
  $('#config-path').textContent = (cfg && cfg.__path__) || ''; // optional, server doesn't expose this
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

// ---------- Forms -----------
$('#bypass-toggle').addEventListener('change', async (e) => {
  if (e.target.checked) {
    const confirmed = confirm(
      'Bypass mode lets the AI launch ANY app without your approval. Enable?'
    );
    if (!confirmed) { e.target.checked = false; return; }
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
$('#autolaunch-toggle').addEventListener('change', async (e) => {
  await window.api.setAutoLaunch(e.target.checked);
});
window.api.getAutoLaunch().then((s) => {
  $('#autolaunch-toggle').checked = !!(s && s.openAtLogin);
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

// ---------- Emergency stop -----------
$('#emergency-stop').addEventListener('click', async () => {
  await window.api.setEmergencyStop(true);
  refresh();
});
$('#emergency-resume').addEventListener('click', async () => {
  await window.api.setEmergencyStop(false);
  refresh();
});

// ---------- Activity tailing -----------
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

// ---------- Misc -----------
$('#open-config').addEventListener('click', () => window.api.openConfigFolder());
$('#github-link').addEventListener('click', (e) => {
  e.preventDefault();
  window.api.openExternal('https://github.com/JNX03/win-computer-use');
});

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])
  );
}
