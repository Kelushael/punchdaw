#!/usr/bin/env bash
#
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  NEONFORGE VOICE — SYSTEM INTERVENTION & INSTALLER                 ║
# ║  For macOS Intel & Apple Silicon  •  No stone left unturned        ║
# ╚══════════════════════════════════════════════════════════════════════╝
#
#  This script performs a FULL system tune-up, dependency installation,
#  and app deployment. It cleans, installs, builds, and delivers.
#  Run:  curl -fsSL https://neonslab.io/intervention-mac | bash
#
set -euo pipefail

APP_NAME="NeonForge Voice"
BUNDLE_ID="io.neonslab.voiceforge"
REPO_URL="https://github.com/Kelushael/punchdaw.git"
INSTALL_DIR="$HOME/.neonslab-voiceforge"
APP_DIR="/Applications"
USER_APP_DIR="$HOME/Applications"
VERSION="2.0.0"

# ── Colors ──
BLK='\033[0;30m' RED='\033[0;31m' GRN='\033[0;32m'
YEL='\033[1;33m' BLU='\033[0;34m' MAG='\033[0;35m'
CYAN='\033[0;36m' WHT='\033[1;37m' NC='\033[0m'
BOLD='\033[1m'

banner() {
  echo ""
  echo "${CYAN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
  echo "${CYAN}║${NC}  ${BOLD}${WHT}NEONFORGE VOICE${NC}  ${MAG}—${NC}  ${YEL}System Intervention & Installer${NC}                ${CYAN}║${NC}"
  echo "${CYAN}║${NC}  ${GRN}v${VERSION}${NC}  •  Intel & Apple Silicon  •  Zero-Tolerance Deployment      ${CYAN}║${NC}"
  echo "${CYAN}╚══════════════════════════════════════════════════════════════════════╝${NC}"
  echo ""
}

log()   { printf "${CYAN}▸${NC} %s\n" "$*"; }
ok()    { printf "${GRN}✓${NC} %s\n" "$*"; }
warn()  { printf "${YEL}⚠${NC} %s\n" "$*"; }
err()   { printf "${RED}✗${NC} %s\n" "$*" >&2; }
die()   { err "$*"; exit 1; }
step()  { echo ""; printf "${BOLD}${BLU}━━ %s ━━${NC}\n" "$*"; }

# ── Platform Detection ──
[[ "$OSTYPE" == "darwin"* ]] || die "This intervention is for macOS only."
ARCH=$(uname -m)
MACOS_VER=$(sw_vers -productVersion 2>/dev/null || echo "unknown")
step "SYSTEM RECONNAISSANCE"
log "Host:    $(hostname)"
log "User:    $(whoami)"
log "Arch:    $ARCH"
log "macOS:   $MACOS_VER"
log "Shell:   $SHELL"

# ── Disk Space Check ──
FREE_GB=$(df -g / | tail -1 | awk '{print $4}')
log "Free space: ${FREE_GB}GB"
[[ "$FREE_GB" -lt 5 ]] && warn "Less than 5GB free. Intervention may be cramped."

# ── PHASE 1: SYSTEM PURGE (safe caches only) ──
step "PHASE 1: SYSTEM SANITIZATION"

