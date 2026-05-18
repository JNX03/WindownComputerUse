const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('api', {
  readConfig: () => ipcRenderer.invoke('config:read'),
  writeConfig: (patch) => ipcRenderer.invoke('config:write', patch),
  readState: () => ipcRenderer.invoke('state:read'),
  tailActivity: (fromOffset) => ipcRenderer.invoke('activity:tail', fromOffset),
  getAutoLaunch: () => ipcRenderer.invoke('autolaunch:get'),
  setAutoLaunch: (enabled) => ipcRenderer.invoke('autolaunch:set', enabled),
  openConfigFolder: () => ipcRenderer.invoke('shell:openConfigFolder'),
  openExternal: (url) => ipcRenderer.invoke('shell:openExternal', url),
  setEmergencyStop: (on) => ipcRenderer.invoke('emergencyStop:set', on),
});
