#!/bin/sh
cd "$(dirname "$0")" || exit 1
if command -v python3 >/dev/null 2>&1; then
  exec python3 dashboard/server.py "$@"
fi
printf '%s\n' 'Python 3.10 or newer is required. Run python3 dashboard/server.py after installing Python.'
read -r answer