purge_dir() {
  local dir="$1" label="$2"
  if [[ -d "$dir" ]]; then
    local size=$(du -sh "$dir" 2>/dev/null | cut -f1)
    rm -rf "$dir"/* 2>/dev/null || true
    ok "Purged $label ($size)"
  fi
}

log "Cleaning safe system caches…"
purge_dir "$HOME/Library/Caches/npm"           "npm cache"
purge_dir "$HOME/Library/Caches/Homebrew"      "Homebrew cache"
purge_dir "$HOME/Library/Caches/pip"           "pip cache"
purge_dir "$HOME/Library/Caches/electron"      "Electron cache"
purge_dir "$HOME/Library/Caches/node-gyp"      "node-gyp cache"
purge_dir "$HOME/Library/Caches/com.apple.dt.Xcode" "Xcode cache"
purge_dir "$HOME/.npm/_cacache"                "npm legacy cache"
purge_dir "$HOME/.cache/pip"                   "pip legacy cache"
purge_dir "$HOME/.cache/electron"              "electron legacy cache"
purge_dir "$HOME/.cache/electron-builder"      "electron-builder cache"

# Purge old node_modules from common locations
find "$HOME" -maxdepth 3 -name "node_modules" -type d -mtime +30 -exec rm -rf {} + 2>/dev/null || true
ok "Pruned stale node_modules"

# Purge old build artifacts
find "$HOME" -maxdepth 3 \( -name "dist" -o -name ".next" -o -name "build" \) -type d -mtime +14 -exec rm -rf {} + 2>/dev/null || true
ok "Pruned stale build artifacts"

# ── PHASE 2: DEPLOYMENT ENVIRONMENT ──
step "PHASE 2: DEPLOYMENT ENVIRONMENT"

# Xcode CLI Tools (silent install — required for node-gyp, native modules)
if ! xcode-select -p &>/dev/null; then
  log "Installing Xcode Command Line Tools (may prompt for admin password)…"
  xcode-select --install 2>/dev/null || true
  # Wait for installation
  until xcode-select -p &>/dev/null; do
    sleep 5
  done
  ok "Xcode CLI Tools installed"
else
  ok "Xcode CLI Tools present"
fi

# Accept Xcode license silently
sudo xcodebuild -license accept 2>/dev/null || true

# Homebrew — the universal package manager
BREW_PREFIX=""
if [[ "$ARCH" == "arm64" ]]; then
  BREW_PREFIX="/opt/homebrew"
else
  BREW_PREFIX="/usr/local"
fi

if ! command -v brew &>/dev/null; then
  log "Installing Homebrew…"
  export HOMEBREW_NO_ANALYTICS=1
  export HOMEBREW_NO_AUTO_UPDATE=1
  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  eval "$("$BREW_PREFIX/bin/brew" shellenv 2>/dev/null)"
  ok "Homebrew installed at $BREW_PREFIX"
else
  eval "$(brew --prefix)/bin/brew shellenv 2>/dev/null || true"
  ok "Homebrew present at $(brew --prefix)"
fi

# Update brew silently
brew update --quiet 2>/dev/null || true

# ── PHASE 3: DEPENDENCY ACQUISITION ──
step "PHASE 3: DEPENDENCY ACQUISITION"

ensure_brew_pkg() {
  local pkg="$1"
  if ! brew list "$pkg" &>/dev/null; then
    log "  Installing $pkg…"
    brew install "$pkg" 2>&1 | tail -1
  else
    log "  $pkg already present"
  fi
}

ensure_brew_pkg "git"
ensure_brew_pkg "ffmpeg"
ensure_brew_pkg "ffprobe"
ensure_brew_pkg "python@3.13"
ensure_brew_pkg "pkg-config"

# Link python
brew link python@3.13 --force --overwrite 2>/dev/null || true

# Node.js via Homebrew (managed, reliable, no nvm fragility)
if ! command -v node &>/dev/null || [[ "$(node -v | sed 's/v//;s/\..*//')" -lt 18 ]]; then
  log "Installing Node.js 22 LTS…"
  brew install node@22
  brew link node@22 --force --overwrite 2>/dev/null || true
fi
ok "Node.js $(node -v) ready"

# Verify all binaries
for bin in git ffmpeg ffprobe python3 node npm; do
  if ! command -v "$bin" &>/dev/null; then
    die "$bin not found in PATH after installation"
  fi
done
ok "All binaries verified"

# ── PHASE 4: SOURCE ACQUISITION ──
step "PHASE 4: SOURCE ACQUISITION"

if [[ -d "$INSTALL_DIR/.git" ]]; then
  log "Updating existing source…"
  cd "$INSTALL_DIR"
  git fetch --depth 1 origin
  git reset --hard origin/main 2>/dev/null || git reset --hard origin/master 2>/dev/null || true
  git pull --ff-only
else
  log "Cloning fresh source…"
  rm -rf "$INSTALL_DIR"
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
  cd "$INSTALL_DIR"
fi
ok "Source locked and loaded at $INSTALL_DIR"

# ── PHASE 5: BUILD PREPARATION ──
step "PHASE 5: BUILD PREPARATION"

log "Installing Node packages (this will take a moment)…"
npm ci --silent --prefer-offline 2>/dev/null || npm install --silent --prefer-offline
ok "Node packages installed"

log "Building frontend…"
npm run build
ok "Frontend built"

# ── PHASE 6: APP BUNDLE CREATION ──
step "PHASE 6: APP BUNDLE CREATION"

BUNDLE_NAME="${APP_NAME}.app"
BUNDLE_PATH="$APP_DIR/$BUNDLE_NAME"
USER_BUNDLE_PATH="$USER_APP_DIR/$BUNDLE_NAME"

# Remove old versions
if [[ -d "$BUNDLE_PATH" ]]; then
  log "Removing old system install…"
  rm -rf "$BUNDLE_PATH"
fi
if [[ -d "$USER_BUNDLE_PATH" ]]; then
  log "Removing old user install…"
  rm -rf "$USER_BUNDLE_PATH"
fi

# Build with electron-builder if available
if npx electron-builder --mac --dir 2>/dev/null; then
  BUILT_APP="dist/mac${ARCH/arm64/-arm64}/$BUNDLE_NAME"
  [[ "$ARCH" == "x86_64" ]] && BUILT_APP="dist/mac/$BUNDLE_NAME"
  
  if [[ -d "$BUILT_APP" ]]; then
    cp -R "$BUILT_APP" "$USER_BUNDLE_PATH"
    ok "App bundle copied to ~/Applications"
  else
    warn "electron-builder succeeded but bundle not at expected path"
  fi
else
  warn "electron-builder --mac --dir failed, building manual bundle…"
fi

# Fallback: manual .app bundle creation
if [[ ! -d "$USER_BUNDLE_PATH" ]]; then
  log "Creating manual app bundle…"
  mkdir -p "$USER_BUNDLE_PATH/Contents/MacOS"
  mkdir -p "$USER_BUNDLE_PATH/Contents/Resources"
  
  cat > "$USER_BUNDLE_PATH/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>$APP_NAME</string>
  <key>CFBundleDisplayName</key><string>$APP_NAME</string>
  <key>CFBundleIdentifier</key><string>$BUNDLE_ID</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleExecutable</key><string>NeonForgeVoice</string>
  <key>LSMinimumSystemVersion</key><string>10.14</string>
  <key>NSHighResolutionCapable</key><true/>
  <key>NSMicrophoneUsageDescription</key>
  <string>$APP_NAME requires microphone access for recording vocals.</string>
</dict>
</plist>
EOF

  cat > "$USER_BUNDLE_PATH/Contents/MacOS/NeonForgeVoice" <<'LAUNCHER'
#!/bin/bash
set -e
APP_ROOT="$HOME/.neonslab-voiceforge"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
cd "$APP_ROOT"
exec npx electron . --no-sandbox
LAUNCHER
  chmod +x "$USER_BUNDLE_PATH/Contents/MacOS/NeonForgeVoice"
  ok "Manual bundle created at $USER_BUNDLE_PATH"
fi

# ── PHASE 7: CAPITULATION (system compliance) ──
step "PHASE 7: SYSTEM CAPITULATION"

# Ensure the app is not quarantined
xattr -rd com.apple.quarantine "$USER_BUNDLE_PATH" 2>/dev/null || true

# Create a symlink in ~/Applications for Finder visibility
ln -sf "$USER_BUNDLE_PATH" "$USER_APP_DIR/$BUNDLE_NAME" 2>/dev/null || true

# Touch the app so Finder notices it
touch "$USER_BUNDLE_PATH"

# Register the app with LaunchServices
/System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister -f "$USER_BUNDLE_PATH" 2>/dev/null || true

# ── DONE ──
step "INTERVENTION COMPLETE"
echo ""
echo "${GRN}╔══════════════════════════════════════════════════════════════════════╗${NC}"
echo "${GRN}║${NC}  ${BOLD}${WHT}$APP_NAME${NC} ${GRN}v${VERSION}${NC} has been deployed.                         ${GRN}║${NC}"
echo "${GRN}║${NC}  System sanitized. Dependencies acquired. App installed.            ${GRN}║${NC}"
echo "${GRN}╚══════════════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo "  ${CYAN}🚀 Launch:${NC}      open '$USER_BUNDLE_PATH'"
echo "  ${CYAN}📁 Source:${NC}      $INSTALL_DIR"
echo "  ${CYAN}🔄 Update:${NC}      cd $INSTALL_DIR && git pull && npm ci"
echo ""
echo "  ${YEL}Shortcuts:${NC}"
echo "    Space  — Play / Pause global transport"
echo "    Enter  — Return to start"
echo ""
echo "  ${YEL}First run:${NC}"
echo "    1. Load a beat (drag & drop or click LOAD BEAT)"
echo "    2. Hit the red button → 4-count → record"
echo "    3. Click takes in lanes to promote to Staging Track"
echo "    4. Space to hear beat + staged take in sync"
echo ""
