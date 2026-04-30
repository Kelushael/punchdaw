import { useState, useRef, useEffect, useCallback } from 'react';

export interface Take {
  id: number;
  name: string;
  duration: string;
  durationSeconds: number;
  path: string;
  url: string;
  createdAt: number;
  offset: number; // seconds from project start when recording began
}

export function useAudioRecorder() {
  const [isRecording, setIsRecording] = useState(false);
  const [seconds, setSeconds] = useState(0);
  const [takes, setTakes] = useState<Take[]>([]);

  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startTimeRef = useRef<number>(0);
  const pendingOffsetRef = useRef<number>(0);

  useEffect(() => {
    if (!window.electronAPI) return;

    const removeDone = window.electronAPI.onRecordingDone((data) => {
      setTakes(prev => [{
        id: Date.now(),
        name: data.name,
        duration: data.duration,
        durationSeconds: data.durationSeconds || 0,
        path: data.path,
        url: data.url,
        createdAt: Date.now(),
        offset: pendingOffsetRef.current,
      }, ...prev]);
      setIsRecording(false);
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setSeconds(0);
      pendingOffsetRef.current = 0;
    });

    const removeError = window.electronAPI.onRecordingError((msg) => {
      console.error('[Recorder]', msg);
      setIsRecording(false);
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      setSeconds(0);
      pendingOffsetRef.current = 0;
    });

    return () => {
      removeDone?.();
      removeError?.();
    };
  }, []);

  const setRecordingOffset = useCallback((offset: number) => {
    pendingOffsetRef.current = offset;
  }, []);

  const startRecording = useCallback(() => {
    if (!window.electronAPI) {
      alert('Electron API not available');
      return;
    }
    window.electronAPI.startRecording();
    setIsRecording(true);
    startTimeRef.current = Date.now();
    setSeconds(0);

    timerRef.current = setInterval(() => {
      setSeconds(s => s + 1);
    }, 1000);
  }, []);

  const stopRecording = useCallback(() => {
    if (!window.electronAPI) return;
    window.electronAPI.stopRecording();
    // Don't clear timer here — wait for IPC callback
  }, []);

  const deleteTake = useCallback((id: number) => {
    setTakes(prev => prev.filter(t => t.id !== id));
  }, []);

  const formatTime = (totalSeconds: number) => {
    const m = String(Math.floor(totalSeconds / 60)).padStart(2, '0');
    const s = String(totalSeconds % 60).padStart(2, '0');
    return `00:${m}:${s}`;
  };

  return {
    isRecording,
    seconds,
    formattedTime: formatTime(seconds),
    takes,
    startRecording,
    stopRecording,
    deleteTake,
    setRecordingOffset,
  };
}
