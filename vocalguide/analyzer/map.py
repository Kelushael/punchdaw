#!/usr/bin/env python3
"""
Vocal Guide Map Generator — with Whisper lyrics + BPM grid alignment
---------------------------------------------------------------------
Feed an MP3. Outputs JSON map with:
  - BPM, beat grid, bar grid, beats_per_second
  - Section boundaries
  - Pitch contour (YIN)
  - Energy envelope
  - Whisper-transcribed lyrics aligned to beats/bars

BPM math:
  beats_per_second = BPM / 60
  beat_period = 60.0 / BPM
  bar_period = beat_period * beats_per_bar

Usage:
  python3 map.py reference.mp3 -o guide.json --bpm 128 --model base
"""

import argparse
import json
import math
import numpy as np
import librosa
from pathlib import Path


def fast_onset_beats(y, sr, bpm=None, beats_per_bar=4):
    hop = 512
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    if bpm is None:
        tempo = librosa.beat.tempo(onset_envelope=onset_env, sr=sr, hop_length=hop)
        bpm = float(tempo[0]) if hasattr(tempo, '__iter__') else float(tempo)
    beat_period = 60.0 / bpm
    beat_frames_per_second = sr / hop
    period_frames = int(beat_period * beat_frames_per_second)
    beat_frames = librosa.util.peak_pick(
        onset_env, pre_max=period_frames//2, post_max=period_frames//2,
        pre_avg=period_frames, post_avg=period_frames,
        delta=0.5*np.mean(onset_env), wait=period_frames//2
    )
    if len(beat_frames) == 0:
        duration = len(y) / sr
        n_beats = int(duration / beat_period)
        return bpm, [i * beat_period for i in range(n_beats + 1)]
    first_beat_time = librosa.frames_to_time(beat_frames[0], sr=sr, hop_length=hop)
    duration = len(y) / sr
    beat_times = []
    t = first_beat_time
    while t < duration:
        beat_times.append(float(t))
        t += beat_period
    return bpm, beat_times


def extract_pitch_contour(y, sr, hop_length=512):
    f0 = librosa.yin(y, fmin=librosa.note_to_hz('C2'), fmax=librosa.note_to_hz('C7'),
                     sr=sr, hop_length=hop_length)
    times = librosa.frames_to_time(np.arange(len(f0)), sr=sr, hop_length=hop_length)
    contour = []
    for t, freq in zip(times, f0):
        if freq is not None and not np.isnan(freq) and freq > 0:
            contour.append({
                'time': float(t),
                'frequency': float(freq),
                'midi': float(librosa.hz_to_midi(freq)),
                'confidence': 1.0
            })
        else:
            contour.append({'time': float(t), 'frequency': 0.0, 'midi': 0.0, 'confidence': 0.0})
    return contour


def extract_energy(y, sr, hop_length=512):
    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
    return [{'time': float(t), 'rms': float(e)} for t, e in zip(times, rms)]


def simple_sections(duration, bpm, beats_per_bar=4):
    bar_duration = beats_per_bar * 60.0 / bpm
    total_bars = int(duration / bar_duration)
    structure = [
        ('Intro', 4), ('Verse', 8), ('Chorus', 8),
        ('Verse', 8), ('Chorus', 8), ('Bridge', 4),
        ('Chorus', 8), ('Outro', 4)
    ]
    sections = []
    bar_idx = 0
    for name, bars in structure:
        if bar_idx >= total_bars:
            break
        end_bar = min(bar_idx + bars, total_bars)
        sections.append({
            'name': name,
            'start_bar': bar_idx,
            'end_bar': end_bar,
            'start_time': round(bar_idx * bar_duration, 3),
            'end_time': round(end_bar * bar_duration, 3)
        })
        bar_idx = end_bar
    if bar_idx < total_bars:
        sections.append({
            'name': 'Outro',
            'start_bar': bar_idx,
            'end_bar': total_bars,
            'start_time': round(bar_idx * bar_duration, 3),
            'end_time': round(total_bars * bar_duration, 3)
        })
    return sections


def transcribe_with_whisper(mp3_path, model_size='base'):
    """Transcribe MP3 using faster-whisper. Returns list of word dicts."""
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print("faster_whisper not available, falling back to openai-whisper")
        import whisper
        model = whisper.load_model(model_size)
        result = model.transcribe(mp3_path, word_timestamps=True)
        words = []
        for seg in result.get('segments', []):
            for w in seg.get('words', []):
                words.append({
                    'text': w.get('word', '').strip(),
                    'start': float(w.get('start', 0)),
                    'end': float(w.get('end', 0))
                })
        return words

    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(mp3_path, word_timestamps=True)
    words = []
    for seg in segments:
        for w in seg.words:
            words.append({
                'text': w.word.strip(),
                'start': float(w.start),
                'end': float(w.end)
            })
    return words


