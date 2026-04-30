#!/usr/bin/env python3
"""
NeonForge Transcription Module
Interfaces with GPU server (108.181.162.206) for Whisper transcription.
Can also run local fallback if whisper is installed.
"""

import json
import subprocess
import sys
from pathlib import Path

GPU_SERVER = "108.181.162.206"
SSH_KEY = Path.home() / ".ssh/id_ollama"


def transcribe_via_ssh(audio_path: str, model: str = "base") -> dict:
    """Send audio to GPU server via SSH and run Whisper."""
    remote_path = f"/tmp/{Path(audio_path).name}"

    # SCP file to GPU server
    scp = subprocess.run(
        ["scp", "-i", str(SSH_KEY), "-o", "StrictHostKeyChecking=no",
         audio_path, f"administrator@{GPU_SERVER}:{remote_path}"],
        capture_output=True, text=True
    )
    if scp.returncode != 0:
        return {"error": f"SCP failed: {scp.stderr}"}

    # Run Whisper on GPU server
    ssh_cmd = (
        f"ssh -i {SSH_KEY} -o StrictHostKeyChecking=no "
        f"administrator@{GPU_SERVER} "
        f"'whisper {remote_path} --model {model} --output_format json --output_dir /tmp/'"
    )
    result = subprocess.run(ssh_cmd, shell=True, capture_output=True, text=True)

    if result.returncode != 0:
        return {"error": f"Whisper failed: {result.stderr}"}

    # Fetch result back
    json_path = f"/tmp/{Path(audio_path).stem}.json"
    scp_back = subprocess.run(
        ["scp", "-i", str(SSH_KEY), "-o", "StrictHostKeyChecking=no",
         f"administrator@{GPU_SERVER}:{json_path}", "/tmp/"],
        capture_output=True, text=True
    )
    if scp_back.returncode != 0:
        return {"error": f"Result fetch failed: {scp_back.stderr}"}

    data = json.loads(Path("/tmp/" + Path(json_path).name).read_text())
    return {
        "text": data.get("text", ""),
        "segments": data.get("segments", []),
        "language": data.get("language", "en"),
    }


def transcribe_local(audio_path: str, model: str = "base") -> dict:
    """Run whisper locally if available."""
    try:
        import whisper
        m = whisper.load_model(model)
        result = m.transcribe(audio_path)
        return {
            "text": result["text"],
            "segments": result.get("segments", []),
            "language": result.get("language", "en"),
        }
    except ImportError:
        return {"error": "whisper not installed locally. Use GPU server or pip install openai-whisper"}


def main():
    if len(sys.argv) < 2:
        print("Usage: transcribe.py <audio_file> [local|ssh] [model]")
        sys.exit(1)

    audio = sys.argv[1]
    mode = sys.argv[2] if len(sys.argv) > 2 else "local"
    model = sys.argv[3] if len(sys.argv) > 3 else "base"

    if mode == "ssh":
        result = transcribe_via_ssh(audio, model)
    else:
        result = transcribe_local(audio, model)

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
