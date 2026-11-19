#!/bin/bash
export PATH="/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/3.12/bin:$PATH"
exec /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 "$(dirname "$0")/clipper.py" "$@"
