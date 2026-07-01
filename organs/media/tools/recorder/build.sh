#!/usr/bin/env bash
# Build the native media-recorder (ScreenCaptureKit). No external deps.
set -euo pipefail
cd "$(dirname "$0")"
swiftc -O -parse-as-library record.swift -o media-recorder
echo "built: $(pwd)/media-recorder"
