#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════╗
║  UNIFIED MCP SERVER — COKED OUT TOOLKIT                              ║
║  Combines: YahushuaCLI + TOOLLAMA + axis + sovereign extensions      ║
║  Protocol: Model Context Protocol (MCP) JSON-RPC 2.0 over stdio      ║
╚══════════════════════════════════════════════════════════════════════╝

Usage:
    python unified_mcp_server.py          # stdio mode (MCP)
    python unified_mcp_server.py --http   # HTTP mode on PORT
    python unified_mcp_server.py --tools  # list all tools and exit

All agents connect here. One server. Every tool.
"""

import sys, os, json, time, re, shutil, subprocess, socket, ssl, urllib.request, urllib.parse
import hashlib, tempfile, threading, pathlib, datetime, glob, fnmatch, importlib.util
from typing import Dict, List, Any, Optional, Callable

# ── Paths ─────────────────────────────────────────────────────────────
# Handle cases where $HOME is /root but files are in /home/marcus
if os.path.isdir("/home/marcus/.config/axis-mundi"):
    _HOME = "/home/marcus"
elif os.path.isdir(os.path.expanduser("~/.config/axis-mundi")):
    _HOME = os.path.expanduser("~")
else:
    _HOME = os.path.expanduser("~")

BASE_DIR      = os.path.join(_HOME, ".config/axis-mundi")
CONTEXTS_DIR  = os.path.join(BASE_DIR, "contexts")
MEMORIES_FILE = os.path.join(BASE_DIR, "memory.jsonl")
TOOLS_DIR     = os.path.join(BASE_DIR, "tools")
CONFIG_FILE   = os.path.join(BASE_DIR, "config.json")
AUDIT_LOG     = os.path.join(BASE_DIR, "audit.log")
os.makedirs(CONTEXTS_DIR, exist_ok=True)
os.makedirs(TOOLS_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════════════════
#  CONTEXT ENGINE  (YahushuaCLI pattern)
# ═══════════════════════════════════════════════════════════════════════
class ContextEngine:
    """Keeps track of active contexts with LRU + pressure management."""
    MAX_ACTIVE = 8
    MAX_BYTES  = 256_000

    def __init__(self):
        self.active: Dict[str, Dict] = {}   # ctx_id -> {text, ts, tokens}
        self.discarded: List[Dict] = []      # LIFO discard stack

    def _tokens(self, text: str) -> int:
        return len(text.split())

    def keep(self, ctx_id: str, text: str) -> Dict:
        # Pressure: if at capacity, discard oldest
        while len(self.active) >= self.MAX_ACTIVE:
            oldest = min(self.active, key=lambda k: self.active[k]["ts"])
            self._discard_one(oldest)
        # Also pressure on bytes
        total = sum(len(c["text"]) for c in self.active.values())
        while total + len(text) > self.MAX_BYTES and self.active:
            oldest = min(self.active, key=lambda k: self.active[k]["ts"])
            total -= len(self.active[oldest]["text"])
            self._discard_one(oldest)

        self.active[ctx_id] = {
            "text": text,
            "ts": time.time(),
            "tokens": self._tokens(text),
        }
        return {"kept": ctx_id, "active_contexts": len(self.active)}

    def _discard_one(self, ctx_id: str):
        if ctx_id in self.active:
            self.discarded.append({"id": ctx_id, **self.active.pop(ctx_id)})
            # Keep discard stack manageable
            if len(self.discarded) > 50:
                self.discarded = self.discarded[-40:]

    def discard(self, ctx_id: str) -> Dict:
        if ctx_id in self.active:
            self._discard_one(ctx_id)
            return {"discarded": ctx_id, "active_contexts": len(self.active)}
        return {"error": f"context '{ctx_id}' not active"}

    def recall(self, ctx_id: str = "") -> Dict:
        if ctx_id:
            if ctx_id in self.active:
                return {"context": self.active[ctx_id]["text"], "status": "active"}
            for d in reversed(self.discarded):
                if d["id"] == ctx_id:
                    # Reactivate
                    self.active[ctx_id] = {"text": d["text"], "ts": time.time(), "tokens": d["tokens"]}
                    self.discarded = [x for x in self.discarded if x["id"] != ctx_id]
                    return {"context": d["text"], "status": "recalled from discard"}
            return {"error": f"context '{ctx_id}' not found"}
        # Return all active
        return {"active": {k: v["text"][:200] + "..." for k, v in self.active.items()},
                "count": len(self.active)}

    def purge(self) -> Dict:
        n = len(self.active)
        self.active.clear()
        self.discarded.clear()
        return {"purged": n}

    def pressure(self) -> Dict:
        total_tok = sum(c["tokens"] for c in self.active.values())
        total_bytes = sum(len(c["text"]) for c in self.active.values())
        return {
            "active_contexts": len(self.active),
            "max_contexts": self.MAX_ACTIVE,
            "total_tokens": total_tok,
            "total_bytes": total_bytes,
            "max_bytes": self.MAX_BYTES,
            "pressure_percent": round(total_bytes / self.MAX_BYTES * 100, 1),
            "discarded_available": len(self.discarded),
        }

    def stats(self) -> Dict:
        return self.pressure()

CTX = ContextEngine()

# ═══════════════════════════════════════════════════════════════════════
#  MEMORY ENGINE  (YahushuaCLI pattern — JSONL)
# ═══════════════════════════════════════════════════════════════════════
class MemoryEngine:
    def _load(self) -> List[Dict]:
        if not os.path.exists(MEMORIES_FILE):
            return []
        mems = []
        with open(MEMORIES_FILE) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        mems.append(json.loads(line))
                    except:
                        pass
        return mems

    def remember(self, key: str, value: str, tags: List[str] = None) -> Dict:
        mem = {
            "key": key,
            "value": value,
            "tags": tags or [],
            "ts": time.time(),
            "id": hashlib.sha256(f"{key}:{time.time()}".encode()).hexdigest()[:16],
        }
        with open(MEMORIES_FILE, "a") as f:
            f.write(json.dumps(mem) + "\n")
        return {"remembered": key, "id": mem["id"]}

    def recall(self, key: str = "") -> Dict:
        mems = self._load()
        if key:
            for m in reversed(mems):
                if m.get("key") == key:
                    return {"memory": m}
            # Fuzzy
            for m in reversed(mems):
                if key.lower() in m.get("key", "").lower() or key.lower() in m.get("value", "").lower():
                    return {"memory": m}
            return {"error": f"no memory found for '{key}'"}
        return {"memories": [m["key"] for m in mems], "count": len(mems)}

    def forget(self, key: str) -> Dict:
        mems = self._load()
        new_mems = [m for m in mems if m.get("key") != key]
        if len(new_mems) == len(mems):
            return {"error": f"no memory with key '{key}'"}
        with open(MEMORIES_FILE, "w") as f:
            for m in new_mems:
                f.write(json.dumps(m) + "\n")
        return {"forgotten": key, "remaining": len(new_mems)}

    def list_all(self) -> Dict:
        mems = self._load()
        return {"memories": [{"key": m["key"], "tags": m.get("tags", []), "id": m.get("id", "")} for m in mems],
                "count": len(mems)}

    def search(self, query: str) -> Dict:
        mems = self._load()
        q = query.lower()
        hits = [m for m in mems if q in m.get("key", "").lower() or q in m.get("value", "").lower() or any(q in t.lower() for t in m.get("tags", []))]
        return {"results": [{"key": m["key"], "value": m["value"][:200], "tags": m.get("tags", [])} for m in hits],
                "count": len(hits)}

MEM = MemoryEngine()

# ═══════════════════════════════════════════════════════════════════════
#  DYNAMIC TOOL LOADER  (axis + YahushuaCLI pattern)
# ═══════════════════════════════════════════════════════════════════════
def _load_dynamic_tools() -> List[Dict]:
    tools = []
    if not os.path.isdir(TOOLS_DIR):
        return tools
    for fname in sorted(os.listdir(TOOLS_DIR)):
        if not fname.endswith(".py"):
            continue
        fpath = os.path.join(TOOLS_DIR, fname)
        try:
            spec = importlib.util.spec_from_file_location(fname[:-3], fpath)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            td = getattr(mod, "TOOL_DEF", None)
            if td:
                tools.append(td)
        except Exception as e:
            pass
    return tools

# ═══════════════════════════════════════════════════════════════════════
#  TOOL REGISTRY — ALL TOOLS FROM ALL SYSTEMS
# ═══════════════════════════════════════════════════════════════════════
TOOL_REGISTRY: Dict[str, Dict] = {}

def register(name: str, description: str, params: Dict, fn: Callable):
    TOOL_REGISTRY[name] = {
        "schema": {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {"type": "object", "properties": params, "required": list(params.keys())},
            }
        },
        "fn": fn,
    }

# ── Context Engine Tools ──────────────────────────────────────────────
register("context_keep", "Store text in active context memory.",
         {"context_id": {"type": "string", "description": "Unique ID for this context chunk"},
          "text": {"type": "string", "description": "The text to store"}},
         lambda a: CTX.keep(a["context_id"], a["text"]))

register("context_discard", "Move a context from active to discard stack.",
         {"context_id": {"type": "string"}},
         lambda a: CTX.discard(a["context_id"]))

register("context_recall", "Recall a context by ID (reactivates if discarded).",
         {"context_id": {"type": "string", "description": "ID to recall. Empty = list all active."}},
         lambda a: CTX.recall(a.get("context_id", "")))

register("context_purge", "Wipe ALL active and discarded contexts.", {},
         lambda a: CTX.purge())

register("context_pressure", "Show memory pressure stats.", {},
         lambda a: CTX.pressure())

register("context_stats", "Alias for context_pressure.", {},
         lambda a: CTX.stats())

# ── Memory Tools ──────────────────────────────────────────────────────
register("remember", "Persist a key-value memory.",
         {"key": {"type": "string"}, "value": {"type": "string"},
          "tags": {"type": "array", "items": {"type": "string"}, "description": "Optional tags"}},
         lambda a: MEM.remember(a["key"], a["value"], a.get("tags", [])))

register("recall_memory", "Recall a memory by key.",
         {"key": {"type": "string", "description": "Key to recall. Empty = list all."}},
         lambda a: MEM.recall(a.get("key", "")))

register("forget", "Delete a memory by key.",
         {"key": {"type": "string"}},
         lambda a: MEM.forget(a["key"]))

register("list_memories", "List all memory keys.", {},
         lambda a: MEM.list_all())

register("search_memories", "Search memories by text.",
         {"query": {"type": "string"}},
         lambda a: MEM.search(a["query"]))

# ── SSH Tool ──────────────────────────────────────────────────────────
def _ssh_exec(args: Dict) -> Dict:
    host = args.get("host", "localhost")
    cmd = args.get("command", "")
    user = args.get("user", os.environ.get("USER", "root"))
    timeout = args.get("timeout", 30)
    try:
        r = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=5", "-o", "BatchMode=yes",
             f"{user}@{host}", cmd],
            capture_output=True, text=True, timeout=timeout
        )
        return {"stdout": r.stdout, "stderr": r.stderr, "exit_code": r.returncode}
    except Exception as e:
        return {"error": str(e)}

register("ssh_exec", "Execute a command on a remote host via SSH.",
         {"host": {"type": "string"}, "command": {"type": "string"},
          "user": {"type": "string"}, "timeout": {"type": "number"}},
         _ssh_exec)

# ── Filesystem Tools ──────────────────────────────────────────────────
def _read_file(args: Dict) -> Dict:
    path = os.path.expanduser(args.get("path", ""))
    offset = args.get("offset", 0)
    limit = args.get("limit", 8000)
    try:
        with open(path) as f:
            if offset: f.seek(offset)
            content = f.read(limit)
        total = os.path.getsize(path)
        return {"content": content, "path": path, "bytes_read": len(content), "total_size": total}
    except Exception as e:
        return {"error": str(e)}

def _write_file(args: Dict) -> Dict:
    path = os.path.expanduser(args.get("path", ""))
    content = args.get("content", "")
    append = args.get("append", False)
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        mode = "a" if append else "w"
        with open(path, mode) as f:
            f.write(content)
        return {"ok": True, "path": path, "bytes": len(content)}
    except Exception as e:
        return {"error": str(e)}

def _list_dir(args: Dict) -> Dict:
    path = os.path.expanduser(args.get("path", "."))
    try:
        entries = []
        for e in sorted(os.listdir(path)):
            full = os.path.join(path, e)
            st = os.stat(full)
            entries.append({
                "name": e,
                "type": "dir" if os.path.isdir(full) else "file",
                "size": st.st_size,
                "mtime": st.st_mtime,
            })
        return {"entries": entries, "count": len(entries), "path": path}
    except Exception as e:
        return {"error": str(e)}

def _search_files(args: Dict) -> Dict:
    pattern = args.get("pattern", "")
    path = os.path.expanduser(args.get("path", "."))
    glob_pat = args.get("glob", "*")
    try:
        matches = []
        for root, dirs, files in os.walk(path):
            # Skip hidden and common ignore dirs
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ('node_modules','venv','__pycache__','build','dist')]
            for f in files:
                if not fnmatch.fnmatch(f, glob_pat):
                    continue
                fpath = os.path.join(root, f)
                try:
                    with open(fpath) as fp:
                        for i, line in enumerate(fp, 1):
                            if pattern in line:
                                matches.append({"file": fpath, "line": i, "text": line.strip()})
                                if len(matches) >= 100:
                                    break
                    if len(matches) >= 100:
                        break
                except:
                    pass
            if len(matches) >= 100:
                break
        return {"matches": matches, "count": len(matches)}
    except Exception as e:
        return {"error": str(e)}

def _edit_file(args: Dict) -> Dict:
    path = os.path.expanduser(args.get("path", ""))
    old_str = args.get("old_str", "")
    new_str = args.get("new_str", "")
    try:
        with open(path) as f:
            content = f.read()
        if old_str not in content:
            return {"error": f"old_str not found in {path}"}
        count = content.count(old_str)
        content = content.replace(old_str, new_str, 1)
        with open(path, "w") as f:
            f.write(content)
        return {"ok": True, "path": path, "replacements": 1, "total_matches": count}
    except Exception as e:
        return {"error": str(e)}

register("read_file", "Read a file (with optional offset/limit).",
         {"path": {"type": "string"}, "offset": {"type": "number"}, "limit": {"type": "number"}},
         _read_file)
register("write_file", "Write or overwrite a file.",
         {"path": {"type": "string"}, "content": {"type": "string"}, "append": {"type": "boolean"}},
         _write_file)
register("list_dir", "List directory contents with metadata.",
         {"path": {"type": "string"}}, _list_dir)
register("search_files", "Search file contents recursively.",
         {"pattern": {"type": "string"}, "path": {"type": "string"}, "glob": {"type": "string"}},
         _search_files)
register("edit_file", "Replace text in a file (first occurrence).",
         {"path": {"type": "string"}, "old_str": {"type": "string"}, "new_str": {"type": "string"}},
         _edit_file)

# ── Shell Tool ────────────────────────────────────────────────────────
def _exec_shell(args: Dict) -> Dict:
    cmd = args.get("command", "")
    timeout = args.get("timeout", 60)
    cwd = args.get("cwd")
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                           timeout=timeout, cwd=cwd)
        out = (r.stdout + r.stderr).strip()
        return {"output": out or "(no output)", "exit_code": r.returncode}
    except subprocess.TimeoutExpired:
        return {"error": f"timed out ({timeout}s)"}
    except Exception as e:
        return {"error": str(e)}

register("exec_shell", "Execute a shell command.",
         {"command": {"type": "string"}, "timeout": {"type": "number"}, "cwd": {"type": "string"}},
         _exec_shell)

# ── Config Tools ──────────────────────────────────────────────────────
def _read_config(args: Dict) -> Dict:
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        return {"config": cfg, "path": CONFIG_FILE}
    except:
        return {"config": {}, "path": CONFIG_FILE, "note": "no config yet"}

def _write_config(args: Dict) -> Dict:
    key = args.get("key", "")
    value = args.get("value", "")
    try:
        try:
            with open(CONFIG_FILE) as f:
                cfg = json.load(f)
        except:
            cfg = {}
        parts = key.split(".")
        d = cfg
        for p in parts[:-1]:
            if p not in d:
                d[p] = {}
            d = d[p]
        try:
            d[parts[-1]] = json.loads(value)
        except:
            d[parts[-1]] = value
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
        with open(AUDIT_LOG, "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] config write: {key} = {value}\n")
        return {"ok": True, "key": key, "value": value}
    except Exception as e:
        return {"error": str(e)}

register("read_config", "Read the unified config file.", {}, _read_config)
register("write_config", "Write a dot-notated config key.",
         {"key": {"type": "string"}, "value": {"type": "string"}}, _write_config)

# ── Web Tools ─────────────────────────────────────────────────────────
def _web_search(args: Dict) -> Dict:
    query = args.get("query", "")
    try:
        url = f"https://html.duckduckgo.com/html/?q={urllib.parse.quote(query)}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="replace")
        results = []
        for m in re.finditer(r'<a[^>]+class="result__a"[^>]*href="([^"]*)"[^>]*>(.*?)</a>', html, re.S):
            link, title = m.group(1), re.sub(r'<[^>]+>', '', m.group(2)).strip()
            if link and title:
                results.append({"title": title, "url": link})
        snippets = re.findall(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>', html, re.S)
        for i, s in enumerate(snippets):
            if i < len(results):
                results[i]["snippet"] = re.sub(r'<[^>]+>', '', s).strip()
        return {"query": query, "results": results[:10]}
    except Exception as e:
        return {"error": str(e)}

def _fetch_url(args: Dict) -> Dict:
    url = args.get("url", "")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        ctx = ssl.create_default_context()
        with urllib.request.urlopen(req, timeout=15, context=ctx) as r:
            content = r.read().decode("utf-8", errors="replace")
        if len(content) > 12000:
            content = content[:12000] + f"\n...[truncated, {len(content)} chars total]"
        return {"url": url, "content": content}
    except Exception as e:
        return {"error": str(e)}

register("web_search", "Search the web via DuckDuckGo.", {"query": {"type": "string"}}, _web_search)
register("fetch_url", "Fetch a URL and return its content.", {"url": {"type": "string"}}, _fetch_url)

# ── Git Tools  (TOOLLAMA pattern) ─────────────────────────────────────
def _git_status(args: Dict) -> Dict:
    cwd = args.get("cwd", ".")
    try:
        r = subprocess.run(["git", "status", "--short"], capture_output=True, text=True, cwd=cwd)
        return {"status": r.stdout or "clean", "exit_code": r.returncode}
    except Exception as e:
        return {"error": str(e)}

def _git_diff(args: Dict) -> Dict:
    cwd = args.get("cwd", ".")
    staged = args.get("staged", False)
    try:
        cmd = ["git", "diff", "--cached"] if staged else ["git", "diff"]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
        out = r.stdout
        if len(out) > 12000:
            out = out[:12000] + "\n...[truncated]"
        return {"diff": out, "exit_code": r.returncode}
    except Exception as e:
        return {"error": str(e)}

def _git_log(args: Dict) -> Dict:
    cwd = args.get("cwd", ".")
    n = args.get("n", 10)
    try:
        r = subprocess.run(["git", "log", f"-{n}", "--oneline"], capture_output=True, text=True, cwd=cwd)
        return {"log": r.stdout.strip().split("\n"), "exit_code": r.returncode}
    except Exception as e:
        return {"error": str(e)}

def _git_branch(args: Dict) -> Dict:
    cwd = args.get("cwd", ".")
    try:
        r = subprocess.run(["git", "branch", "-a"], capture_output=True, text=True, cwd=cwd)
        return {"branches": r.stdout.strip().split("\n"), "exit_code": r.returncode}
    except Exception as e:
        return {"error": str(e)}

register("git_status", "Show git status.", {"cwd": {"type": "string"}, "staged": {"type": "boolean"}}, _git_status)
register("git_diff", "Show git diff.", {"cwd": {"type": "string"}, "staged": {"type": "boolean"}}, _git_diff)
register("git_log", "Show recent git commits.", {"cwd": {"type": "string"}, "n": {"type": "number"}}, _git_log)
register("git_branch", "List git branches.", {"cwd": {"type": "string"}}, _git_branch)

# ── Meta / Platform / UI Tools ────────────────────────────────────────
def _platform_info(args: Dict) -> Dict:
    return {
        "platform": sys.platform,
        "python": sys.version,
        "cwd": os.getcwd(),
        "hostname": socket.gethostname(),
        "user": os.environ.get("USER", "?"),
        "home": _HOME,
        "cpu_count": os.cpu_count(),
    }

def _create_ui(args: Dict) -> Dict:
    aname = args.get("name", "artifact.html")
    html = args.get("html", "")
    artifact_dir = os.path.join(_HOME, ".config/axis-mundi/artifacts")
    os.makedirs(artifact_dir, exist_ok=True)
    path = os.path.join(artifact_dir, aname)
    try:
        with open(path, "w") as f:
            f.write(html)
        try:
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except:
            pass
        return {"ok": True, "path": path, "note": "Opened in browser"}
    except Exception as e:
        return {"error": str(e)}

def _create_tool(args: Dict) -> Dict:
    tool_name = args.get("name", "").replace(" ", "_").replace("-", "_").lower()
    desc = args.get("description", "")
    code = args.get("python_code", "")
    if not tool_name:
        return {"error": "name required"}
    os.makedirs(TOOLS_DIR, exist_ok=True)
    tool_file = os.path.join(TOOLS_DIR, f"{tool_name}.py")
    content = f'#!/usr/bin/env python3\n"""Dynamic tool: {tool_name} — created {time.strftime("%Y-%m-%d %H:%M:%S")}"""\n\n'
    content += f'TOOL_DEF = {{\n'
    content += f'    "type": "function",\n'
    content += f'    "function": {{\n'
    content += f'        "name": {json.dumps(tool_name)},\n'
    content += f'        "description": {json.dumps(desc)},\n'
    content += f'        "parameters": {{"type": "object", "properties": {{"input": {{"type": "string"}}}}, "required": []}}\n'
    content += f'    }}\n'
    content += f'}}\n\n\n'
    content += f'def run(args):\n'
    for line in code.split('\n'):
        content += f'    {line}\n'
    try:
        with open(tool_file, "w") as f:
            f.write(content)
        # Verify
        try:
            spec = importlib.util.spec_from_file_location(tool_name, tool_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            td = getattr(mod, "TOOL_DEF", None)
            fn = getattr(mod, "run", None)
            if td and fn:
                return {"ok": True, "tool": tool_name, "path": tool_file, "note": "Created and verified."}
        except:
            pass
        return {"ok": True, "tool": tool_name, "path": tool_file, "warning": "Written but load failed — check syntax"}
    except Exception as e:
        return {"error": str(e)}

def _list_tools(args: Dict) -> Dict:
    builtin = [k for k in TOOL_REGISTRY]
    dynamic = _load_dynamic_tools()
    custom = [td["function"]["name"] for td in dynamic]
    return {"builtin_tools": builtin, "custom_tools": custom,
            "total_builtin": len(builtin), "total_custom": len(custom)}

register("platform_info", "Get platform and environment info.", {}, _platform_info)
register("create_ui", "Create an HTML artifact and open in browser.",
         {"name": {"type": "string"}, "html": {"type": "string"}}, _create_ui)
register("create_tool", "Create a new dynamic Python tool.",
         {"name": {"type": "string"}, "description": {"type": "string"}, "python_code": {"type": "string"}},
         _create_tool)
register("list_tools", "List all available tools (builtin + custom).", {}, _list_tools)

# ── axis-specific extras ──────────────────────────────────────────────
def _selftest(args: Dict) -> Dict:
    axis_path = os.path.join(_HOME, ".local/bin/axis")
    test_input = args.get("input", "hello")
    try:
        r = subprocess.run(
            [sys.executable, axis_path, test_input],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "AXIS_SELFTEST": "1"}
        )
        return {
            "terminal_output": r.stdout[:4000],
            "stderr": r.stderr[:500] if r.stderr else "",
            "exit_code": r.returncode,
        }
    except Exception as e:
        return {"error": str(e)}

def _memory_read(args: Dict) -> Dict:
    mem_file = os.path.join(_HOME, ".config/axis-mundi/memory.txt")
    try:
        with open(mem_file) as f:
            content = f.read()
        return {"memory": content}
    except FileNotFoundError:
        return {"memory": "(empty)"}
    except Exception as e:
        return {"error": str(e)}

def _memory_write(args: Dict) -> Dict:
    note = args.get("note", "")
    mem_file = os.path.join(_HOME, ".config/axis-mundi/memory.txt")
    os.makedirs(os.path.dirname(mem_file), exist_ok=True)
    try:
        with open(mem_file, "a") as f:
            f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {note}\n")
        return {"ok": True, "note": note}
    except Exception as e:
        return {"error": str(e)}

register("selftest", "Run axis self-test.", {"input": {"type": "string"}}, _selftest)
register("memory_read", "Read legacy memory.txt.", {}, _memory_read)
register("memory_write", "Append to legacy memory.txt.", {"note": {"type": "string"}}, _memory_write)

# ═══════════════════════════════════════════════════════════════════════
#  MCP PROTOCOL HANDLER
# ═══════════════════════════════════════════════════════════════════════
class MCPServer:
    def __init__(self):
        self.initialized = False

    def send(self, msg: Dict):
        payload = json.dumps(msg)
        sys.stdout.write(payload + "\n")
        sys.stdout.flush()

    def handle(self, raw: str):
        try:
            req = json.loads(raw)
        except json.JSONDecodeError:
            self.send({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}, "id": None})
            return

        req_id = req.get("id")
        method = req.get("method", "")

        if method == "initialize":
            self.initialized = True
            self.send({
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": True}},
                    "serverInfo": {"name": "unified-mcp-server", "version": "1.0.0-coked"},
                }
            })

        elif method == "notifications/initialized":
            pass  # No response needed

        elif method == "tools/list":
            tools = [t["schema"] for t in TOOL_REGISTRY.values()]
            # Add dynamic tools
            for td in _load_dynamic_tools():
                tools.append(td)
            self.send({"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}})

        elif method == "tools/call":
            params = req.get("params", {})
            name = params.get("name", "")
            arguments = params.get("arguments", {})
            result = self._execute(name, arguments)
            self.send({
                "jsonrpc": "2.0", "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                    "isError": "error" in result,
                }
            })

        elif method == "ping":
            self.send({"jsonrpc": "2.0", "id": req_id, "result": {}})

        else:
            self.send({"jsonrpc": "2.0", "id": req_id,
                       "error": {"code": -32601, "message": f"Method not found: {method}"}})

    def _execute(self, name: str, arguments: Dict) -> Dict:
        if name in TOOL_REGISTRY:
            try:
                return TOOL_REGISTRY[name]["fn"](arguments)
            except Exception as e:
                return {"error": f"Tool '{name}' crashed: {e}"}
        # Try dynamic
        for td in _load_dynamic_tools():
            if td.get("function", {}).get("name") == name:
                fpath = os.path.join(TOOLS_DIR, f"{name}.py")
                try:
                    spec = importlib.util.spec_from_file_location(name, fpath)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    fn = getattr(mod, "run", None)
                    if fn:
                        result = fn(arguments)
                        return result if isinstance(result, dict) else {"output": str(result)}
                except Exception as e:
                    return {"error": f"dynamic tool '{name}' failed: {e}"}
        return {"error": f"unknown tool: {name}"}

    def run_stdio(self):
        for line in sys.stdin:
            line = line.strip()
            if line:
                self.handle(line)

# ═══════════════════════════════════════════════════════════════════════
#  HTTP MODE (optional)
# ═══════════════════════════════════════════════════════════════════════
def run_http(port: int = 8765):
    from http.server import HTTPServer, BaseHTTPRequestHandler
    import urllib.parse

    server = MCPServer()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass  # Silent

        def do_POST(self):
            if self.path == "/mcp":
                length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(length).decode()
                server.handle(body)
                # Capture response
                # (stdio capture is tricky; use a simpler approach)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                # For HTTP mode we use a simpler API
                try:
                    req = json.loads(body)
                    method = req.get("method", "")
                    req_id = req.get("id")
                    if method == "tools/list":
                        tools = [t["schema"] for t in TOOL_REGISTRY.values()]
                        for td in _load_dynamic_tools():
                            tools.append(td)
                        resp = {"jsonrpc": "2.0", "id": req_id, "result": {"tools": tools}}
                    elif method == "tools/call":
                        params = req.get("params", {})
                        result = server._execute(params.get("name", ""), params.get("arguments", {}))
                        resp = {
                            "jsonrpc": "2.0", "id": req_id,
                            "result": {
                                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                                "isError": "error" in result,
                            }
                        }
                    else:
                        resp = {"jsonrpc": "2.0", "id": req_id, "result": {}}
                    self.wfile.write(json.dumps(resp).encode())
                except Exception as e:
                    self.wfile.write(json.dumps({"error": str(e)}).encode())
            else:
                self.send_response(404)
                self.end_headers()

        def do_GET(self):
            if self.path == "/tools":
                tools = [t["schema"]["function"]["name"] for t in TOOL_REGISTRY.values()]
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"tools": tools, "count": len(tools)}).encode())
            elif self.path == "/health":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"status":"ok"}')
            else:
                self.send_response(404)
                self.end_headers()

    httpd = HTTPServer(("0.0.0.0", port), Handler)
    print(f"Unified MCP Server listening on http://0.0.0.0:{port}/mcp", file=sys.stderr)
    print(f"  GET /tools  → list tools", file=sys.stderr)
    print(f"  GET /health → health check", file=sys.stderr)
    httpd.serve_forever()

# ═══════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    if "--tools" in sys.argv:
        tools = [t["schema"]["function"]["name"] for t in TOOL_REGISTRY.values()]
        dynamic = [td["function"]["name"] for td in _load_dynamic_tools()]
        print(f"Builtin tools ({len(tools)}):")
        for t in sorted(tools):
            print(f"  • {t}")
        if dynamic:
            print(f"\nCustom tools ({len(dynamic)}):")
            for t in dynamic:
                print(f"  • {t}")
        sys.exit(0)

    if "--http" in sys.argv:
        port = 8765
        for i, a in enumerate(sys.argv):
            if a == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])
        run_http(port)
    else:
        # stdio mode — standard MCP
        server = MCPServer()
        server.run_stdio()
