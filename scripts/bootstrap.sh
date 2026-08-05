#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(dirname "$SCRIPT_DIR")
PYTHON_BIN=${PYTHON_BIN:-}

python_version_supported() {
    "$1" -c 'import sys; raise SystemExit(sys.version_info < (3, 11))' \
        >/dev/null 2>&1
}

select_python() {
    if [ -n "$PYTHON_BIN" ]; then
        if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
            echo "Selected Python interpreter is unavailable: $PYTHON_BIN" >&2
            exit 2
        fi
        if ! python_version_supported "$PYTHON_BIN"; then
            echo "Selected Python interpreter must be Python 3.11 or newer: $PYTHON_BIN" >&2
            exit 2
        fi
        PYTHON_BIN=$(command -v "$PYTHON_BIN")
        return
    fi

    for candidate in python3 python3.13 python3.12 python3.11; do
        if command -v "$candidate" >/dev/null 2>&1 && python_version_supported "$candidate"; then
            PYTHON_BIN=$(command -v "$candidate")
            return
        fi
    done

    echo "No compatible Python interpreter was found. Install Python 3.11+ or set PYTHON_BIN to its path." >&2
    exit 2
}

select_python

if [ ! -d "$PROJECT_ROOT/.venv" ]; then
    "$PYTHON_BIN" -m venv "$PROJECT_ROOT/.venv" || {
        echo "The selected Python requires venv with pip (Ubuntu/Debian: install the matching package, for example python3.11-venv)." >&2
        exit 2
    }
fi

"$PROJECT_ROOT/.venv/bin/python" -m pip install --upgrade pip
"$PROJECT_ROOT/.venv/bin/python" -m pip install --require-hashes \
    -r "$PROJECT_ROOT/requirements-build.lock"
"$PROJECT_ROOT/.venv/bin/python" -m pip install --require-hashes \
    -r "$PROJECT_ROOT/requirements.lock"
"$PROJECT_ROOT/.venv/bin/python" -m pip install --no-deps \
    --no-build-isolation --editable "$PROJECT_ROOT"
"$PROJECT_ROOT/.venv/bin/python" -m pip check

echo "Environment ready. Start with ./scripts/run-agent.sh."
