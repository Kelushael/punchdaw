import { useState, useRef, useCallback } from 'react';
import VoiceMemoPanel from './components/VoiceMemoPanel';
import TerminalPanel from './components/TerminalPanel';

function App() {
  const [splitRatio, setSplitRatio] = useState(48);
  const containerRef = useRef<HTMLDivElement>(null);
  const isDragging = useRef(false);

  const handleMouseDown = useCallback(() => {
    isDragging.current = true;
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
  }, []);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!isDragging.current || !containerRef.current) return;
    const rect = containerRef.current.getBoundingClientRect();
    const pct = ((e.clientX - rect.left) / rect.width) * 100;
    setSplitRatio(Math.max(25, Math.min(75, pct)));
  }, []);

  const handleMouseUp = useCallback(() => {
    isDragging.current = false;
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
  }, []);

  return (
    <div
      ref={containerRef}
      className="h-screen w-screen flex overflow-hidden bg-black"
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
    >
      <div style={{ width: `${splitRatio}%`, minWidth: 300 }} className="h-full flex-shrink-0">
        <TerminalPanel />
      </div>

      <div
        onMouseDown={handleMouseDown}
        className="w-1 cursor-col-resize bg-forge-line hover:bg-forge-accent flex-shrink-0 transition-colors"
      />

      <div style={{ width: `${100 - splitRatio}%`, minWidth: 400 }} className="h-full flex-shrink-0">
        <VoiceMemoPanel />
      </div>
    </div>
  );
}

export default App;
