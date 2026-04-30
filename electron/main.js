const { app, BrowserWindow, ipcMain, session, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');

const WORKBENCH_DIR = path.join(__dirname, '..');
const BACKEND_DIR = path.join(WORKBENCH_DIR, 'backend');
const CLIPS_DIR = path.join(WORKBENCH_DIR, 'clips');
const AGENT_SCRIPT = path.join(BACKEND_DIR, 'agent.py');

// ── Bundled binary resolver ──
// In production .app bundles, binaries live in Resources/bin/<platform>/
function getBinary(name) {
  const bundled = path.join(process.resourcesPath, 'bin', os.platform(), name);
  if (fs.existsSync(bundled)) return bundled;
  return name; // fallback to PATH
}

let mainWindow = null;
let pythonProcess = null;
let stdoutBuffer = '';
let recordProcess = null;
let levelProcess = null;
let monitorModuleId = null;
let currentTakePath = '';
let takeCounter = 0;

// PulseAudio needs XDG_RUNTIME_DIR to find the server socket.
// When Electron is launched from an SSH session (su - marcus) this is
// often missing.  We inject the standard systemd user-runtime path.
const PULSE_ENV = {
  ...process.env,
  XDG_RUNTIME_DIR: process.env.XDG_RUNTIME_DIR || '/run/user/1000',
};

function ensureDirs() {
  if (!fs.existsSync(CLIPS_DIR)) fs.mkdirSync(CLIPS_DIR, { recursive: true });
}

function getNextTakeName() {
  takeCounter++;
  return `Take ${takeCounter}`;
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1680,
    height: 980,
    minWidth: 1100,
    minHeight: 700,
    title: 'NeonForge Voice',
    backgroundColor: '#0a0a08',
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      preload: path.join(__dirname, 'preload.js'),
    },
  });

  if (process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function flushLines(text) {
  if (!mainWindow || mainWindow.isDestroyed()) return;
  const lines = text.split('\n');
  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === '') continue;
    if (trimmed === '{"_done":true}') {
      mainWindow.webContents.send('turn-done');
    } else {
      mainWindow.webContents.send('terminal-output', line + '\n');
    }
  }
}

function startAgent() {
  pythonProcess = spawn('python3', [AGENT_SCRIPT], {
    cwd: WORKBENCH_DIR,
    stdio: ['pipe', 'pipe', 'pipe'],
    env: { ...process.env, PYTHONUNBUFFERED: '1' },
  });

  pythonProcess.stdout.on('data', (data) => {
    stdoutBuffer += data.toString();
    let idx;
    while ((idx = stdoutBuffer.indexOf('\n')) !== -1) {
      const line = stdoutBuffer.slice(0, idx + 1);
      stdoutBuffer = stdoutBuffer.slice(idx + 1);
      flushLines(line);
    }
  });

  pythonProcess.stderr.on('data', (data) => {
    const text = data.toString();
    console.error('[Agent stderr]', text);
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('terminal-output', '\x1b[31m' + text + '\x1b[0m');
    }
  });

  pythonProcess.on('exit', (code) => {
    console.log(`[Agent] exited with code ${code}`);
    pythonProcess = null;
  });

  pythonProcess.on('error', (err) => {
    console.error('[Agent] failed to start:', err);
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('terminal-output', '\r\n\x1b[31mAgent failed to start.\x1b[0m\r\n');
      mainWindow.webContents.send('turn-done');
    }
  });
}

function sendToAgent(text) {
  if (pythonProcess && pythonProcess.stdin.writable) {
    pythonProcess.stdin.write(text + '\n');
  }
}

// ── Cross-Platform Audio Engine ──
//
//  Linux:   PulseAudio (parec) — PreSonus held by PA, direct ALSA fails
//  macOS:   CoreAudio via ffmpeg avfoundation
//  Windows: DirectSound via ffmpeg dshow (future)
//
const IS_MAC = process.platform === 'darwin';
const IS_LINUX = process.platform === 'linux';

