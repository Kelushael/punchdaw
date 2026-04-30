# NeonForge Voice

A zero-config, god-mode vocal tracking workstation built on Electron. Record takes over instrumentals, comp the best performances, and export with one click.

## Download

| Platform | Download | Notes |
|----------|----------|-------|
| macOS | [NeonForge-Voice-mac.pkg](https://github.com/Kelushael/punchdaw/releases/latest) | Double-click → Continue → Install |
| Linux | Clone & `npm install && npm start` | See below |

### macOS Install (one click)

1. Download the `.pkg` from [Releases](https://github.com/Kelushael/punchdaw/releases/latest)
2. Double-click it
3. Click **Continue → Continue → Install**
4. Enter your Mac login password when asked
5. **NeonForge Voice** appears in your Applications folder

Everything is bundled — no Homebrew, no terminal, no dependencies to install.

## Features

- **One-button recording** — hit the red button, 4-count intro, automatic take capture
- **Zero-latency monitoring** — hear yourself in real time while recording
- **Staging track** — promote takes from muted lanes to the audible comp track
- **Timeline arrangement** — takes snap to grid, positioned at their recorded offset
- **Beat loading** — drag & drop or click to load instrumentals (WAV, MP3, FLAC, etc.)
- **VU meter** — real-time input level visualization
- **Trim modal** — playback-based trimming with preview
- **Normalize + ZIP export** — level and stitch all takes

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Space` | Play / Pause global transport |
| `Enter` | Return to start |

## Development

```bash
git clone https://github.com/Kelushael/punchdaw.git
cd punchdaw
npm install
npm run dev          # Vite dev server
npm start            # Build + Electron
npm run dist:mac     # Build .pkg + .dmg
```

### macOS Build Requirements

- macOS 10.15+
- Node.js 18+
- Xcode Command Line Tools

The CI workflow (`.github/workflows/release-mac.yml`) builds signed packages automatically on release.

## Architecture

| Layer | Technology |
|-------|------------|
| Frontend | React 19 + TypeScript + Tailwind CSS |
| Desktop | Electron 41 |
| Terminal | xterm.js + Python agent |
| Audio (Linux) | PulseAudio (`parec` + `pactl`) |
| Audio (macOS) | CoreAudio via `ffmpeg -f avfoundation` |
| Backend | Python 3 + Flask + Ollama gateway |

## License

Do what thou wilt.
