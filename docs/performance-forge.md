# NeonForge Performance Forge

Performance Forge is an engine-agnostic ingest layer for exact-performance vocal replacement, voice conversion, and final vocal mix prep.

It is not tied to Suno, Controlla, Spleeter, Demucs, or any other single provider. Those tools can be swapped in and out. The purpose of this layer is to prepare the clean lanes those tools need.

## Core principle

The vocal fingerprint lane should be clean vocal only.

The beat/instrumental lane is used for timing, karaoke-style following, and final mixback. It should not be baked into the clone/fingerprint source unless there is no clean vocal available.

## Input roles

### Clean vocal stem

Use this when you already have the vocal by itself.

```bash
python3 backend/performance_forge.py \
  --artist "Artist" \
  --title "Song" \
  --beat /path/to/beat.mp3 \
  --vocal-stem /path/to/vocal.wav \
  --zip
```

This creates:

- `clone_input/vocal_fingerprint_clean.wav`
- `guide/karaoke_follow_along_mix.wav`
- `guide/karaoke_follow_along_mix.mp3`
- `metadata/manifest.json`
- `delivery/HANDOFF.md`

## Full mix or scratch track fallback

Use this when the input is a full track or contaminated scratch performance and a clean vocal stem is not available.

```bash
python3 backend/performance_forge.py \
  --artist "Artist" \
  --title "Song" \
  --performance-track /path/to/full_mix_or_scratch.mp3 \
  --try-separate \
  --zip
```

If Demucs is installed, Performance Forge tries to separate vocals from instrumental. If separation succeeds, the extracted vocal becomes the clone/fingerprint lane. If separation fails or Demucs is unavailable, the package writes a `NEEDS_CLEAN_VOCAL.md` handoff note.

## Beat plus vocal stem workflow

This is the preferred mode.

```bash
python3 backend/performance_forge.py \
  --artist "Artist" \
  --title "Song" \
  --beat /path/to/beat.mp3 \
  --vocal-stem /path/to/lead_vocal.wav
```

What happens:

1. Beat converts to a normalized reference WAV.
2. Vocal stem converts to a clean reference WAV.
3. Vocal gets a conservative cleanup chain for fingerprint use.
4. Beat and vocal are rendered into a karaoke follow-along guide.
5. A manifest records every input, output, and decision.

## Returned vocal mixback

After an external voice conversion or clone engine returns a dry vocal stem, run:

```bash
python3 backend/performance_forge.py \
  --artist "Artist" \
  --title "Song" \
  --beat /path/to/beat.mp3 \
  --returned-vocal /path/to/returned_voice.wav \
  --zip
```

This creates:

- `mix/returned_vocal_polished.wav`
- `mix/final_reference_mix.wav`
- `mix/final_reference_mix.mp3`

## Full two-stage flow

Stage 1 prepares the clean vocal fingerprint and guide mix:

```bash
python3 backend/performance_forge.py \
  --artist "Artist" \
  --title "Song" \
  --beat ./beat.mp3 \
  --vocal-stem ./vocal.wav \
  --zip
```

Stage 2 mixes the returned converted voice back against the beat:

```bash
python3 backend/performance_forge.py \
  --artist "Artist" \
  --title "Song" \
  --beat ./beat.mp3 \
  --returned-vocal ./returned_voice.wav \
  --zip
```

## Rights rule

Only transform voices you own, performed yourself, or have explicit permission to use. The system is designed around authorized voice conversion and artist-owned workflows.

## Design notes

Performance Forge intentionally keeps the AI/provider layer outside the core pipeline. The local tool does the durable work:

- audio conversion
- lane separation policy
- clean vocal prep
- guide mix rendering
- returned vocal polishing
- final reference mix rendering
- manifest generation
- zip packaging

That makes the external AI service replaceable instead of central.
