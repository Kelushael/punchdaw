# Infrastructure Registry
> Last updated: 2026-04-29
> This file is the single source of truth for all domains, hosts, and access methods.

---

## Domain Registry

| Domain | Points To | Purpose | Provider | Managed By |
|---|---|---|---|---|
| `axismundi.fun` | Local Debian box (`axismundi`) | Primary dev machine, main creative hub | — | Local |
| `1playaway.fun` | Same as `axismundi.fun` | Alias / same API endpoint as axismundi | — | Local |
| `markyninox.com` | Hostinger (separate account) | — | Hostinger | Separate login |
| `nosonlastacos.fun` | — | — | — | — |
| `fakie` | — | Project / domain placeholder | — | — |

---

## Hosts & Access

### Local Dev Box — `axismundi`
- **OS:** Debian (GNOME/X11)
- **User:** `marcus` (daily), `root` (admin)
- **Display:** `:0`
- **Audio:** PulseAudio, PreSonus AudioBox USB
- **Key projects:** `/home/marcus/neonslab-voiceforge/`
- **Access:** Physical / local terminal

### VPS — Hostinger (`185.28.23.43`)
- **Provider:** Hostinger
- **IP:** `185.28.23.43`
- **Login:** `ssh root@185.28.23.43`
- **Access from:** Laptop → SSH → this VPS
- **Purpose:** Remote server, nested SSH target

### markyninox.com Hostinger
- **Provider:** Hostinger
- **Note:** Separate Hostinger account from the `185.28.23.43` VPS

---

## GitHub

| Repo | URL | Local Path |
|---|---|---|
| `Kelushael/punchdaw` | https://github.com/Kelushael/punchdaw | `/home/marcus/neonslab-voiceforge` |

### Auth
- **Primary account:** `Kelushael`
- **Token location:** `~/.config/gh/hosts.yml` (fine-grained PAT)
- **Scopes:** `gist`, `read:org`, `repo`
- **Note:** For workflow pushes, need `workflow` scope (use hitlergoyim account or classic PAT)
- **Secondary account:** `hitlergoyim` — has `repo` + `workflow` scope

---

## API Endpoints & Services

| Service | URL / Address | Auth | Notes |
|---|---|---|---|
| Eyes panel | `http://localhost:8282` | None | File watcher daemon (pid=45429) |
| Preview panel | `http://localhost:8181` | None | Preview daemon (pid=45433) |
| GitHub API | `https://api.github.com` | PAT in `~/.config/gh/hosts.yml` | — |

---

## Project Locations

| Project | Path | Repo | Status |
|---|---|---|---|
| NeonForge Voice (DAW) | `/home/marcus/neonslab-voiceforge` | `Kelushael/punchdaw` | Legacy / on hold |
| Vocal Guide | `/home/marcus/neonslab-voiceforge/vocalguide/` | `Kelushael/punchdaw` | ✅ Active |

---

## Secrets Storage

| Secret | Location | Never commit? |
|---|---|---|
| GitHub PAT (Kelushael) | `~/.config/gh/hosts.yml` | ✅ |
| GitHub PAT (hitlergoyim) | `~/.config/gh/hosts.yml` | ✅ |
| SSH keys | `~/.ssh/` | ✅ |

---

## To Complete

- [ ] Add Hostinger panel login URLs for both accounts
- [ ] Add DNS records for `nosonlastacos.fun` and `fakie`
- [ ] Confirm what `1playaway.fun` serves (same API as axismundi?)
- [ ] Add any Cloudflare / CDN details
- [ ] Add API keys for external services (if any)
