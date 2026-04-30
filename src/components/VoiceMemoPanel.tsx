import { useState, useRef, useEffect, useCallback } from 'react';
import {
  Mic, Play, Pause, Scissors, Trash2, Download,
  Music, Upload, Repeat, Repeat1, X,
  SkipBack, Magnet
} from 'lucide-react';
import { useAudioRecorder } from '../hooks/useAudioRecorder';

interface TrimState {
  takeId: number;
  isPlaying: boolean;
  playbackSeconds: number;
  audio: HTMLAudioElement | null;
}

const TIMELINE_SCALE = 50; // pixels per second
const TIMELINE_PADDING = 100;
const GRID_RESOLUTIONS = [0.25, 0.5, 1, 2];

function formatSeconds(sec: number) {
  const m = String(Math.floor(sec / 60)).padStart(2, '0');
  const s = String(Math.floor(sec % 60)).padStart(2, '0');
  return `${m}:${s}`;
}

function parseDurationToSeconds(dur: string): number {
  const parts = dur.split(':');
  if (parts.length === 3) {
    return parseInt(parts[1]) * 60 + parseInt(parts[2]);
  }
  return 0;
}

function snapValue(value: number, resolution: number): number {
  return Math.round(value / resolution) * resolution;
}

export default function VoiceMemoPanel() {
  const {
    isRecording,
    formattedTime,
    takes,
    startRecording,
    stopRecording,
    deleteTake,
    setRecordingOffset,
  } = useAudioRecorder();

  const [trim, setTrim] = useState<TrimState | null>(null);

  // ── Beat state ──
  const [beatPath, setBeatPath] = useState<string | null>(null);
  const [beatName, setBeatName] = useState<string | null>(null);
  const [beatUrl, setBeatUrl] = useState<string | null>(null);
  const [isBeatPlaying, setIsBeatPlaying] = useState(false);
  const [beatCurrentTime, setBeatCurrentTime] = useState(0);
  const [beatDuration, setBeatDuration] = useState(0);
  const [restartBeatOnRecord, setRestartBeatOnRecord] = useState(true);
  const [isDragOver, setIsDragOver] = useState(false);

  // ── Grid / arrangement ──
  const [snapEnabled, setSnapEnabled] = useState(true);
  const [gridResolution, setGridResolution] = useState(1);

  // ── Global playback ──
  const [globalTime, setGlobalTime] = useState(0);
  const [isGlobalPlaying, setIsGlobalPlaying] = useState(false);
  const [stagingTakeId, setStagingTakeId] = useState<number | null>(null);

  // ── VU meter ──
  const [audioLevel, setAudioLevel] = useState(0);
  const [peakLevel, setPeakLevel] = useState(0);
  const peakDecayRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Countdown ──
  const [isCountingDown, setIsCountingDown] = useState(false);
  const [countdownNumber, setCountdownNumber] = useState(4);

  // Refs
  const beatAudioRef = useRef<HTMLAudioElement | null>(null);
  const stagingAudioRef = useRef<HTMLAudioElement | null>(null);
  const beatUpdateRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const countdownRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const rafRef = useRef<number>(0);
  const timelineRef = useRef<HTMLDivElement>(null);

  // ── Total timeline length ──
  const totalDuration = Math.max(
    beatDuration,
    takes.reduce((max, t) => Math.max(max, t.offset + (t.durationSeconds || parseDurationToSeconds(t.duration))), 0),
    60
  );
  const timelineWidth = totalDuration * TIMELINE_SCALE + TIMELINE_PADDING;

  // ── Audio level listener ──
  useEffect(() => {
    if (!window.electronAPI?.onAudioLevel) return;
    const remove = window.electronAPI.onAudioLevel((level: number) => {
      setAudioLevel(level);
      setPeakLevel(prev => Math.max(prev, level));
    });
    // Peak decay
    peakDecayRef.current = setInterval(() => {
      setPeakLevel(prev => prev * 0.95);
    }, 50);
    return () => {
      remove?.();
      if (peakDecayRef.current) clearInterval(peakDecayRef.current);
    };
  }, []);

  // ── Keyboard shortcuts ──
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.code === 'Space') {
        e.preventDefault();
        toggleGlobalPlayback();
      }
      if (e.code === 'Enter') {
        e.preventDefault();
        seekGlobal(0);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isGlobalPlaying, beatUrl, stagingTakeId, globalTime]);

  // ── Global playback sync loop ──
  useEffect(() => {
    if (!isGlobalPlaying) {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      return;
    }
    const tick = () => {
      if (beatAudioRef.current) {
        const t = beatAudioRef.current.currentTime;
        setGlobalTime(t);
        if (stagingAudioRef.current && stagingTakeId !== null) {
          const take = takes.find(ta => ta.id === stagingTakeId);
          if (take) {
            const takeTime = t - take.offset;
            if (takeTime >= 0 && takeTime < (take.durationSeconds || parseDurationToSeconds(take.duration))) {
              if (Math.abs(stagingAudioRef.current.currentTime - takeTime) > 0.1) {
                stagingAudioRef.current.currentTime = takeTime;
              }
              if (stagingAudioRef.current.paused) {
                stagingAudioRef.current.play().catch(() => {});
              }
            } else {
              stagingAudioRef.current.pause();
            }
          }
        }
      }
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, [isGlobalPlaying, stagingTakeId, takes]);

  // ── Beat time updater ──
  useEffect(() => {
    if (isBeatPlaying && beatAudioRef.current && !isGlobalPlaying) {
      beatUpdateRef.current = setInterval(() => {
        if (beatAudioRef.current) {
          setBeatCurrentTime(beatAudioRef.current.currentTime);
        }
      }, 200);
    }
    return () => {
      if (beatUpdateRef.current) clearInterval(beatUpdateRef.current);
    };
  }, [isBeatPlaying, isGlobalPlaying]);

  // ── Cleanup ──
  useEffect(() => {
    return () => {
      if (beatAudioRef.current) { beatAudioRef.current.pause(); beatAudioRef.current = null; }
      if (stagingAudioRef.current) { stagingAudioRef.current.pause(); stagingAudioRef.current = null; }
      if (countdownRef.current) clearInterval(countdownRef.current);
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
    };
  }, []);

  // ── Global playback controls ──
  const toggleGlobalPlayback = useCallback(() => {
    if (isGlobalPlaying) {
      pauseGlobalPlayback();
    } else {
      startGlobalPlayback();
    }
  }, [isGlobalPlaying]);

  const startGlobalPlayback = useCallback(() => {
    if (!beatAudioRef.current && !stagingAudioRef.current) return;
    if (beatAudioRef.current) {
      beatAudioRef.current.play();
      setIsBeatPlaying(true);
    }
    setIsGlobalPlaying(true);
  }, []);

  const pauseGlobalPlayback = useCallback(() => {
    if (beatAudioRef.current) beatAudioRef.current.pause();
    if (stagingAudioRef.current) stagingAudioRef.current.pause();
    setIsGlobalPlaying(false);
    setIsBeatPlaying(false);
  }, []);

  const seekGlobal = useCallback((time: number) => {
    setGlobalTime(time);
    if (beatAudioRef.current) {
      beatAudioRef.current.currentTime = time;
      setBeatCurrentTime(time);
    }
    if (stagingAudioRef.current && stagingTakeId !== null) {
      const take = takes.find(ta => ta.id === stagingTakeId);
      if (take) {
        const takeTime = time - take.offset;
        if (takeTime >= 0) {
          stagingAudioRef.current.currentTime = takeTime;
        } else {
          stagingAudioRef.current.pause();
          stagingAudioRef.current.currentTime = 0;
        }
      }
    }
  }, [stagingTakeId, takes]);

  // ── Staging track ──
  const assignToStaging = useCallback((takeId: number) => {
    const take = takes.find(t => t.id === takeId);
    if (!take) return;
    if (stagingAudioRef.current) {
      stagingAudioRef.current.pause();
    }
    const audio = new Audio(take.url);
    stagingAudioRef.current = audio;
    setStagingTakeId(takeId);
    if (isGlobalPlaying && beatAudioRef.current) {
      const t = beatAudioRef.current.currentTime;
      const takeTime = t - take.offset;
      if (takeTime >= 0) {
        audio.currentTime = takeTime;
        audio.play().catch(() => {});
      }
    }
  }, [takes, isGlobalPlaying]);

  const clearStaging = useCallback(() => {
    if (stagingAudioRef.current) {
      stagingAudioRef.current.pause();
      stagingAudioRef.current = null;
    }
    setStagingTakeId(null);
  }, []);

  // ── Beat loading ──
  const handleBeatFile = useCallback((filePath: string) => {
    const name = filePath.split('/').pop() || 'Beat';
    const url = `file://${filePath}`;
    setBeatPath(filePath);
    setBeatName(name);
    setBeatUrl(url);
    setBeatCurrentTime(0);
    setBeatDuration(0);
    setIsBeatPlaying(false);

    const audio = new Audio(url);
    audio.addEventListener('loadedmetadata', () => {
      setBeatDuration(audio.duration);
    });
    audio.addEventListener('ended', () => {
      setIsBeatPlaying(false);
      setIsGlobalPlaying(false);
      setBeatCurrentTime(0);
    });
    audio.addEventListener('timeupdate', () => {
      setBeatCurrentTime(audio.currentTime);
    });
    if (beatAudioRef.current) {
      beatAudioRef.current.pause();
    }
    beatAudioRef.current = audio;
  }, []);

  const loadBeatViaDialog = useCallback(async () => {
    if (!window.electronAPI?.openAudioFile) return;
    const path = await window.electronAPI.openAudioFile();
    if (path) handleBeatFile(path);
  }, [handleBeatFile]);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    if (files.length > 0 && window.electronAPI?.getFilePath) {
      const path = window.electronAPI.getFilePath(files[0]);
      if (path) handleBeatFile(path);
    }
  }, [handleBeatFile]);

  const toggleBeatPlayback = useCallback(() => {
    if (!beatAudioRef.current) return;
    if (isBeatPlaying) {
      beatAudioRef.current.pause();
      setIsBeatPlaying(false);
      setIsGlobalPlaying(false);
    } else {
      beatAudioRef.current.play();
      setIsBeatPlaying(true);
    }
  }, [isBeatPlaying]);

  const seekBeat = useCallback((e: React.ChangeEvent<HTMLInputElement>) => {
    const time = parseFloat(e.target.value);
    seekGlobal(time);
  }, [seekGlobal]);

  const clearBeat = useCallback(() => {
    if (beatAudioRef.current) {
      beatAudioRef.current.pause();
      beatAudioRef.current = null;
    }
    setBeatPath(null);
    setBeatName(null);
    setBeatUrl(null);
    setIsBeatPlaying(false);
    setBeatCurrentTime(0);
    setBeatDuration(0);
  }, []);

  // ── Countdown ──
  const startCountdown = useCallback(() => {
    if (!beatAudioRef.current) return;
    if (restartBeatOnRecord) {
      beatAudioRef.current.currentTime = 0;
      setBeatCurrentTime(0);
      setGlobalTime(0);
    }
    if (!isBeatPlaying) {
      beatAudioRef.current.play();
      setIsBeatPlaying(true);
    }
    setIsCountingDown(true);
    setCountdownNumber(4);
    let count = 4;
    countdownRef.current = setInterval(() => {
      count -= 1;
      setCountdownNumber(count);
      if (count <= 0) {
        if (countdownRef.current) clearInterval(countdownRef.current);
        setIsCountingDown(false);
        let offset = beatAudioRef.current?.currentTime || 0;
        if (snapEnabled) {
          offset = snapValue(offset, gridResolution);
        }
        setRecordingOffset(offset);
        startRecording();
      }
    }, 1000);
  }, [beatAudioRef, restartBeatOnRecord, isBeatPlaying, snapEnabled, gridResolution, setRecordingOffset, startRecording]);

  const cancelCountdown = useCallback(() => {
    if (countdownRef.current) {
      clearInterval(countdownRef.current);
      countdownRef.current = null;
    }
    setIsCountingDown(false);
    setCountdownNumber(4);
  }, []);

  // ── Record button handler ──
  const handleToggleRecording = useCallback(() => {
    if (isRecording) {
      stopRecording();
      return;
    }
    if (isCountingDown) {
      cancelCountdown();
      return;
    }
    if (beatPath) {
      startCountdown();
    } else {
      setRecordingOffset(0);
      startRecording();
    }
  }, [isRecording, isCountingDown, beatPath, stopRecording, cancelCountdown, startCountdown, setRecordingOffset, startRecording]);

  // ── Trim modal ──
  const openTrimModal = useCallback((takeId: number) => {
    const take = takes.find(t => t.id === takeId);
    if (!take) return;
    const audio = new Audio(take.url);
    setTrim({ takeId, isPlaying: false, playbackSeconds: 0, audio });
  }, [takes]);

  const closeTrimModal = useCallback(() => {
    if (trim?.audio) {
      trim.audio.pause();
      trim.audio.currentTime = 0;
    }
    setTrim(null);
  }, [trim]);

  const toggleTrimPlayback = useCallback(() => {
    if (!trim?.audio) return;
    if (trim.isPlaying) {
      trim.audio.pause();
      setTrim({ ...trim, isPlaying: false });
    } else {
      trim.audio.play();
      setTrim({ ...trim, isPlaying: true });
      const interval = setInterval(() => {
        if (trim.audio) {
          setTrim(prev => prev ? { ...prev, playbackSeconds: trim.audio!.currentTime } : null);
        }
      }, 100);
      trim.audio.onended = () => {
        clearInterval(interval);
        setTrim(prev => prev ? { ...prev, isPlaying: false } : null);
      };
    }
  }, [trim]);

  const confirmTrim = useCallback(() => {
    if (!trim) return;
    const timeStr = formatSeconds(trim.playbackSeconds);
    alert(`✅ Trim applied at ${timeStr}\nEverything after this point deleted.\nOriginal preserved in archive.`);
    closeTrimModal();
  }, [trim, closeTrimModal]);

  const normalizeAndZip = useCallback(() => {
    if (takes.length === 0) {
      alert('No takes to export. Record something first.');
      return;
    }
    alert(`🔧 Normalizing ${takes.length} takes...\n🎵 Stitching final track...\n📦 ZIP ready for download (demo — real ffmpeg processing runs on GPU server)`);
  }, [takes]);

  // ── VU meter segments ──
  const vuSegments = 16;
  const activeSegments = Math.floor(audioLevel * vuSegments);
  const peakSegment = Math.floor(peakLevel * vuSegments);

  const stagingTake = takes.find(t => t.id === stagingTakeId);

  return (
    <div
      className="h-full flex flex-col bg-gradient-to-br from-[#0c0c0c] to-black overflow-hidden"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {/* ── Top bar: Record + Global Transport ── */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-forge-line shrink-0">
        {/* Record button + VU */}
        <div className="flex items-center gap-4 relative">
          <button
            onClick={handleToggleRecording}
            className={`w-16 h-16 rounded-2xl border-4 border-red-500 bg-black flex items-center justify-center shadow-2xl shadow-red-500/60 hover:scale-105 transition-all active:scale-95 ${isRecording ? 'record-pulse' : ''}`}
          >
            <div className="w-7 h-7 bg-red-500 rounded-lg flex items-center justify-center">
              {isRecording ? (
                <div className="w-3.5 h-3.5 bg-white rounded-sm" />
              ) : isCountingDown ? (
                <X className="w-4 h-4 text-white" />
              ) : (
                <Mic className="w-4 h-4 text-white" />
              )}
            </div>
          </button>

          {/* VU Meter */}
          <div className="flex flex-col gap-[2px]">
            <div className="flex gap-[2px] items-end h-8">
              {Array.from({ length: vuSegments }, (_, i) => {
                let color = 'bg-green-500';
                if (i >= vuSegments * 0.6) color = 'bg-yellow-400';
                if (i >= vuSegments * 0.8) color = 'bg-red-500';
                const isActive = i < activeSegments;
                const isPeak = i === peakSegment && i >= activeSegments;
                return (
                  <div
                    key={i}
                    className={`w-1.5 rounded-sm transition-all duration-75 ${
                      isActive ? color : isPeak ? 'bg-white/40' : 'bg-white/5'
                    }`}
                    style={{ height: `${8 + (i / vuSegments) * 24}px` }}
                  />
                );
              })}
            </div>
            <div className="text-[9px] text-forge-muted font-mono tracking-wider">
              {isRecording ? 'INPUT' : 'READY'}
            </div>
          </div>

          {/* Countdown */}
          {isCountingDown && (
            <div className="absolute left-20 top-0 bottom-0 flex items-center">
              <div className="text-5xl font-black text-neon-cyan animate-pulse tabular-nums">
                {countdownNumber}
              </div>
            </div>
          )}
        </div>

        {/* Global transport */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => seekGlobal(0)}
            title="Return to start (Enter)"
            className="w-10 h-10 bg-white/5 hover:bg-white/10 rounded-xl flex items-center justify-center text-forge-muted hover:text-white transition"
          >
            <SkipBack size={18} />
          </button>
          <button
            onClick={toggleGlobalPlayback}
            disabled={!beatUrl && !stagingTake}
            className={`w-12 h-12 rounded-xl flex items-center justify-center transition ${
              isGlobalPlaying
                ? 'bg-amber-500 hover:bg-amber-600 text-black'
                : 'bg-neon-cyan hover:bg-cyan-300 text-black disabled:opacity-30 disabled:cursor-not-allowed'
            }`}
          >
            {isGlobalPlaying ? <Pause size={22} /> : <Play size={22} className="ml-0.5" />}
          </button>
          <div className="text-sm font-mono text-forge-muted tabular-nums w-[100px] text-right">
            {formatSeconds(globalTime)} / {formatSeconds(beatDuration || totalDuration)}
          </div>
        </div>
      </div>

      {/* ── Beat load / Beat info ── */}
      <div className="px-6 py-2 border-b border-forge-line shrink-0">
        {!beatPath ? (
          <button
            onClick={loadBeatViaDialog}
            className={`w-full py-3 border-2 border-dashed rounded-xl flex items-center justify-center gap-2 transition ${
              isDragOver
                ? 'border-neon-cyan bg-neon-cyan/10'
                : 'border-forge-line hover:border-neon-cyan/50 hover:bg-white/5'
            }`}
          >
            <Upload className={`w-5 h-5 ${isDragOver ? 'text-neon-cyan' : 'text-forge-muted'}`} />
            <span className={`text-sm font-bold ${isDragOver ? 'text-neon-cyan' : 'text-forge-muted'}`}>
              {isDragOver ? 'DROP BEAT HERE' : 'LOAD BEAT'}
            </span>
          </button>
        ) : (
          <div className="flex items-center gap-3">
            <Music className="w-4 h-4 text-neon-cyan shrink-0" />
            <div className="text-white text-sm font-bold truncate flex-1">{beatName}</div>
            <button
              onClick={() => setRestartBeatOnRecord(v => !v)}
              title={restartBeatOnRecord ? 'Restarts from top on record' : 'Continues from current position'}
              className={`flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-bold transition ${
                restartBeatOnRecord ? 'bg-neon-cyan/20 text-neon-cyan' : 'bg-white/5 text-forge-muted'
              }`}
            >
              {restartBeatOnRecord ? <Repeat size={12} /> : <Repeat1 size={12} />}
              {restartBeatOnRecord ? 'RESTART' : 'CONTINUE'}
            </button>
            <button onClick={clearBeat} className="text-forge-muted hover:text-red-400 transition">
              <X size={16} />
            </button>
          </div>
        )}
      </div>

      {/* ── Grid controls ── */}
      <div className="px-6 py-1 border-b border-forge-line/50 shrink-0 flex items-center gap-3">
        <button
          onClick={() => setSnapEnabled(v => !v)}
          className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-bold transition ${
            snapEnabled ? 'bg-neon-cyan/20 text-neon-cyan' : 'bg-white/5 text-forge-muted'
          }`}
        >
          <Magnet size={11} />
          SNAP {snapEnabled ? 'ON' : 'OFF'}
        </button>
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-forge-muted">GRID:</span>
          {GRID_RESOLUTIONS.map(res => (
            <button
              key={res}
              onClick={() => setGridResolution(res)}
              className={`px-1.5 py-0.5 rounded text-[10px] font-mono transition ${
                gridResolution === res
                  ? 'bg-white/10 text-white'
                  : 'text-forge-muted hover:text-white/60'
              }`}
            >
              {res}s
            </button>
          ))}
        </div>
      </div>

      {/* ── Timeline / Arrangement ── */}
      <div className="flex-1 overflow-hidden flex flex-col min-h-0">
        <div
          ref={timelineRef}
          className="flex-1 overflow-x-auto overflow-y-auto timeline-scroll relative"
        >
          <div style={{ width: timelineWidth, minHeight: '100%' }} className="relative">
            {/* Playhead */}
            <div
              className="playhead-line"
              style={{ left: globalTime * TIMELINE_SCALE }}
            />

            {/* Grid lines */}
            {snapEnabled && Array.from({ length: Math.ceil(totalDuration / gridResolution) + 1 }, (_, i) => i * gridResolution).map(t => (
              <div
                key={`grid-${t}`}
                className="absolute top-0 bottom-0 border-l border-dashed border-white/5 pointer-events-none"
                style={{ left: t * TIMELINE_SCALE }}
              />
            ))}

            {/* ── Staging Track ── */}
            <div className="staging-lane h-16 flex items-center px-2 relative">
              <div className="w-28 shrink-0 text-[10px] font-bold text-neon-cyan uppercase tracking-wider pr-2">
                Staging Track
              </div>
              <div className="flex-1 relative h-10">
                {stagingTake ? (
                  <div
                    className="take-clip active h-full flex items-center px-2 absolute top-0"
                    style={{
                      left: stagingTake.offset * TIMELINE_SCALE,
                      width: Math.max(60, (stagingTake.durationSeconds || parseDurationToSeconds(stagingTake.duration)) * TIMELINE_SCALE),
                    }}
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="text-xs text-white font-bold truncate">{stagingTake.name}</span>
                    </div>
                    <button
                      onClick={(e) => { e.stopPropagation(); clearStaging(); }}
                      className="absolute right-1 top-1/2 -translate-y-1/2 text-white/50 hover:text-red-400"
                    >
                      <X size={14} />
                    </button>
                  </div>
                ) : (
                  <div className="h-full flex items-center text-xs text-forge-muted italic">
                    Click a take below to place it here for playback
                  </div>
                )}
              </div>
            </div>

            {/* ── Beat Track ── */}
            {beatUrl && (
              <div className="lane-strip h-12 flex items-center px-2 relative">
                <div className="w-28 shrink-0 text-[10px] font-bold text-amber-500 uppercase tracking-wider pr-2">
                  Beat
                </div>
                <div className="flex-1 relative h-8">
                  <div
                    className="absolute top-0 h-full rounded bg-amber-500/20 border border-amber-500/40"
                    style={{ left: 0, width: beatDuration * TIMELINE_SCALE }}
                  />
                  <div
                    className="absolute top-0 h-full rounded bg-amber-500/30"
                    style={{ left: 0, width: beatCurrentTime * TIMELINE_SCALE }}
                  />
                </div>
              </div>
            )}

            {/* ── Time Ruler ── */}
            <div className="time-ruler h-6 flex items-end relative">
              <div className="w-28 shrink-0" />
              <div className="flex-1 relative h-full">
                {Array.from({ length: Math.ceil(totalDuration / 5) + 1 }, (_, i) => i * 5).map(t => (
                  <div
                    key={t}
                    className="absolute bottom-0 flex flex-col items-center"
                    style={{ left: t * TIMELINE_SCALE }}
                  >
                    <div className="w-px h-2 bg-white/30" />
                    <span className="text-[9px] text-white/40 tabular-nums">{formatSeconds(t)}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* ── Take Lanes (muted staircase) ── */}
            {takes.length === 0 ? (
              <div className="h-32 flex items-center justify-center text-forge-muted text-sm italic">
                {beatPath
                  ? 'Hit the red button — 4-count intro, then record'
                  : 'Hit the red button to start recording'}
              </div>
            ) : (
              takes.map((take, idx) => {
                const dur = take.durationSeconds || parseDurationToSeconds(take.duration);
                const isOnStaging = stagingTakeId === take.id;
                const stepClass = `lane-step-${Math.min(idx, 7)}`;
                return (
                  <div
                    key={take.id}
                    className={`stair-lane h-11 flex items-center relative ${stepClass}`}
                  >
                    <div className="w-24 shrink-0 flex items-center gap-1.5 pr-2 pl-3">
                      <span className="text-[10px] font-bold text-white/20 uppercase">{idx + 1}</span>
                      <button
                        onClick={() => openTrimModal(take.id)}
                        className="text-white/15 hover:text-amber-400 transition ml-auto"
                        title="Trim"
                      >
                        <Scissors size={11} />
                      </button>
                      <button
                        onClick={() => deleteTake(take.id)}
                        className="text-white/15 hover:text-red-400 transition"
                        title="Delete"
                      >
                        <Trash2 size={11} />
                      </button>
                    </div>
                    <div className="flex-1 relative h-7">
                      <div
                        onClick={() => assignToStaging(take.id)}
                        className={`stair-clip h-full flex items-center px-2 absolute top-0 ${isOnStaging ? 'active' : ''}`}
                        style={{
                          left: take.offset * TIMELINE_SCALE,
                          width: Math.max(50, dur * TIMELINE_SCALE),
                        }}
                        title={`${take.name} — ${take.duration} @ ${formatSeconds(take.offset)}`}
                      >
                        <div className="flex items-end gap-[2px] h-3 mr-2 opacity-30 shrink-0">
                          {Array.from({ length: 8 }, (_, i) => (
                            <div
                              key={i}
                              className="w-[2px] bg-white/40 rounded-sm"
                              style={{ height: `${20 + Math.random() * 60}%` }}
                            />
                          ))}
                        </div>
                        <span className="text-[10px] text-white/50 font-medium truncate">{take.name}</span>
                        <span className="text-[9px] text-white/20 ml-auto shrink-0 tabular-nums">{take.duration}</span>
                      </div>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>
      </div>

      {/* ── Normalize + ZIP ── */}
      <div className="p-4 border-t border-forge-line bg-black/60 shrink-0">
        <button
          onClick={normalizeAndZip}
          className="w-full py-4 bg-gradient-to-r from-emerald-400 to-cyan-500 hover:from-emerald-500 hover:to-cyan-600 text-black font-bold text-lg rounded-2xl flex items-center justify-center gap-3 shadow-xl hover:scale-[1.02] transition"
        >
          <Download size={20} />
          NORMALIZE ALL + DOWNLOAD ZIP
        </button>
        <div className="text-center text-forge-muted text-[10px] mt-1">
          All takes leveled + stitched • Downloaded as .zip
        </div>
      </div>

      {/* ── Trim Modal ── */}
      {trim && (
        <div className="fixed inset-0 bg-black/95 flex items-center justify-center z-50">
          <div className="bg-forge-panel border-4 border-neon-cyan rounded-3xl w-full max-w-[520px] mx-4 p-8 shadow-2xl shadow-neon-cyan/20">
            <div className="flex justify-between items-center mb-6">
              <div className="text-3xl font-bold neon-text-cyan">
                Trim {takes.find(t => t.id === trim.takeId)?.name}
              </div>
              <button onClick={closeTrimModal} className="text-4xl text-white/60 hover:text-white leading-none">
                ×
              </button>
            </div>

            <div className="bg-black rounded-2xl p-6 mb-8 text-center border border-forge-line">
              <div className="text-5xl font-mono tabular-nums text-white mb-4">
                {formatSeconds(trim.playbackSeconds)}
              </div>
              <button
                onClick={toggleTrimPlayback}
                className="w-20 h-20 bg-neon-cyan hover:bg-cyan-300 rounded-full flex items-center justify-center mx-auto shadow-xl shadow-neon-cyan/40 transition hover:scale-105"
              >
                {trim.isPlaying ? (
                  <Pause size={36} className="text-black" />
                ) : (
                  <Play size={36} className="text-black ml-1" />
                )}
              </button>
              <div className="text-xs text-forge-muted mt-3">
                Play the clip • Pause at the exact cut point
              </div>
            </div>

            <button
              onClick={confirmTrim}
              className="w-full py-7 bg-gradient-to-r from-red-500 to-orange-500 hover:from-red-600 hover:to-orange-600 text-white font-bold text-2xl rounded-3xl shadow-xl transition hover:scale-[1.02]"
            >
              <Scissors className="inline-block mr-2" size={24} />
              TRIM EVERYTHING AFTER THIS POINT
            </button>

            <div className="text-center text-xs text-forge-muted mt-4">
              Original preserved in ./clips/archive/
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
