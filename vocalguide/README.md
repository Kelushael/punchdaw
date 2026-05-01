# NeonForge Vocal Guide

**Cymatic karaoke lattice for vocal practice.**

Feed an MP3 reference track. The analyzer maps every beat, bar, section, and pitch contour — then Whisper transcribes the lyrics and snaps them to the BPM grid. The visualizer renders it all as a living cymatic plate: you see the words before you sing them, your live pitch orbits the reference line, and the background blooms gold when you nail the note.

---

## What it does

| Feature | How |
|---|---|
| **BPM Grid** | `beats_per_second = BPM / 60`. Every beat, bar, and downbeat mapped. |
| **Whisper Lyrics** | OpenAI Whisper transcribes words → aligned to nearest beat/bar. |
| **Pitch Contour** | YIN algorithm extracts reference melody. Live YIN on mic input. |
| **Formant Analysis** | LPC (10th order) tracks F1/F2/F3 in real time. |
| **Cymatic Background** | Chladni-plate standing waves + fBM noise. Responds to your energy & consistency. |
| **Symmetric Lattice** | Timeline centered on "now". Equal window left/right. Lyrics positioned at exact temporal coordinates. |
| **Lookahead** | Current line + next line shown at bottom. Words highlight as their time arrives. |

---

## Quick Start (Linux)

```bash
# 1. Analyze your MP3
cd analyzer
python3 map.py ~/Music/your_song.mp3 -o guide.json --bpm 128

# 2. Launch visualizer
cd ../build
./vocalguide ../guide.json ~/Music/your_song.mp3
```

## Quick Start (macOS — Intel)

```bash
# 1. Install deps (one time)
brew install sdl2 sdl2_ttf cmake

# 2. Build
cd scripts
./build-mac.sh

# 3. Launch
open ../build-mac/"NeonForge Vocal Guide.app"
```

---

## Controls

| Key | Action |
|---|---|
| `Space` | Play / Pause |
| `R` | Restart from beginning |
| `Esc` | Quit |

---

## Analyzer Options

```bash
python3 map.py song.mp3 -o guide.json [options]
```

| Option | Description |
|---|---|
| `--bpm 128` | Override auto-detected BPM |
| `--beats-per-bar 4` | Time signature (default 4/4) |
| `--whisper-model tiny` | Whisper model: tiny, base, small |
| `--no-whisper` | Skip lyrics transcription |

---

## File Structure

```
vocalguide/
├── analyzer/
│   └── map.py           # MP3 → guide.json (Python + librosa + Whisper)
├── src/
│   ├── main.cpp         # C++ visualizer (SDL2 + OpenGL + miniaudio)
│   ├── miniaudio.h      # Single-header audio engine
│   └── json.hpp         # Single-header JSON parser
├── scripts/
│   └── build-mac.sh     # macOS app bundle builder
├── build/               # Linux build dir
└── README.md            # This file
```

---

## BPM Math

```
beat_period      = 60.0 / BPM
beats_per_second = BPM / 60.0
bar_period       = beat_period * beats_per_bar
```

Every lyric word is snapped to the nearest beat. The visualizer places words at `(time, pitch)` coordinates on a symmetric lattice centered on the current playback position.

---

## Requirements

**Linux:** `libsdl2-dev libsdl2-ttf-dev libgl1-mesa-dev cmake g++ python3 librosa numpy`

**macOS:** Xcode Command Line Tools, Homebrew, `sdl2`, `sdl2_ttf`, `cmake`
