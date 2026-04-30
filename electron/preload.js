const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // Terminal
  sendChat: (text) => ipcRenderer.send('chat-input', text),
  sendInterrupt: () => ipcRenderer.send('chat-interrupt'),
  onTerminalOutput: (cb) => ipcRenderer.on('terminal-output', (e, text) => cb(text)),
  onTurnDone: (cb) => ipcRenderer.on('turn-done', () => cb()),

  // Recording
  startRecording: () => ipcRenderer.send('recorder:start'),
  stopRecording: () => ipcRenderer.send('recorder:stop'),
  onRecordingDone: (cb) => ipcRenderer.on('recorder:done', (e, data) => cb(data)),
  onRecordingError: (cb) => ipcRenderer.on('recorder:error', (e, msg) => cb(msg)),
  onAudioLevel: (cb) => ipcRenderer.on('audio-level', (e, level) => cb(level)),

  // Beat loading
  openAudioFile: () => ipcRenderer.invoke('open-audio-file'),
  getFilePath: (file) => webUtils.getPathForFile(file),
});
