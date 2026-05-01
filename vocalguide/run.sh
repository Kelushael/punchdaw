#!/bin/bash
# Quick launcher for Linux
# Usage: ./run.sh guide.json song.mp3

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build"

if [ $# -lt 2 ]; then
    echo "Usage: $0 <guide.json> <reference.mp3>"
    echo ""
    echo "Generate guide first:"
    echo "  python3 analyzer/map.py your_song.mp3 -o guide.json"
    echo ""
    exit 1
fi

if [ ! -f "$BUILD_DIR/vocalguide" ]; then
    echo "Binary not found. Building..."
    mkdir -p "$BUILD_DIR"
    cd "$BUILD_DIR"
    cmake "$SCRIPT_DIR"
    make -j$(nproc)
    cd "$SCRIPT_DIR"
fi

"$BUILD_DIR/vocalguide" "$1" "$2"
