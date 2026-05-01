#!/bin/bash
# NeonForge Vocal Guide — macOS Build Script
# Run this on your Intel Mac. Double-click if made executable, or run in Terminal.

set -e

APP_NAME="NeonForge Vocal Guide"
BUNDLE_ID="com.neonforge.vocalguide"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_DIR/build-mac"
BUNDLE_DIR="$BUILD_DIR/$APP_NAME.app"

echo "========================================"
echo "  NeonForge Vocal Guide — macOS Build"
echo "========================================"

# Check for Homebrew
if ! command -v brew &>/dev/null; then
    echo "❌ Homebrew not found. Please install it first:"
    echo "   /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    exit 1
fi

# Install dependencies
echo "📦 Checking dependencies..."
brew list sdl2 &>/dev/null || brew install sdl2
brew list sdl2_ttf &>/dev/null || brew install sdl2_ttf

# Export paths for CMake
export PKG_CONFIG_PATH="/usr/local/opt/sdl2/lib/pkgconfig:/usr/local/opt/sdl2_ttf/lib/pkgconfig:$PKG_CONFIG_PATH"

# Build
echo "🔨 Building..."
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"
cmake "$PROJECT_DIR" -DCMAKE_BUILD_TYPE=Release
make -j$(sysctl -n hw.ncpu)

# Create app bundle
echo "📁 Creating app bundle..."
rm -rf "$BUNDLE_DIR"
mkdir -p "$BUNDLE_DIR/Contents/MacOS"
mkdir -p "$BUNDLE_DIR/Contents/Resources"

# Copy binary
cp "$BUILD_DIR/vocalguide" "$BUNDLE_DIR/Contents/MacOS/"

# Write Info.plist
cat > "$BUNDLE_DIR/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>vocalguide</string>
    <key>CFBundleIdentifier</key>
    <string>$BUNDLE_ID</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>$APP_NAME</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>10.13</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
EOF

# Create launcher script that sets library paths
# This lets the app find Homebrew SDL2 without modifying the binary
cat > "$BUNDLE_DIR/Contents/MacOS/launcher" <<'EOF'
#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
export DYLD_LIBRARY_PATH="/usr/local/opt/sdl2/lib:/usr/local/opt/sdl2_ttf/lib:/usr/local/opt/freetype/lib:$DYLD_LIBRARY_PATH"
exec "$DIR/vocalguide" "$@"
EOF
chmod +x "$BUNDLE_DIR/Contents/MacOS/launcher"

# Also create a .command file in the build dir for easy launching
cat > "$BUILD_DIR/launch-$APP_NAME.command" <<EOF
#!/bin/bash
cd "$(dirname "$0")"
export DYLD_LIBRARY_PATH="/usr/local/opt/sdl2/lib:/usr/local/opt/sdl2_ttf/lib:/usr/local/opt/freetype/lib:\$DYLD_LIBRARY_PATH"
"$APP_NAME.app/Contents/MacOS/vocalguide" "\$@"
EOF
chmod +x "$BUILD_DIR/launch-$APP_NAME.command"

echo ""
echo "✅ Build complete!"
echo ""
echo "📂 App bundle: $BUNDLE_DIR"
echo "🚀 Launcher:   $BUILD_DIR/launch-$APP_NAME.command"
echo ""
echo "To use:"
echo "  1. Put your MP3 and guide.json in the same folder"
echo "  2. Drag them onto the app, or launch from Terminal:"
echo "     $BUNDLE_DIR/Contents/MacOS/vocalguide guide.json song.mp3"
echo ""
