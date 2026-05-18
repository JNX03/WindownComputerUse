# Win:Computer Use — Electron Manager

Dev run:

```powershell
cd electron-manager
npm install
npm start
```

The manager reads/writes `%USERPROFILE%\.win_computer_use\config.json` and tails `activity.log`. It uses file-based IPC — no HTTP, no native ports.

Inside the app:
- **Status** — server heartbeat, bypass state, agent name, and a big EMERGENCY STOP.
- **Permissions** — edit `allowed_apps` / `blocked_apps`; bypass toggle with a confirmation.
- **Cursor & Agent** — agent name, ring color, overlay on/off, motion speed slider, showcase mode, **auto-launch with Windows** toggle.
- **Activity** — live tail of every MCP tool call (`tool`, args, OK/fail, elapsed ms).

Auto-launch uses `app.setLoginItemSettings({ openAtLogin: true, args: ['--hidden'] })`. On startup the window stays hidden and only the tray icon appears.