function getRecorderArgs(outputPath) {
  if (IS_MAC) {
    return {
      cmd: getBinary('ffmpeg'),
      args: ['-y', '-f', 'avfoundation', '-i', ':0',
             '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2', outputPath],
    };
  }
  // Linux default — PulseAudio parec
  return {
    cmd: getBinary('parec'),
    args: ['--rate=44100', '--channels=2', '--format=s16le', '--file-format=wav', outputPath],
    env: PULSE_ENV,
  };
}

function getLevelMonitorArgs() {
  if (IS_MAC) {
    return {
      cmd: getBinary('ffmpeg'),
      args: ['-f', 'avfoundation', '-i', ':0',
             '-acodec', 'pcm_s16le', '-ar', '44100', '-ac', '2',
             '-f', 's16le', 'pipe:1'],
    };
  }
  // Linux
  return {
    cmd: getBinary('parec'),
    args: ['--rate=44100', '--channels=2', '--format=s16le', '--raw'],
    env: PULSE_ENV,
  };
}

function startRecording() {
  if (recordProcess) {
    console.log('[Recorder] Already recording');
    return;
  }

  const ts = Date.now();
  const filename = `take-${ts}.wav`;
  currentTakePath = path.join(CLIPS_DIR, filename);

  // ── Recorder ──
  const rec = getRecorderArgs(currentTakePath);
  recordProcess = spawn(rec.cmd, rec.args, {
    cwd: WORKBENCH_DIR,
    env: rec.env || process.env,
  });

  // ── Level meter ──
  const lvl = getLevelMonitorArgs();
  levelProcess = spawn(lvl.cmd, lvl.args, {
    cwd: WORKBENCH_DIR,
    env: lvl.env || process.env,
  });

  let levelBuffer = Buffer.alloc(0);
  levelProcess.stdout.on('data', (chunk) => {
    levelBuffer = Buffer.concat([levelBuffer, chunk]);
    const frameBytes = 4; // s16le stereo
    while (levelBuffer.length >= frameBytes * 256) {
      const slice = levelBuffer.slice(0, frameBytes * 256);
      levelBuffer = levelBuffer.slice(frameBytes * 256);
      let sum = 0;
      for (let i = 0; i < slice.length; i += 2) {
        const sample = slice.readInt16LE(i);
        sum += sample * sample;
      }
      const rms = Math.sqrt(sum / (slice.length / 2));
      const normalized = Math.min(1, rms / 32768);
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('audio-level', normalized);
      }
    }
  });

  levelProcess.on('exit', () => { levelProcess = null; });
  levelProcess.on('error', (err) => {
    console.error('[level]', err);
    levelProcess = null;
  });

  // ── Monitor: PulseAudio loopback (Linux only) ──
  if (IS_LINUX) {
    const pactl = spawn('pactl', [
      'load-module', 'module-loopback', 'latency_msec=1',
    ], {
      cwd: WORKBENCH_DIR,
      env: PULSE_ENV,
    });
    pactl.stdout.on('data', (data) => {
      const id = data.toString().trim();
      if (id && !isNaN(parseInt(id))) {
        monitorModuleId = parseInt(id);
        console.log(`[Monitor] loopback module ${monitorModuleId} loaded`);
      }
    });
    pactl.stderr.on('data', (data) => {
      console.error('[pactl]', data.toString());
    });
  }

  recordProcess.stderr.on('data', (data) => {
    const text = data.toString();
    if (text.includes('error') || text.includes('Error') || text.includes('Failed')) {
      console.error('[recorder]', text);
    }
  });

  recordProcess.on('exit', (code, signal) => {
    recordProcess = null;
    if (levelProcess) { levelProcess.kill('SIGTERM'); levelProcess = null; }
    const ok = code === 0 || code === null || signal === 'SIGTERM' || signal === 'SIGINT';
    if (ok && fs.existsSync(currentTakePath)) {
      const ffprobe = spawn(getBinary('ffprobe'), [
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        currentTakePath,
      ]);
      let duration = '00:00:00';
      let durationSeconds = 0;
      ffprobe.stdout.on('data', (d) => {
        const sec = parseFloat(d.toString().trim());
        if (!isNaN(sec)) {
          durationSeconds = sec;
          const m = String(Math.floor(sec / 60)).padStart(2, '0');
          const s = String(Math.floor(sec % 60)).padStart(2, '0');
          duration = `00:${m}:${s}`;
        }
      });
      ffprobe.on('close', () => {
        if (mainWindow && !mainWindow.isDestroyed()) {
          mainWindow.webContents.send('recorder:done', {
            path: currentTakePath,
            name: getNextTakeName(),
            duration,
            durationSeconds,
            url: `file://${currentTakePath}`,
          });
        }
      });
    } else {
      console.error(`[recorder] exited code=${code} signal=${signal}`);
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('recorder:error', `recorder exited code=${code} signal=${signal}`);
      }
    }
  });

  recordProcess.on('error', (err) => {
    console.error('[recorder] spawn error:', err);
    recordProcess = null;
    if (levelProcess) { levelProcess.kill('SIGTERM'); levelProcess = null; }
    stopMonitor();
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.send('recorder:error', err.message);
    }
  });
}

