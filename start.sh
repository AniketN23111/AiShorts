#!/bin/bash
set -e
cd "$(dirname "$0")"
if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)"; fi
if command -v brew >/dev/null && brew list --versions ffmpeg-full >/dev/null 2>&1; then
  export PATH="$(brew --prefix ffmpeg-full)/bin:$PATH"
fi
if [ ! -x .venv/bin/python ]; then echo 'Create the virtual environment first (see README).'; exit 1; fi
exec .venv/bin/python app.py
