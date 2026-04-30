export interface TakeData {
  path: string;
  name: string;
  duration: string;
  durationSeconds: number;
  url: string;
}

export interface ElectronAPI {
  sendChat: (text: string) => void;
  sendInterrupt: () => void;
  onTerminalOutput: (cb: (text: string) => void) => { (): void };
  onTurnDone: (cb: () => void) => { (): void };

  startRecording: () => void;
  stopRecording: () => void;
  onRecordingDone: (cb: (data: TakeData) => void) => { (): void };
  onRecordingError: (cb: (msg: string) => void) => { (): void };
  onAudioLevel: (cb: (level: number) => void) => { (): void };

  openAudioFile: () => Promise<string | null>;
  getFilePath: (file: File) => string;
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}

export {};