function stopMonitor() {
  if (!IS_LINUX) return;
  if (monitorModuleId !== null) {
    spawn('pactl', ['unload-module', String(monitorModuleId)], {
      cwd: WORKBENCH_DIR,
      env: PULSE_ENV,
    });
    console.log(`[Monitor] loopback module ${monitorModuleId} unloaded`);
    monitorModuleId = null;
  }
}

function stopRecording() {
  if (!recordProcess) return;
  recordProcess.kill(IS_MAC ? 'SIGTERM' : 'SIGINT');
  if (levelProcess) { levelProcess.kill('SIGTERM'); levelProcess = null; }
  stopMonitor();
  setTimeout(() => {
    if (recordProcess) recordProcess.kill('SIGTERM');
  }, 800);
}

app.whenReady().then(() => {
  ensureDirs();

  // Auto-approve permissions
  session.defaultSession.setPermissionRequestHandler((webContents, permission, callback) => {
    callback(true);
  });
  session.defaultSession.setPermissionCheckHandler(() => true);

  createWindow();

  if (mainWindow) {
    mainWindow.webContents.on('did-finish-load', () => {
      if (!pythonProcess) startAgent();
    });
  }

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

// Terminal IPC
ipcMain.on('chat-input', (event, text) => {
  sendToAgent(text);
});

ipcMain.on('chat-interrupt', () => {
  if (pythonProcess) {
    pythonProcess.kill('SIGINT');
    setTimeout(() => {
      if (!pythonProcess) startAgent();
    }, 500);
  }
});

// Recording IPC
ipcMain.on('recorder:start', () => {
  startRecording();
});

ipcMain.on('recorder:stop', () => {
  stopRecording();
});

// Beat loading IPC
ipcMain.handle('open-audio-file', async () => {
  if (!mainWindow || mainWindow.isDestroyed()) return null;
  const result = await dialog.showOpenDialog(mainWindow, {
    properties: ['openFile'],
    filters: [
      { name: 'Audio', extensions: ['wav', 'mp3', 'ogg', 'flac', 'm4a', 'aac', 'aiff', 'wma'] },
    ],
  });
  if (!result.canceled && result.filePaths.length > 0) {
    return result.filePaths[0];
  }
  return null;
});

app.on('window-all-closed', () => {
  if (recordProcess) recordProcess.kill('SIGTERM');
  stopMonitor();
  if (pythonProcess) pythonProcess.kill('SIGTERM');
  app.quit();
});
