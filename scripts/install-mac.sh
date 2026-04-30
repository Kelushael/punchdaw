#!/usr/bin/env bash
#
# NeonForge Voice — macOS Installer (Download & Open .pkg)
#
# One-liner:
#   curl -fsSL https://neonslab.io/install-mac | bash
#
# What this does:
#   1. Detects your Mac (Intel or Apple Silicon)
#   2. Downloads the latest .pkg from GitHub releases
#   3. Opens it in Installer.app — you click Next → Next → Finish
#   4. App lands in /Applications, shows up in Finder
#
# SAFE: This script ONLY downloads and opens a file. It does NOT delete
#       anything. Your apps, songs, and documents are untouched.
#
set -euo pipefail

REPO="Kelushael/punchdaw"
TMPDIR="$(mktemp -d)"
ARCH=$(uname -m)

# ── Colors ──
GRN='\033[0;32m'
CYAN='\033[0;36m'
YEL='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()  { printf "${GRN}✓${NC} %s\n" "$*"; }
log() { printf "${CYAN}▸${NC} %s\n" "$*"; }
warn(){ printf "${YEL}⚠${NC} %s\n" "$*"; }
die() { printf "${RED}✗${NC} %s\n" "$*" >&2; exit 1; }

# ── Safety check ──
[[ "$OSTYPE" == "darwin"* ]] || die "This installer is for macOS only."

log "NeonForge Voice — macOS Installer"
log "Architecture: $ARCH"

# ── Fetch latest release info ──
log "Finding latest release…"
API_URL="https://api.github.com/repos/$REPO/releases/latest"
RELEASE_JSON=$(curl -fsSL "$API_URL" 2>/dev/null) || die "Cannot reach GitHub. Check your internet."

VERSION=$(echo "$RELEASE_JSON" | grep '"tag_name":' | head -1 | sed 's/.*"tag_name": "\(.*\)".*/\1/')
ok "Latest version: $VERSION"

# ── Pick the right package ──
# Apple Silicon → *-arm64.pkg
# Intel         → *.pkg (but not arm64)
if [[ "$ARCH" == "arm64" ]]; then
  PKG_URL=$(echo "$RELEASE_JSON" | grep '"browser_download_url":' | grep 'arm64.pkg' | head -1 | sed 's/.*"browser_download_url": "\(.*\)".*/\1/')
else
  PKG_URL=$(echo "$RELEASE_JSON" | grep '"browser_download_url":' | grep '\.pkg' | grep -v 'arm64' | head -1 | sed 's/.*"browser_download_url": "\(.*\)".*/\1/')
fi

# Fallback: grab any .pkg if arch-specific not found
[[ -z "$PKG_URL" ]] && PKG_URL=$(echo "$RELEASE_JSON" | grep '"browser_download_url":' | grep '\.pkg' | head -1 | sed 's/.*"browser_download_url": "\(.*\)".*/\1/')

[[ -z "$PKG_URL" ]] && die "No .pkg found in release $VERSION"
ok "Package: $(basename "$PKG_URL")"

# ── Download ──
PKG_FILE="$TMPDIR/$(basename "$PKG_URL")"
log "Downloading…"
curl -fSL --progress-bar "$PKG_URL" -o "$PKG_FILE"
ok "Downloaded to $PKG_FILE"

# ── Verify ──
if [[ ! -f "$PKG_FILE" ]] || [[ ! -s "$PKG_FILE" ]]; then
  die "Download failed — file is missing or empty"
fi

# ── Open in Installer.app ──
log "Opening Installer.app…"
echo ""
echo "${YEL}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo "${YEL}  Click ${BOLD}Continue → Continue → Agree → Install${NC}${YEL} in the wizard${NC}"
echo "${YEL}  Enter your Mac login password when asked${NC}"
echo "${YEL}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

open "$PKG_FILE"

# ── Wait for install ──
sleep 2

# Check if app exists
if [[ -d "/Applications/NeonForge Voice.app" ]]; then
  ok "App detected in /Applications"
  echo ""
  echo "${GRN}🚀 Launch:  open '/Applications/NeonForge Voice.app'${NC}"
else
  warn "Installer is still running. Check the wizard window."
fi

# Cleanup temp dir on exit
trap 'rm -rf "$TMPDIR"' EXIT
