#!/usr/bin/env python3
"""
NeonForge Performance Forge

Engine-agnostic ingest layer for "exact performance" vocal replacement and mix prep.

This script is intentionally not tied to Suno, Controlla, Spleeter, Demucs,
or any single provider. It builds the local package around them:

- Beat/instrumental lane
- Clean vocal fingerprint lane
- Karaoke follow-along guide lane
- Optional full-mix/reference lane
- Optional local separation when Demucs is installed
- Returned authorized voice/conversion vocal mixback
- Manifest + next-step docs

Voice rights rule:
Only transform voices you own, performed yourself, or have explicit permission to use.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import textwrap
import zipfile
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


APP_NAME = "NeonForge Performance Forge"
DEFAULT_SR = 44100
DEFAULT_CHANNELS = 2


class ForgeError(RuntimeError):
    pass


@dataclass
class AudioInfo:
    path: str
    duration_seconds: float
    sample_rate: Optional[int]
    channels: Optional[int]
    codec: Optional[str]
    bit_rate: Optional[str]


def now_slug() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def safe_slug(value: str, fallback: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9._ -]+", "", value or "").strip()
    value = re.sub(r"\s+", "_", value)
    return value or fallback


def which(binary: str) -> Optional[str]:
    return shutil.which(binary)


def require(binary: str) -> str:
    found = which(binary)
    if not found:
        raise ForgeError(f"Missing required binary: {binary}. Install ffmpeg/ffprobe or bundle it with NeonForge.")
    return found


def run(cmd: List[str], *, label: str, cwd: Optional[Path] = None, allow_fail: bool = False) -> subprocess.CompletedProcess[str]:
    print(f"[forge] {label}")
    print("[cmd] " + " ".join(str(x) for x in cmd))
    result = subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True)
    if result.returncode != 0 and not allow_fail:
        raise ForgeError(
            f"{label} failed with exit code {result.returncode}\n\n"
            f"STDOUT:\n{result.stdout[-4000:]}\n\nSTDERR:\n{result.stderr[-4000:]}"
        )
    return result


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def copy_original(src: Path, dst_dir: Path) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    shutil.copy2(src, dst)
    return dst


def ffprobe_json(path: Path) -> Dict[str, Any]:
    ffprobe = require("ffprobe")
    result = run(
        [
            ffprobe,
            "-v", "error",
            "-show_format",
            "-show_streams",
            "-of", "json",
            str(path),
        ],
        label=f"Inspect {path.name}",
    )
    return json.loads(result.stdout or "{}")


def audio_info(path: Path) -> AudioInfo:
    probe = ffprobe_json(path)
    fmt = probe.get("format", {}) or {}
    streams = [s for s in probe.get("streams", []) if s.get("codec_type") == "audio"]
    stream = streams[0] if streams else {}

    def as_float(v: Any) -> float:
        try:
            return float(v or 0)
        except Exception:
            return 0.0

    def as_int(v: Any) -> Optional[int]:
        try:
            return int(v) if v is not None else None
        except Exception:
            return None

    return AudioInfo(
        path=str(path),
        duration_seconds=as_float(fmt.get("duration") or stream.get("duration")),
        sample_rate=as_int(stream.get("sample_rate")),
        channels=as_int(stream.get("channels")),
        codec=stream.get("codec_name"),
        bit_rate=fmt.get("bit_rate"),
    )


def convert_audio(src: Path, dst: Path, *, sr: int = DEFAULT_SR, channels: int = DEFAULT_CHANNELS) -> None:
    ffmpeg = require("ffmpeg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            ffmpeg, "-y",
            "-i", str(src),
            "-vn",
            "-ac", str(channels),
            "-ar", str(sr),
            "-sample_fmt", "s16",
            str(dst),
        ],
        label=f"Convert {src.name} -> {dst.name}",
    )


def loudnorm(src: Path, dst: Path, *, integrated_lufs: float, true_peak: float = -1.5, lra: float = 9.0) -> None:
    ffmpeg = require("ffmpeg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            ffmpeg, "-y",
            "-i", str(src),
            "-vn",
            "-af", f"loudnorm=I={integrated_lufs}:TP={true_peak}:LRA={lra}",
            "-ac", str(DEFAULT_CHANNELS),
            "-ar", str(DEFAULT_SR),
            "-sample_fmt", "s16",
            str(dst),
        ],
        label=f"Loudness normalize {src.name}",
    )


def vocal_clean_chain(src: Path, dst: Path) -> None:
    """FFmpeg-only cleanup for clone/fingerprint input. No fake AI pitch claims."""
    ffmpeg = require("ffmpeg")
    chain = ",".join(
        [
            "agate=threshold=0.010:ratio=1.5:attack=20:release=180",
            "highpass=f=70",
            "lowpass=f=17500",
            "loudnorm=I=-18:TP=-2:LRA=11",
        ]
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            ffmpeg, "-y",
            "-i", str(src),
            "-vn",
            "-af", chain,
            "-ac", str(DEFAULT_CHANNELS),
            "-ar", str(DEFAULT_SR),
            "-sample_fmt", "s16",
            str(dst),
        ],
        label="Prepare clean vocal fingerprint input",
    )


def vocal_mix_chain(src: Path, dst: Path) -> None:
    """Conservative reference-mix vocal chain for returned authorized voice stem."""
    ffmpeg = require("ffmpeg")
    chain = ",".join(
        [
            "agate=threshold=0.014:ratio=1.8:attack=20:release=180",
            "highpass=f=75",
            "lowpass=f=17000",
            "equalizer=f=260:t=q:w=1:g=-1.5",
            "equalizer=f=3300:t=q:w=1:g=1.8",
            "acompressor=threshold=-18dB:ratio=2.3:attack=12:release=110:makeup=1.8",
            "loudnorm=I=-16:TP=-1.5:LRA=9",
        ]
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            ffmpeg, "-y",
            "-i", str(src),
            "-vn",
            "-af", chain,
            "-ac", str(DEFAULT_CHANNELS),
            "-ar", str(DEFAULT_SR),
            "-sample_fmt", "s16",
            str(dst),
        ],
        label="Polish returned vocal for mixback",
    )


def make_mp3(src: Path, dst: Path) -> None:
    ffmpeg = require("ffmpeg")
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            ffmpeg, "-y",
            "-i", str(src),
            "-codec:a", "libmp3lame",
            "-b:a", "320k",
            str(dst),
        ],
        label=f"Create MP3 reference {dst.name}",
    )


def make_karaoke_guide(beat: Path, vocal: Path, dst: Path, *, beat_gain: float, vocal_gain: float) -> None:
    ffmpeg = require("ffmpeg")
    filter_complex = (
        f"[0:a]volume={beat_gain}[beat];"
        f"[1:a]volume={vocal_gain}[vox];"
        "[beat][vox]amix=inputs=2:duration=longest:normalize=0,"
        "loudnorm=I=-16:TP=-1.5:LRA=10[mix]"
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            ffmpeg, "-y",
            "-i", str(beat),
            "-i", str(vocal),
            "-filter_complex", filter_complex,
            "-map", "[mix]",
            "-ac", str(DEFAULT_CHANNELS),
            "-ar", str(DEFAULT_SR),
            "-sample_fmt", "s16",
            str(dst),
        ],
        label="Create karaoke follow-along guide mix",
    )


def make_final_mix(beat: Path, returned_vocal: Path, dst: Path, *, beat_gain: float, vocal_gain: float) -> None:
    ffmpeg = require("ffmpeg")
    filter_complex = (
        f"[0:a]volume={beat_gain}[beat];"
        f"[1:a]volume={vocal_gain},aecho=0.55:0.30:185:0.12[vox];"
        "[beat][vox]amix=inputs=2:duration=longest:normalize=0,"
        "loudnorm=I=-14:TP=-1.0:LRA=9[mix]"
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            ffmpeg, "-y",
            "-i", str(beat),
            "-i", str(returned_vocal),
            "-filter_complex", filter_complex,
            "-map", "[mix]",
            "-ac", str(DEFAULT_CHANNELS),
            "-ar", str(DEFAULT_SR),
            "-sample_fmt", "s16",
            str(dst),
        ],
        label="Render final reference mix",
    )


def find_demucs_output(sep_root: Path) -> Tuple[Optional[Path], Optional[Path]]:
    vocals = list(sep_root.rglob("vocals.wav"))
    no_vocals = list(sep_root.rglob("no_vocals.wav"))
    return (vocals[0] if vocals else None, no_vocals[0] if no_vocals else None)


def try_demucs_separate(src: Path, sep_dir: Path) -> Tuple[Optional[Path], Optional[Path], str]:
    demucs = which("demucs")
    if not demucs:
        return None, None, "demucs_not_installed"

    sep_dir.mkdir(parents=True, exist_ok=True)
    result = run(
        [demucs, "--two-stems", "vocals", "-o", str(sep_dir), str(src)],
        label="Attempt local Demucs vocal/instrumental separation",
        allow_fail=True,
    )
    vocals, no_vocals = find_demucs_output(sep_dir)
    if result.returncode != 0 or not vocals:
        return None, None, "demucs_failed"
    return vocals, no_vocals, "demucs_ok"


def zip_folder(folder: Path, zip_path: Path) -> None:
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file in folder.rglob("*"):
            if file.is_file() and file != zip_path:
                zf.write(file, file.relative_to(folder))


def handoff_md(manifest: Dict[str, Any]) -> str:
    clean_vocal = manifest["outputs"].get("clone_input_vocal")
    guide_mix = manifest["outputs"].get("karaoke_guide_mix")
    final_mix = manifest["outputs"].get("final_mix")
    sep_status = manifest["separation"]["status"]

    return textwrap.dedent(
        f"""
        # Performance Forge Handoff

        ## Core idea

        This package treats the vocal performance and the beat as separate lanes.

        The clone / voice-conversion input should be clean vocal only. The beat is used for
        alignment, karaoke-style following, and final mixback — not as fingerprint material.

        ## Files that matter

        - Clean clone input: `{clean_vocal or "not available yet"}`
        - Follow-along guide mix: `{guide_mix or "not available yet"}`
        - Final reference mix: `{final_mix or "not rendered yet"}`
        - Separation status: `{sep_status}`

        ## Recommended external-engine flow

        1. Feed the clean vocal file into your authorized voice conversion / clone / swap engine.
        2. Use the karaoke guide mix only as a human reference for melody, timing, emotion, and phrasing.
        3. Do not train/fingerprint from a file with instruments baked into it unless there is no other option.
        4. Download the returned dry converted vocal.
        5. Re-run Performance Forge with `--returned-vocal` to mix it against the beat.

        ## Input roles

        - `--vocal-stem` means the file is already a clean vocal stem.
        - `--performance-track` means the file is a full mix or scratch recording that needs vocal extraction.
        - `--beat` means instrumental/beat lane.
        - `--full-mix` means reference-only full mix.
        - `--returned-vocal` means the voice-converted/generated vocal stem to mix back in.

        ## Rights

        Only use your own voice, a collaborator with permission, or licensed/authorized voices.
        """
    ).strip() + "\n"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Prepare exact-performance vocal replacement / mix packages.")
    p.add_argument("--artist", default="Artist", help="Artist name for package metadata.")
    p.add_argument("--title", default="Untitled", help="Song/session title for package metadata.")
    p.add_argument("--out", default=None, help="Output root. Defaults to ./performance_forge_exports")

    p.add_argument("--beat", default=None, help="Instrumental/beat lane.")
    p.add_argument("--vocal-stem", default=None, help="Clean vocal stem. Used directly as clone/fingerprint input.")
    p.add_argument("--performance-track", default=None, help="Full/scratch track whose vocal performance should be extracted.")
    p.add_argument("--full-mix", default=None, help="Optional full finished mix/reference track.")
    p.add_argument("--returned-vocal", default=None, help="Returned voice-converted/generated dry vocal stem.")

    p.add_argument("--try-separate", action="store_true", help="Try local Demucs separation for --performance-track.")
    p.add_argument("--force-separate-vocal", action="store_true", help="Treat --vocal-stem as contaminated/mixed and try separation first.")
    p.add_argument("--beat-gain", type=float, default=0.86, help="Beat gain for guide/final renders.")
    p.add_argument("--guide-vocal-gain", type=float, default=0.90, help="Original vocal gain in karaoke guide.")
    p.add_argument("--final-vocal-gain", type=float, default=1.00, help="Returned vocal gain in final mix.")
    p.add_argument("--zip", action="store_true", help="Create a zip archive of the package.")
    return p


def resolve_paths(args: argparse.Namespace) -> Dict[str, Optional[Path]]:
    items = {
        "beat": args.beat,
        "vocal_stem": args.vocal_stem,
        "performance_track": args.performance_track,
        "full_mix": args.full_mix,
        "returned_vocal": args.returned_vocal,
    }
    resolved: Dict[str, Optional[Path]] = {}
    for key, value in items.items():
        if not value:
            resolved[key] = None
            continue
        path = Path(value).expanduser().resolve()
        if not path.exists():
            raise ForgeError(f"{key} file not found: {path}")
        resolved[key] = path
    if not any([resolved["vocal_stem"], resolved["performance_track"], resolved["returned_vocal"]]):
        raise ForgeError("Provide at least --vocal-stem, --performance-track, or --returned-vocal.")
    return resolved


def forge(args: argparse.Namespace) -> Path:
    paths = resolve_paths(args)

    out_root = Path(args.out).expanduser().resolve() if args.out else Path.cwd() / "performance_forge_exports"
    session_name = f"{safe_slug(args.artist, 'artist')}-{safe_slug(args.title, 'song')}-{now_slug()}"
    root = out_root / session_name

    dirs = {
        "audio": root / "audio",
        "clone": root / "clone_input",
        "guide": root / "guide",
        "mix": root / "mix",
        "separation": root / "separation",
        "metadata": root / "metadata",
        "delivery": root / "delivery",
        "originals": root / "originals",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    inputs: Dict[str, Optional[str]] = {}
    input_info: Dict[str, Any] = {}
    outputs: Dict[str, str] = {}
    separation = {"status": "not_requested", "source": None, "vocals": None, "instrumental": None}

    for role, path in paths.items():
        if path:
            copy_original(path, dirs["originals"])
            inputs[role] = str(path)
            input_info[role] = asdict(audio_info(path))
        else:
            inputs[role] = None

    beat_ref: Optional[Path] = None
    vocal_source: Optional[Path] = None

    if paths["beat"]:
        beat_ref = dirs["audio"] / "beat_reference.wav"
        convert_audio(paths["beat"], beat_ref)
        outputs["beat_reference"] = str(beat_ref)

    if paths["vocal_stem"] and not args.force_separate_vocal:
        vocal_source = dirs["audio"] / "vocal_stem_reference.wav"
        convert_audio(paths["vocal_stem"], vocal_source)
        separation["status"] = "not_needed_clean_vocal_stem_supplied"
    else:
        sep_candidate = paths["vocal_stem"] if args.force_separate_vocal else paths["performance_track"]
        if sep_candidate and args.try_separate:
            separation["source"] = str(sep_candidate)
            sep_vocals, sep_instrumental, status = try_demucs_separate(sep_candidate, dirs["separation"])
            separation["status"] = status
            if sep_vocals:
                vocal_source = dirs["audio"] / "extracted_vocal_reference.wav"
                convert_audio(sep_vocals, vocal_source)
                outputs["extracted_vocal_reference"] = str(vocal_source)
                separation["vocals"] = str(sep_vocals)
            if sep_instrumental and not beat_ref:
                beat_ref = dirs["audio"] / "extracted_instrumental_reference.wav"
                convert_audio(sep_instrumental, beat_ref)
                outputs["extracted_instrumental_reference"] = str(beat_ref)
                separation["instrumental"] = str(sep_instrumental)
        elif sep_candidate:
            separation["status"] = "needs_separation_but_not_requested"

    if paths["full_mix"]:
        full_ref = dirs["audio"] / "full_mix_reference.wav"
        convert_audio(paths["full_mix"], full_ref)
        outputs["full_mix_reference"] = str(full_ref)
        full_mp3 = dirs["audio"] / "full_mix_reference.mp3"
        make_mp3(full_ref, full_mp3)
        outputs["full_mix_reference_mp3"] = str(full_mp3)

    if paths["performance_track"]:
        perf_ref = dirs["audio"] / "performance_track_reference.wav"
        convert_audio(paths["performance_track"], perf_ref)
        outputs["performance_track_reference"] = str(perf_ref)

    if vocal_source:
        clean_vocal = dirs["clone"] / "vocal_fingerprint_clean.wav"
        vocal_clean_chain(vocal_source, clean_vocal)
        outputs["clone_input_vocal"] = str(clean_vocal)

        if beat_ref:
            guide_mix = dirs["guide"] / "karaoke_follow_along_mix.wav"
            make_karaoke_guide(beat_ref, clean_vocal, guide_mix, beat_gain=args.beat_gain, vocal_gain=args.guide_vocal_gain)
            outputs["karaoke_guide_mix"] = str(guide_mix)
            guide_mp3 = dirs["guide"] / "karaoke_follow_along_mix.mp3"
            make_mp3(guide_mix, guide_mp3)
            outputs["karaoke_guide_mix_mp3"] = str(guide_mp3)

    if paths["returned_vocal"]:
        returned_ref = dirs["audio"] / "returned_vocal_reference.wav"
        convert_audio(paths["returned_vocal"], returned_ref)
        outputs["returned_vocal_reference"] = str(returned_ref)

        polished = dirs["mix"] / "returned_vocal_polished.wav"
        vocal_mix_chain(returned_ref, polished)
        outputs["returned_vocal_polished"] = str(polished)

        if beat_ref:
            final_mix = dirs["mix"] / "final_reference_mix.wav"
            make_final_mix(beat_ref, polished, final_mix, beat_gain=args.beat_gain, vocal_gain=args.final_vocal_gain)
            outputs["final_mix"] = str(final_mix)
            final_mp3 = dirs["mix"] / "final_reference_mix.mp3"
            make_mp3(final_mix, final_mp3)
            outputs["final_mix_mp3"] = str(final_mp3)

    if not vocal_source:
        write_text(
            dirs["delivery"] / "NEEDS_CLEAN_VOCAL.md",
            textwrap.dedent(
                """
                # Clean Vocal Needed

                Performance Forge did not produce a clean vocal fingerprint lane.

                Best options:
                1. Provide `--vocal-stem` if you already have the vocal stem.
                2. Provide `--performance-track` plus `--try-separate` if Demucs is installed.
                3. Provide a vocal-only export from your DAW.

                The clone/voice conversion engine should not fingerprint from a file with the beat
                baked into it unless you have no other option.
                """
            ).strip() + "\n",
        )

    manifest = {
        "app": APP_NAME,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "artist": args.artist,
        "title": args.title,
        "inputs": inputs,
        "input_info": input_info,
        "separation": separation,
        "outputs": outputs,
        "rules": {
            "clone_input_policy": "Use clean vocal stem only. Beat/instrumental is guide and mixback, not fingerprint material.",
            "rights_policy": "Only transform voices you own, performed yourself, or have explicit permission to use.",
            "engine_policy": "External generation/conversion engines are swappable. This package only prepares and mixes assets.",
        },
    }

    write_json(dirs["metadata"] / "manifest.json", manifest)
    write_text(dirs["delivery"] / "HANDOFF.md", handoff_md(manifest))

    summary = {
        "workspace": str(root),
        "separation_status": separation["status"],
        "clone_input_ready": bool(outputs.get("clone_input_vocal")),
        "guide_mix_ready": bool(outputs.get("karaoke_guide_mix")),
        "final_mix_ready": bool(outputs.get("final_mix")),
        "outputs": outputs,
        "next_action": (
            "Send clone_input/vocal_fingerprint_clean.wav to your authorized voice conversion engine, "
            "then rerun with --returned-vocal to render the mix."
            if outputs.get("clone_input_vocal") and not outputs.get("final_mix")
            else "Review delivery/HANDOFF.md."
        ),
    }
    write_json(root / "forge_summary.json", summary)

    if args.zip:
        zip_path = out_root / f"{session_name}.zip"
        zip_folder(root, zip_path)
        summary["zip"] = str(zip_path)
        write_json(root / "forge_summary.json", summary)

    print(json.dumps(summary, indent=2))
    return root


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        out = forge(args)
        print(f"\n✅ Performance Forge package complete: {out}")
        return 0
    except ForgeError as exc:
        print(f"\n❌ {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
