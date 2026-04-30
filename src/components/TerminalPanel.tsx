import { useEffect, useRef } from 'react';
import { Terminal } from 'xterm';
import { FitAddon } from '@xterm/addon-fit';
import 'xterm/css/xterm.css';
import { Skull, Zap, Terminal as TerminalIcon } from 'lucide-react';

const QUICK_COMMANDS = [
  'agent: transcribe all takes and smart comp against the beat',
  'agent: normalize all takes to -3dB and render zip',
  'agent: detect flubs and rescue comp the best parts',
  'agent: generate a self-improving audio processing script',
  'agent: acquire latest whisper model with gpu support',
  'agent: do what thou wilt with all voice clips',
];

export default function TerminalPanel() {
  const terminalRef = useRef<HTMLDivElement>(null);
  const term = useRef<Terminal | null>(null);
  const fitAddon = useRef<FitAddon | null>(null);

  useEffect(() => {
    if (!terminalRef.current) return;

    term.current = new Terminal({
      cursorBlink: true,
      fontSize: 14,
      fontFamily: 'Consolas, "Liberation Mono", Menlo, monospace',
      theme: {
        background: '#0a0a08',
        foreground: '#00ff9f',
        cursor: '#ff00ff',
        selectionBackground: '#ff00ff44',
        black: '#0a0a08',
        red: '#e71d36',
        green: '#2ec4b6',
        yellow: '#ff9f1c',
        blue: '#3498db',
        magenta: '#ff00ff',
        cyan: '#00f7ff',
        white: '#f2ebd9',
        brightBlack: '#5a5448',
        brightRed: '#e71d36',
        brightGreen: '#2ec4b6',
        brightYellow: '#ff9f1c',
        brightBlue: '#3498db',
        brightMagenta: '#ff00ff',
        brightCyan: '#00f7ff',
        brightWhite: '#fff',
      },
      scrollback: 10000,
    });

    fitAddon.current = new FitAddon();
    term.current.loadAddon(fitAddon.current);
    term.current.open(terminalRef.current);
    fitAddon.current.fit();

    // Boot sequence
    term.current.writeln('\x1b[35m╔════════════════════════════════════════════════════════════╗\x1b[0m');
    term.current.writeln('\x1b[35m║  NEONFORGE AGENT v2.0  —  "Do what thou wilt"              ║\x1b[0m');
    term.current.writeln('\x1b[35m║  No weaknesses. Only acquisition. Only will.               ║\x1b[0m');
    term.current.writeln('\x1b[35m╚════════════════════════════════════════════════════════════╝\x1b[0m');
    term.current.writeln('');
    term.current.writeln('\x1b[36m[SYSTEM] GPU: 108.181.162.206  │  Gateway: 185.28.23.43\x1b[0m');
    term.current.writeln('\x1b[36m[SYSTEM] Whisper: ready  │  FFmpeg: ready  │  Ollama: ready\x1b[0m');
    term.current.writeln('\x1b[32m[READY] Type your will or click a quick command below\x1b[0m\r\n');

    // Input handler
    let currentLine = '';
    let history: string[] = [];
    let historyIndex = -1;

    term.current.onData((data) => {
      const code = data.charCodeAt(0);

      if (code === 13) { // Enter
        term.current?.writeln('');
        if (currentLine.trim()) {
          history.push(currentLine);
          historyIndex = history.length;
          window.electronAPI?.sendChat(currentLine);
        }
        currentLine = '';
        term.current?.write('\x1b[32mneonforge>\x1b[0m ');
      } else if (code === 127 || code === 8) { // Backspace
        if (currentLine.length > 0) {
          currentLine = currentLine.slice(0, -1);
          term.current?.write('\b \b');
        }
      } else if (code === 27) { // Escape sequences (arrows)
        if (data === '\x1b[A') { // Up
          if (historyIndex > 0) {
            historyIndex--;
            clearPromptLine();
            currentLine = history[historyIndex];
            term.current?.write(currentLine);
          }
        } else if (data === '\x1b[B') { // Down
          if (historyIndex < history.length - 1) {
            historyIndex++;
            clearPromptLine();
            currentLine = history[historyIndex];
            term.current?.write(currentLine);
          } else if (historyIndex === history.length - 1) {
            historyIndex = history.length;
            clearPromptLine();
            currentLine = '';
          }
        }
      } else if (code === 3) { // Ctrl+C
        term.current?.write('^C\r\n');
        currentLine = '';
        window.electronAPI?.sendInterrupt();
        term.current?.write('\x1b[32mneonforge>\x1b[0m ');
      } else if (code >= 32 && code !== 127) {
        currentLine += data;
        term.current?.write(data);
      }
    });

    function clearPromptLine() {
      term.current?.write('\r\x1b[K\x1b[32mneonforge>\x1b[0m ');
    }

    // Receive output from Python agent
    const removeOutput = window.electronAPI?.onTerminalOutput((text: string) => {
      term.current?.write(text.replace(/\n/g, '\r\n'));
    });

    const removeDone = window.electronAPI?.onTurnDone(() => {
      term.current?.write('\r\n\x1b[32mneonforge>\x1b[0m ');
    });

    term.current.write('\x1b[32mneonforge>\x1b[0m ');

    const handleResize = () => fitAddon.current?.fit();
    window.addEventListener('resize', handleResize);

    return () => {
      window.removeEventListener('resize', handleResize);
      removeOutput?.();
      removeDone?.();
      term.current?.dispose();
    };
  }, []);

  const sendCommand = (cmd: string) => {
    if (term.current) {
      term.current.write(cmd + '\r');
    }
  };

  return (
    <div className="h-full flex flex-col bg-forge-bg border-r border-forge-line">
      {/* Header */}
      <div className="px-5 py-4 border-b border-forge-line flex items-center justify-between bg-black/60">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-full bg-gradient-to-br from-neon-pink to-neon-green flex items-center justify-center">
            <Skull className="w-5 h-5 text-black" />
          </div>
          <div>
            <div className="text-neon-green font-bold text-lg tracking-wider">NEONFORGE</div>
            <div className="text-neon-pink text-[10px] -mt-0.5">GOD MODE • NO WEAKNESSES</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="px-2 py-0.5 bg-neon-pink/20 text-neon-pink text-[10px] rounded font-bold">AGENT</div>
          <div className="px-2 py-0.5 bg-neon-green/20 text-neon-green text-[10px] rounded font-bold">WILL</div>
        </div>
      </div>

      {/* Terminal */}
      <div ref={terminalRef} className="flex-1 p-3 overflow-hidden" />

      {/* Quick Commands */}
      <div className="p-4 border-t border-forge-line bg-black/80">
        <div className="text-[10px] text-forge-muted mb-2 flex items-center gap-1">
          <Zap size={10} /> QUICK WILL
        </div>
        <div className="flex flex-col gap-1.5 max-h-[120px] overflow-y-auto scrollbar-thin">
          {QUICK_COMMANDS.map((cmd, i) => (
            <button
              key={i}
              onClick={() => sendCommand(cmd)}
              className="text-left text-[10px] px-2 py-1 bg-forge-panel hover:bg-neon-green/10 border border-forge-line hover:border-neon-green/40 rounded text-neon-green transition truncate"
              title={cmd}
            >
              <TerminalIcon size={9} className="inline mr-1 opacity-50" />
              {cmd.replace('agent: ', '').slice(0, 50)}
              {cmd.length > 55 ? '...' : ''}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
