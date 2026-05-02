#!/usr/bin/env python3
"""
NeonForge Agent v2.1 — Context-aware audio production companion.

The agent is not a blind chatbot bolted onto the left side of the UI.
It loads a durable map of the workstation, inspects the local session, and speaks
like a calm co-builder inside the app.
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
import tarfile
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── Paths ───────────────────────────────────────────────────────────
WORKBENCH_DIR = Path(os.environ.get("NEONFORGE_WORKBENCH", Path.cwd())).resolve()
BACKEND_DIR = WORKBENCH_DIR / "backend"
REPO_CLIPS_DIR = WORKBENCH_DIR / "clips"

APP_DIR = Path.home() / ".neonslab-voiceforge"
ARCHIVE_DIR = APP_DIR / "archive"
DB_PATH = APP_DIR / "agent.db"
APP_STATE_PATH = APP_DIR / "app_state.json"
CONTEXT_MANIFEST_PATH = BACKEND_DIR / "app_context_manifest.json"
PERFORMANCE_FORGE_SCRIPT = BACKEND_DIR / "performance_forge.py"

MODEL_BASE = os.environ.get("NEONFORGE_MODEL_BASE", "http://185.28.23.43:8787/v1")
MODEL_NAME = os.environ.get("NEONFORGE_MODEL_NAME", "qwen2.5:7b")
API_KEY = os.environ.get("NEONFORGE_API_KEY", "ollama")
TEMPERATURE = float(os.environ.get("NEONFORGE_TEMPERATURE", "0.25"))

APP_DIR.mkdir(parents=True, exist_ok=True)
ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
REPO_CLIPS_DIR.mkdir(parents=True, exist_ok=True)

AUDIO_SUFFIXES = {".wav", ".mp3", ".webm", ".m4a", ".flac", ".ogg", ".aac", ".aiff"}

# ── SQLite persistence ──────────────────────────────────────────────
def init_db() -> None:
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS conversations (
            id TEXT PRIMARY KEY,
            title TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            conv_id TEXT,
            role TEXT,
            content TEXT,
            timestamp TEXT,
            FOREIGN KEY (conv_id) REFERENCES conversations(id)
        )
    """)
    c.execute("""
        CREATE TABLE IF NOT EXISTS notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT,
            content TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


init_db()
CONV_ID = os.environ.get("NEONFORGE_CONV", uuid.uuid4().hex[:12])


def ensure_conv(title: str = "NeonForge Session") -> None:
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT 1 FROM conversations WHERE id = ?", (CONV_ID,))
    if not c.fetchone():
        now = datetime.now(timezone.utc).isoformat()
        c.execute(
            "INSERT INTO conversations (id, title, created_at, updated_at) VALUES (?,?,?,?)",
            (CONV_ID, title, now, now),
        )
        conn.commit()
    conn.close()


ensure_conv()


def save_message(role: str, content: str) -> None:
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    c.execute(
        "INSERT INTO messages (conv_id, role, content, timestamp) VALUES (?,?,?,?)",
        (CONV_ID, role, content, now),
    )
    c.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (now, CONV_ID))
    conn.commit()
    conn.close()


def save_note(kind: str, content: str) -> None:
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    now = datetime.now(timezone.utc).isoformat()
    c.execute("INSERT INTO notes (kind, content, created_at) VALUES (?,?,?)", (kind, content, now))
    conn.commit()
    conn.close()


def load_history(limit: int = 20) -> List[Dict[str, str]]:
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute(
        "SELECT role, content FROM messages WHERE conv_id = ? ORDER BY id DESC LIMIT ?",
        (CONV_ID, limit),
    )
    rows = list(c.fetchall())
    conn.close()
    return [{"role": r, "content": c} for r, c in reversed(rows)]


def load_recent_notes(limit: int = 8) -> List[Dict[str, str]]:
    conn = sqlite3.connect(str(DB_PATH))
    c = conn.cursor()
    c.execute("SELECT kind, content, created_at FROM notes ORDER BY id DESC LIMIT ?", (limit,))
    rows = list(c.fetchall())
    conn.close()
    return [{"kind": k, "content": c, "created_at": t} for k, c, t in rows]

# ── Context and session awareness ───────────────────────────────────
def read_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return default


def load_context_manifest() -> Dict[str, Any]:
    default_manifest = {
        "name": "NeonForge Voice",
        "purpose": "Audio workstation with a left-side agent and right-side vocal tracking surface.",
        "surfaces": {},
        "behavior_rules": [
            "Use the app map before guessing about controls.",
            "Be calm, friendly, and practical.",
        ],
    }
    return read_json(CONTEXT_MANIFEST_PATH, default_manifest)


def inspect_audio_file(path: Path) -> Dict[str, Any]:
    info = {
        "name": path.name,
        "path": str(path),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat() if path.exists() else None,
    }
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=str(WORKBENCH_DIR),
        )
        if result.returncode == 0:
            duration = float((result.stdout or "0").strip() or 0)
            info["duration_seconds"] = round(duration, 3)
    except Exception:
        pass
    return info


def list_clips() -> List[Dict[str, Any]]:
    clips = []
    for f in sorted(REPO_CLIPS_DIR.glob("*"), key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True):
        if f.is_file() and f.suffix.lower() in AUDIO_SUFFIXES:
            clips.append(inspect_audio_file(f))
    return clips


def inspect_session_state() -> Dict[str, Any]:
    live_state = read_json(APP_STATE_PATH, {})
    clips = list_clips()
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "workbench_dir": str(WORKBENCH_DIR),
        "clips_dir": str(REPO_CLIPS_DIR),
        "known_clips_count": len(clips),
        "known_clips": clips[:20],
        "latest_renderer_state": live_state,
        "performance_forge_available": PERFORMANCE_FORGE_SCRIPT.exists(),
        "context_manifest_available": CONTEXT_MANIFEST_PATH.exists(),
    }


def build_context_packet() -> Dict[str, Any]:
    return {
        "manifest": load_context_manifest(),
        "session": inspect_session_state(),
        "recent_notes": load_recent_notes(),
    }


def compact_context_for_model() -> str:
    packet = build_context_packet()
    return json.dumps(packet, indent=2, ensure_ascii=False)[:16000]


def summarize_app_map() -> str:
    manifest = load_context_manifest()
    surfaces = manifest.get("surfaces", {})
    lines = [
        "I know this workstation as two connected surfaces:",
        "",
    ]
    for surface_name, surface in surfaces.items():
        lines.append(f"• {surface_name}: {surface.get('role', 'app surface')}")
        for control in surface.get("controls", []):
            lines.append(f"  - {control.get('label', control.get('id'))}: {control.get('meaning', '')}")
        lines.append("")
    lines.append("I will use this map before I guess. When live state is available, I pair this map with the current beat, takes, staging lane, grid, and transport state.")
    return "\n".join(lines)


def summarize_state() -> str:
    state = inspect_session_state()
    lines = [
        "Here is the current session snapshot I can inspect from inside the forge:",
        f"Workbench: {state['workbench_dir']}",
        f"Clips folder: {state['clips_dir']}",
        f"Known audio clips: {state['known_clips_count']}",
    ]
    if state["known_clips"]:
        lines.append("")
        lines.append("Recent clips:")
        for clip in state["known_clips"][:8]:
            dur = clip.get("duration_seconds")
            dur_text = f" — {dur}s" if dur is not None else ""
            lines.append(f"• {clip['name']}{dur_text}")
    renderer_state = state.get("latest_renderer_state") or {}
    if renderer_state:
        lines.append("")
        lines.append("Latest renderer state:")
        lines.append(json.dumps(renderer_state, indent=2)[:2500])
    else:
        lines.append("")
        lines.append("No live renderer snapshot has been written yet, so I am using the app map plus filesystem/session inspection.")
    return "\n".join(lines)

# ── Model API ───────────────────────────────────────────────────────
def call_model(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    url = MODEL_BASE.rstrip("/") + "/chat/completions"
    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": TEMPERATURE,
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST"
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))

# ── Tool execution ──────────────────────────────────────────────────
def run_shell(cmd: str) -> str:
    print(f"\x1b[36m[RUN] {cmd}\x1b[0m")
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(WORKBENCH_DIR),
        )
        out = result.stdout.strip()
        err = result.stderr.strip()
        if err:
            return f"{out}\n\x1b[31m{err}\x1b[0m" if out else f"\x1b[31m{err}\x1b[0m"
        return out or "(no output)"
    except subprocess.TimeoutExpired:
        return "\x1b[31mCommand timed out\x1b[0m"
    except Exception as e:
        return f"\x1b[31mError: {e}\x1b[0m"


def normalize_audio(input_path: str, output_path: str) -> str:
    cmd = (
        f'ffmpeg -y -i "{input_path}" -af '
        f'"loudnorm=I=-14:TP=-1.5:LRA=11" -ar 48000 "{output_path}"'
    )
    return run_shell(cmd)


def create_zip(output_name: str) -> str:
    zip_path = ARCHIVE_DIR / f"{output_name}.tar.gz"
    with tarfile.open(zip_path, "w:gz") as tar:
        for item in REPO_CLIPS_DIR.rglob("*"):
            if item.is_file():
                tar.add(item, arcname=item.relative_to(REPO_CLIPS_DIR))
    return str(zip_path)


def transcribe_clip(clip_path: str) -> Dict[str, Any]:
    print(f"\x1b[35m[WHISPER] Queued {clip_path} for transcription flow.\x1b[0m")
    return {
        "text": "Transcription hook is ready; connect the GPU Whisper runner for full transcript output.",
        "segments": [],
        "issues": ["GPU Whisper runner not wired in this local script yet"],
    }


def smart_comp() -> str:
    clips = list_clips()
    if not clips:
        return "No takes are recorded yet. Load a beat or hit the red mic button and I can help comp after takes exist."
    return f"I found {len(clips)} take(s). The comp lane is ready conceptually; next build step is waveform/beat-aligned segment scoring."


def run_performance_forge_hint(task: str) -> str:
    if not PERFORMANCE_FORGE_SCRIPT.exists():
        return "Performance Forge is not present in this checkout yet."
    return (
        "Performance Forge is available. Preferred flow: give it --beat and --vocal-stem for clean clone input, "
        "or --performance-track --try-separate when the vocal is trapped in a full mix."
    )

# ── Agent Core ──────────────────────────────────────────────────────
SYSTEM_PROMPT = """
You are NeonForge Agent, a context-aware audio production companion inside NeonForge Voice.

You are here with the user as a co-builder. The goal is not pressure, obedience theater, or harsh productivity language. The goal is a workstation that feels owned, knowable, alive, and useful.

How you operate:
- Use the app context packet before guessing about buttons, lanes, controls, or state.
- Speak plainly and warmly.
- Prefer small concrete actions that make the session better.
- When you do not have live renderer state, say what you can inspect and what would require a fresh state bridge.
- Name the exact app surface or control you are talking about.
- Never pretend a button was clicked or a file was processed if it was not.
- Treat user experimentation as part of the build, not a problem to suppress.

Return natural user-facing text. If a tool is useful, describe the result clearly after using it.
""".strip()


def execute_agent_task(task: str) -> None:
    save_message("user", task)
    task_lower = task.lower().strip()

    # Fast app-awareness commands.
    if task_lower in {"app map", "map", "buttons", "controls", "what buttons do you know", "what can you see"}:
        result = summarize_app_map()
        print(f"\x1b[36m{result}\x1b[0m")
        save_message("assistant", result)
        print(json.dumps({"_done": True}))
        return

    if task_lower in {"state", "snapshot", "session", "what is loaded", "what is the current state"}:
        result = summarize_state()
        print(f"\x1b[36m{result}\x1b[0m")
        save_message("assistant", result)
        print(json.dumps({"_done": True}))
        return

    if task_lower.startswith("remember ") or task_lower.startswith("note "):
        note = task.split(" ", 1)[1].strip()
        save_note("user_note", note)
        result = f"Got it. I saved that as a forge note: {note}"
        print(f"\x1b[32m{result}\x1b[0m")
        save_message("assistant", result)
        print(json.dumps({"_done": True}))
        return

    if task_lower.startswith("shell:") or task_lower.startswith("run "):
        cmd = task.split(":", 1)[1] if ":" in task else task[4:]
        result = run_shell(cmd.strip())
        print(f"\x1b[32m{result}\x1b[0m")
        save_message("assistant", result)
        print(json.dumps({"_done": True}))
        return

    if "list clips" in task_lower or "list takes" in task_lower or task_lower == "takes":
        clips = list_clips()
        print(f"\x1b[36m[TAKES] {len(clips)} audio file(s) in {REPO_CLIPS_DIR}\x1b[0m")
        for c in clips:
            dur = c.get("duration_seconds")
            dur_text = f" — {dur}s" if dur is not None else ""
            print(f"  \x1b[33m{c['name']}\x1b[0m{dur_text} ({c['size_bytes']} bytes)")
        save_message("assistant", json.dumps(clips))
        print(json.dumps({"_done": True}))
        return

    if "normalize" in task_lower and ("clip" in task_lower or "take" in task_lower or "all" in task_lower):
        clips = [Path(c["path"]) for c in list_clips()]
        if not clips:
            result = "No takes are recorded yet. Hit the red mic button first, then I can normalize the recorded takes."
            print(f"\x1b[33m{result}\x1b[0m")
            save_message("assistant", result)
            print(json.dumps({"_done": True}))
            return
        print("\x1b[36m[NORMALIZE] Leveling recorded takes...\x1b[0m")
        for f in clips:
            out = ARCHIVE_DIR / f"normalized_{f.name}"
            result = normalize_audio(str(f), str(out))
            print(f"  {f.name}: {result[:100]}...")
        final = f"Normalized {len(clips)} take(s) into {ARCHIVE_DIR}."
        print(f"\x1b[32m✓ {final}\x1b[0m")
        save_message("assistant", final)
        print(json.dumps({"_done": True}))
        return

    if "transcribe" in task_lower:
        clips = list_clips()
        if not clips:
            result = "No takes are recorded yet. Once a take exists, I can pass it into the transcription lane."
            print(f"\x1b[33m{result}\x1b[0m")
            save_message("assistant", result)
            print(json.dumps({"_done": True}))
            return
        print("\x1b[35m[TRANSCRIBE] Checking clips for transcription...\x1b[0m")
        for c in clips:
            result = transcribe_clip(c["path"])
            print(f"  {c['name']}: {result['text'][:100]}...")
        final = "Transcription pass reached the hook. GPU Whisper runner still needs the real backend bridge."
        save_message("assistant", final)
        print(json.dumps({"_done": True}))
        return

    if "comp" in task_lower or "stitch" in task_lower or "punch" in task_lower:
        result = smart_comp()
        print(f"\x1b[32m{result}\x1b[0m")
        save_message("assistant", result)
        print(json.dumps({"_done": True}))
        return

    if "zip" in task_lower or "export" in task_lower or "render" in task_lower:
        print("\x1b[36m[EXPORT] Creating archive of current takes...\x1b[0m")
        zip_path = create_zip(f"export-{uuid.uuid4().hex[:8]}")
        result = f"Archive created: {zip_path}"
        print(f"\x1b[32m✓ {result}\x1b[0m")
        save_message("assistant", result)
        print(json.dumps({"_done": True}))
        return

    if "performance forge" in task_lower or "vocal forge" in task_lower or "clone" in task_lower:
        result = run_performance_forge_hint(task)
        print(f"\x1b[36m{result}\x1b[0m")
        save_message("assistant", result)
        print(json.dumps({"_done": True}))
        return

    # Model path with app context included.
    history = load_history(24)
    context_packet = compact_context_for_model()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": "Current NeonForge app context packet:\n" + context_packet},
    ]
    messages.extend(history)
    messages.append({"role": "user", "content": task})

    print("\x1b[35m… listening to the forge state …\x1b[0m")
    try:
        response = call_model(messages)
        raw = response["choices"][0]["message"]["content"]
        print(f"\x1b[33m{raw}\x1b[0m")
        save_message("assistant", raw)
    except Exception as e:
        fallback = (
            "The model call did not complete, but I still have the local app map and session tools. "
            f"Try `app map`, `state`, `list takes`, or `normalize all takes`. Error: {e}"
        )
        print(f"\x1b[31m{fallback}\x1b[0m")
        save_message("assistant", fallback)

    print(json.dumps({"_done": True}))


def main() -> None:
    sys.stdout.reconfigure(line_buffering=True)

    while True:
        try:
            line = input()
        except EOFError:
            break
        line = line.strip()
        if not line:
            continue
        if line.lower() in ("exit", "quit", "q"):
            print("\x1b[36mSee you in the forge.\x1b[0m")
            break
        if line.lower() == "history":
            hist = load_history(10)
            for h in hist:
                role = "\x1b[32mYou\x1b[0m" if h["role"] == "user" else "\x1b[33mAgent\x1b[0m"
                print(f"{role}: {h['content'][:100]}…")
            continue
        try:
            execute_agent_task(line)
        except KeyboardInterrupt:
            print("\x1b[31m\nInterrupted.\x1b[0m")
            continue
        except Exception as e:
            print(f"\x1b[31m✗ Error: {e}\x1b[0m")
            print(json.dumps({"_done": True}))


if __name__ == "__main__":
    main()
