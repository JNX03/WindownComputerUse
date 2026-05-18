const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  // Config + state
  readConfig: () => ipcRenderer.invoke('config:read'),
  writeConfig: (patch) => ipcRenderer.invoke('config:write', patch),
  readState: () => ipcRenderer.invoke('state:read'),
  tailActivity: (fromOffset) => ipcRenderer.invoke('activity:tail', fromOffset),

  // Auto-launch
  getAutoLaunch: () => ipcRenderer.invoke('autolaunch:get'),
  setAutoLaunch: (enabled) => ipcRenderer.invoke('autolaunch:set', enabled),

  // Shell / clipboard
  openConfigFolder: () => ipcRenderer.invoke('shell:openConfigFolder'),
  openExternal: (url) => ipcRenderer.invoke('shell:openExternal', url),
  setEmergencyStop: (on) => ipcRenderer.invoke('emergencyStop:set', on),

  // Setup wizard
  setupPaths: () => ipcRenderer.invoke('setup:paths'),
  setupDetectPython: () => ipcRenderer.invoke('setup:detectPython'),
  setupDetectDeps: (pythonExe) => ipcRenderer.invoke('setup:detectDeps', pythonExe),
  setupInstallDeps: (pythonExe) => ipcRenderer.invoke('setup:installDeps', pythonExe),
  setupDetectClaudeCli: () => ipcRenderer.invoke('setup:detectClaudeCli'),
  setupRegisterClaudeCode: (pythonExe) => ipcRenderer.invoke('setup:registerClaudeCode', pythonExe),
  setupLaunchOverlay: (pythonExe) => ipcRenderer.invoke('setup:launchOverlay', pythonExe),
  setupWriteFile: (filePath, content) => ipcRenderer.invoke('setup:writeFile', filePath, content),
  setupPathExists: (p) => ipcRenderer.invoke('setup:pathExists', p),
  setupCopyToClipboard: (text) => ipcRenderer.invoke('setup:copyToClipboard', text),

  // Setup install log stream
  onSetupInstallLog: (callback) => {
    const fn = (_e, line) => callback(line);
    ipcRenderer.on('setup:installLog', fn);
    return () => ipcRenderer.removeListener('setup:installLog', fn);
  },
});
