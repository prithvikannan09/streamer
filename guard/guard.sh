#!/bin/bash
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
printf '\033]0;Stream Guard\007'
exec /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 guard.py "$@"