def align_words_to_grid(words, bpm, beats, bars, beats_per_bar=4):
    """
    Map each whisper word to the nearest beat/bar.
    beat_period = 60 / BPM
    beats_per_second = BPM / 60
    """
    if not words:
        return []
    beat_period = 60.0 / bpm
    beats_per_second = bpm / 60.0

    aligned = []
    for w in words:
        t = (w['start'] + w['end']) / 2.0  # center time
        # Find nearest beat
        beat_idx = 0
        for i, bt in enumerate(beats):
            if bt <= t:
                beat_idx = i
            else:
                break
        bar_idx = beat_idx // beats_per_bar
        beat_in_bar = beat_idx % beats_per_bar

        # Snap word boundaries to beat grid
        snapped_start = math.floor(w['start'] / beat_period) * beat_period
        snapped_end = math.ceil(w['end'] / beat_period) * beat_period

        aligned.append({
            'text': w['text'],
            'start_time': round(w['start'], 3),
            'end_time': round(w['end'], 3),
            'snapped_start': round(snapped_start, 3),
            'snapped_end': round(snapped_end, 3),
            'beat_index': beat_idx,
            'bar_index': bar_idx,
            'beat_within_bar': beat_in_bar,
            'beats_per_second': round(beats_per_second, 4),
            'beat_period': round(beat_period, 4)
        })
    return aligned


def generate_guide(mp3_path, output_path, bpm_override=None, beats_per_bar=4, whisper_model='base', no_whisper=False):
    print(f"Loading {mp3_path}...")
    y, sr = librosa.load(mp3_path, sr=None, mono=True)
    duration = float(len(y) / sr)
    print(f"Duration: {duration:.2f}s  SR: {sr}Hz")

    print("Detecting beats...")
    bpm, beat_times = fast_onset_beats(y, sr, bpm=bpm_override, beats_per_bar=beats_per_bar)
    beat_period = 60.0 / bpm
    beats_per_second = bpm / 60.0
    print(f"BPM: {bpm:.1f}  Beat period: {beat_period:.4f}s  Beats/sec: {beats_per_second:.4f}")

    print("Building bars...")
    bars = []
    for i in range(0, len(beat_times) - beats_per_bar, beats_per_bar):
        bar_beats = beat_times[i:i+beats_per_bar+1]
        bars.append({
            'index': i // beats_per_bar,
            'start_time': float(bar_beats[0]),
            'end_time': float(bar_beats[-1]) if len(bar_beats) > beats_per_bar else float(beat_times[-1]),
            'beat_times': [float(b) for b in bar_beats[:-1]] if len(bar_beats) > beats_per_bar else [float(b) for b in bar_beats]
        })
    print(f"Bars: {len(bars)}")

    print("Generating sections...")
    sections = simple_sections(duration, bpm, beats_per_bar)
    print(f"Sections: {[s['name'] for s in sections]}")

    print("Extracting pitch contour...")
    pitch_contour = extract_pitch_contour(y, sr)
    print(f"Pitch frames: {len(pitch_contour)}")

    print("Computing energy...")
    energy = extract_energy(y, sr)
    print(f"Energy frames: {len(energy)}")

    # Whisper lyrics
    lyrics = []
    if not no_whisper:
        print(f"Transcribing lyrics with Whisper ({whisper_model})...")
        try:
            words = transcribe_with_whisper(mp3_path, whisper_model)
            print(f"Raw words: {len(words)}")
            lyrics = align_words_to_grid(words, bpm, beat_times, bars, beats_per_bar)
            print(f"Aligned words: {len(lyrics)}")
        except Exception as e:
            print(f"Whisper failed: {e}")
            print("Continuing without lyrics.")

    guide = {
        'source_file': str(Path(mp3_path).name),
        'duration_seconds': round(duration, 3),
        'sample_rate': sr,
        'bpm': round(bpm, 2),
        'beats_per_bar': beats_per_bar,
        'beat_period': round(beat_period, 4),
        'beats_per_second': round(beats_per_second, 4),
        'beats': beat_times,
        'bars': bars,
        'sections': sections,
        'pitch_contour': pitch_contour,
        'energy': energy,
        'lyrics': lyrics,
        'meta': {
            'generated_by': 'vocalguide-analyzer v2.0',
            'bpm_math': 'beats_per_second = BPM / 60  |  beat_period = 60 / BPM',
            'whisper_model': whisper_model if not no_whisper else 'disabled'
        }
    }

    with open(output_path, 'w') as f:
        json.dump(guide, f, indent=2)
    print(f"\n✅ Guide written to {output_path}")
    print(f"   {duration:.1f}s | {bpm:.1f} BPM | {len(bars)} bars | {len(sections)} sections | {len(lyrics)} words")
    return guide


def main():
    parser = argparse.ArgumentParser(description='Generate vocal guide map from MP3.')
    parser.add_argument('mp3', help='Input MP3 file')
    parser.add_argument('-o', '--output', default='guide.json', help='Output JSON path')
    parser.add_argument('--bpm', type=float, default=None, help='Override auto-detected BPM')
    parser.add_argument('--beats-per-bar', type=int, default=4)
    parser.add_argument('--whisper-model', default='base', help='Whisper model: tiny, base, small')
    parser.add_argument('--no-whisper', action='store_true', help='Skip lyrics transcription')
    args = parser.parse_args()

    generate_guide(args.mp3, args.output, bpm_override=args.bpm, beats_per_bar=args.beats_per_bar,
                   whisper_model=args.whisper_model, no_whisper=args.no_whisper)


if __name__ == '__main__':
    main()
