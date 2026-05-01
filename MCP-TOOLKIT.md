# 🔥 Unified MCP Toolkit — COKED OUT

**One server. Every tool. All agents.**

This directory contains the unified MCP (Model Context Protocol) server that merges the best tools from **YahushuaCLI**, **TOOLLAMA**, and **axis** into a single JSON-RPC endpoint.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    UNIFIED MCP SERVER                        │
│              (mcp/unified_mcp_server.py)                     │
│                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ YahushuaCLI │  │  TOOLLAMA   │  │       axis          │  │
│  │ 20 tools    │  │  git + code │  │ exec, web, files    │  │
│  │ context     │  │   tools     │  │ memory, selftest    │  │
│  │ memory      │  │             │  │                     │  │
│  │ ssh         │  │             │  │                     │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         └─────────────────┴────────────────────┘              │
│                           │                                  │
│                    ┌──────┴──────┐                           │
│                    │  33 tools   │                           │
│                    │  + dynamic  │                           │
│                    └──────┬──────┘                           │
│                           │                                  │
│              JSON-RPC 2.0 over stdio / HTTP                  │
└───────────────────────────┬─────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   ┌────┴────┐        ┌────┴────┐        ┌────┴────┐
   │  axis   │        │ Claude  │        │  Other  │
   │ (patched)│        │ Desktop │        │  MCP    │
   │         │        │         │        │ clients │
   └─────────┘        └─────────┘        └─────────┘
```

---

## Quick Start

### 1. List all tools

```bash
python3 mcp/unified_mcp_server.py --tools
```

### 2. Run in stdio mode (MCP standard)

```bash
python3 mcp/unified_mcp_server.py
```

### 3. Run in HTTP mode (for external agents)

```bash
python3 mcp/unified_mcp_server.py --http --port 8765
```

Then query:
```bash
curl http://localhost:8765/health
curl http://localhost:8765/tools
curl -X POST http://localhost:8765/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"platform_info","arguments":{}}}'
```

### 4. axis integration (patched)

axis now auto-detects the unified MCP server. If a tool isn't built into axis, it falls back to the MCP server.

```bash
axis "/tools"          # see all 33+ tools
axis "use context_keep to save this idea"  # MCP tool via axis
```

---

## Tool Inventory (33 builtin + dynamic)

### Context Engine (YahushuaCLI)
| Tool | Description |
|------|-------------|
| `context_keep` | Store text in active context |
| `context_discard` | Move context to discard stack |
| `context_recall` | Recall a context (reactivates if discarded) |
| `context_purge` | Wipe all contexts |
| `context_pressure` | Show memory pressure stats |
| `context_stats` | Alias for context_pressure |

### Memory (YahushuaCLI)
| Tool | Description |
|------|-------------|
| `remember` | Persist key-value memory with tags |
| `recall_memory` | Recall by key |
| `forget` | Delete a memory |
| `list_memories` | List all memory keys |
| `search_memories` | Search by text |

### SSH (YahushuaCLI)
| Tool | Description |
|------|-------------|
| `ssh_exec` | Execute command on remote host |

### Filesystem (combined)
| Tool | Description |
|------|-------------|
| `read_file` | Read file with offset/limit |
| `write_file` | Write/append file |
| `list_dir` | List directory with metadata |
| `search_files` | Recursive file content search |
| `edit_file` | Search/replace in file |

### Shell (combined)
| Tool | Description |
|------|-------------|
| `exec_shell` | Execute shell command |

### Config (combined)
| Tool | Description |
|------|-------------|
| `read_config` | Read JSON config |
| `write_config` | Write dot-notated config key |

### Web (axis)
| Tool | Description |
|------|-------------|
| `web_search` | DuckDuckGo search |
| `fetch_url` | Fetch URL content |

### Git (TOOLLAMA)
| Tool | Description |
|------|-------------|
| `git_status` | Git status |
| `git_diff` | Git diff (optionally staged) |
| `git_log` | Recent commits |
| `git_branch` | List branches |

### Meta / Platform
| Tool | Description |
|------|-------------|
| `platform_info` | OS, Python, hostname, CPU |
| `create_ui` | Create HTML artifact + open browser |
| `create_tool` | Create dynamic Python tool |
| `list_tools` | List all tools |
| `selftest` | Run axis self-test |
| `memory_read` | Read legacy memory.txt |
| `memory_write` | Append to legacy memory.txt |

### Dynamic Tools
Drop `.py` files into `~/.config/axis-mundi/tools/` with a `TOOL_DEF` dict and `run(args)` function. They auto-register.

---

## Protocol

### Initialize
```json
{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "client", "version": "1.0"}}}
```

### List Tools
```json
{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
```

### Call Tool
```json
{"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "platform_info", "arguments": {}}}
```

### Ping
```json
{"jsonrpc": "2.0", "id": 4, "method": "ping"}
```

---

## Files

| File | Purpose |
|------|---------|
| `mcp/unified_mcp_server.py` | The unified MCP server (33+ tools) |
| `mcp/mcp_client.py` | Python MCP client for stdio connections |
| `~/.config/axis-mundi/unified_mcp_server.py` | Live installed server |
| `~/.config/axis-mundi/mcp_client.py` | Live installed client |
| `~/.local/bin/unified-mcp` | Launcher script |
| `~/.local/bin/axis` | Patched axis CLI (MCP fallback) |

---

## Integration Notes

- **axis**: Patched to start MCP server as subprocess on first tool use. Falls back to MCP for unknown tools. System prompt includes MCP tool list dynamically.
- **Claude Desktop**: Add to `claude_desktop_config.json` as a stdio server pointing to `python3 /home/marcus/.config/axis-mundi/unified_mcp_server.py`
- **TOOLLAMA**: Can be reconfigured to use this server instead of its own hub
- **HTTP clients**: Any HTTP client can POST to `/mcp` with JSON-RPC

---

## Status

✅ Unified MCP server with 33 tools  
✅ HTTP + stdio dual mode  
✅ axis patched with MCP fallback  
✅ Context engine with LRU + pressure  
✅ Memory engine with tags + search  
✅ Dynamic tool loading  
✅ Git tools  
✅ Web tools  
✅ SSH tool  
✅ Platform detection  

**Next**: Wire into vocalguide as the "brain" — the MCP server can read guide.json, control playback, and generate new guides on demand.
