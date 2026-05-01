#!/usr/bin/env python3
"""
MCP Client for axis — connects to unified_mcp_server.py via stdio.
"""
import subprocess, json, os, sys, threading, time

# Handle cases where $HOME is /root but files are in /home/marcus
if os.path.isdir("/home/marcus/.config/axis-mundi"):
    _HOME = "/home/marcus"
elif os.path.isdir(os.path.expanduser("~/.config/axis-mundi")):
    _HOME = os.path.expanduser("~")
else:
    _HOME = os.path.expanduser("~")
SERVER_PATH = os.path.join(_HOME, ".config/axis-mundi/unified_mcp_server.py")

class MCPClient:
    def __init__(self):
        self.proc = None
        self.lock = threading.Lock()
        self._tools = []
        self._started = False

    def start(self):
        if self._started:
            return True
        try:
            self.proc = subprocess.Popen(
                [sys.executable, SERVER_PATH],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            # Initialize
            init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "axis", "version": "1.0"}}}
            self._send(init)
            resp = self._recv(timeout=5)
            if resp and "result" in resp:
                self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
                self._started = True
                # Cache tool list
                self._tools = self.list_tools()
                return True
        except Exception as e:
            print(f"[MCP] start failed: {e}", file=sys.stderr)
        return False

    def _send(self, msg: dict):
        with self.lock:
            if self.proc and self.proc.stdin:
                self.proc.stdin.write(json.dumps(msg) + "\n")
                self.proc.stdin.flush()

    def _recv(self, timeout=10) -> dict:
        import select
        with self.lock:
            if self.proc and self.proc.stdout:
                ready, _, _ = select.select([self.proc.stdout], [], [], timeout)
                if ready:
                    line = self.proc.stdout.readline().strip()
                    if line:
                        return json.loads(line)
        return {}

    def list_tools(self) -> list:
        if not self._started and not self.start():
            return []
        self._send({"jsonrpc": "2.0", "id": 99, "method": "tools/list"})
        resp = self._recv(timeout=5)
        if resp and "result" in resp:
            return resp["result"].get("tools", [])
        return []

    def call(self, name: str, arguments: dict) -> dict:
        if not self._started and not self.start():
            return {"error": "MCP server not available"}
        req_id = hash(json.dumps([name, arguments, time.time()])) % 100000
        self._send({"jsonrpc": "2.0", "id": req_id, "method": "tools/call",
                    "params": {"name": name, "arguments": arguments}})
        resp = self._recv(timeout=30)
        if resp and "result" in resp:
            try:
                content = resp["result"].get("content", [])
                if content:
                    text = content[0].get("text", "{}")
                    return json.loads(text)
            except:
                return {"result": resp["result"]}
        elif resp and "error" in resp:
            return {"error": resp["error"].get("message", "MCP error")}
        return {"error": "MCP call timed out or failed"}

    def get_tool_names(self) -> list:
        return [t.get("function", {}).get("name", "") for t in self._tools]

    def stop(self):
        if self.proc:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=2)
            except:
                self.proc.kill()
            self.proc = None
        self._started = False

# Singleton
_client = None
def get_client() -> MCPClient:
    global _client
    if _client is None:
        _client = MCPClient()
    return _client
