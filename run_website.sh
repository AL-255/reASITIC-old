#!/usr/bin/env bash
# Build the reASITIC wheel + Sphinx docs and serve them for local testing.
#
# By default the script runs the full pipeline so the local site mirrors
# what will be deployed to GitHub Pages: sphinx-build → docs/_build/html,
# then the docs/repl/ tree is copied into docs/_build/html/repl/.
#
# Usage:
#   ./run_website.sh             # full build (Sphinx + wheel) and serve
#   ./run_website.sh --repl      # skip the slow Sphinx build, serve docs/repl/ only
#   ./run_website.sh --no-build  # skip wheel rebuild, keep current Sphinx output
#   ./run_website.sh --rebuild   # force a fresh wheel build
#   PORT=9000 ./run_website.sh   # custom port (default 8765)

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOCS_DIR="$PROJECT_ROOT/docs"
REPL_DIR="$DOCS_DIR/repl"
WHEELS_DIR="$REPL_DIR/wheels"
SPHINX_OUT="$DOCS_DIR/_build/html"
PORT="${PORT:-8765}"
PYTHON="${PYTHON:-python3}"

NO_BUILD=0
FORCE_BUILD=0
SKIP_SPHINX=0
for arg in "$@"; do
  case "$arg" in
    --no-build) NO_BUILD=1 ;;
    --rebuild)  FORCE_BUILD=1 ;;
    --repl)     SKIP_SPHINX=1 ;;
    -h|--help)
      awk '/^# Usage:/{p=1} p && /^[^#]/{exit} p' "${BASH_SOURCE[0]}"
      exit 0
      ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done

mkdir -p "$WHEELS_DIR"

build_wheel() {
  echo ">> Building reASITIC wheel from $PROJECT_ROOT"
  if ! "$PYTHON" -c "import build" 2>/dev/null; then
    echo ">> Installing 'build' (PEP 517 frontend) into the active Python"
    "$PYTHON" -m pip install --quiet --upgrade build
  fi

  rm -f "$WHEELS_DIR"/reasitic-*.whl
  ( cd "$PROJECT_ROOT" && "$PYTHON" -m build --wheel --outdir "$WHEELS_DIR" )

  local count
  count=$(ls "$WHEELS_DIR"/reasitic-*.whl 2>/dev/null | wc -l)
  if [[ "$count" -ne 1 ]]; then
    echo "!! Expected exactly one reasitic-*.whl in $WHEELS_DIR, found $count" >&2
    exit 1
  fi
}

sync_app_js_with_wheel() {
  local wheel
  wheel=$(ls "$WHEELS_DIR"/reasitic-*.whl | head -n 1)
  local wheel_name
  wheel_name=$(basename "$wheel")
  if ! grep -q "$wheel_name" "$REPL_DIR/app.js"; then
    echo ">> Updating app.js to reference $wheel_name"
    "$PYTHON" - "$REPL_DIR/app.js" "$wheel_name" <<'PY'
import re, sys, pathlib
app_path = pathlib.Path(sys.argv[1])
new_name = sys.argv[2]
text = app_path.read_text()
text2 = re.sub(r'wheels/reasitic-[^"\']+\.whl', f'wheels/{new_name}', text)
if text != text2:
    app_path.write_text(text2)
PY
  fi
}

if [[ "$NO_BUILD" -eq 1 ]]; then
  if ! ls "$WHEELS_DIR"/reasitic-*.whl >/dev/null 2>&1; then
    echo "!! --no-build set but no wheel found in $WHEELS_DIR" >&2
    exit 1
  fi
  echo ">> Skipping wheel build ($(ls "$WHEELS_DIR"/reasitic-*.whl))"
elif [[ "$FORCE_BUILD" -eq 1 ]] || ! ls "$WHEELS_DIR"/reasitic-*.whl >/dev/null 2>&1; then
  build_wheel
else
  echo ">> Reusing existing wheel: $(ls "$WHEELS_DIR"/reasitic-*.whl)"
  echo "   Pass --rebuild to force a fresh build."
fi

sync_app_js_with_wheel

build_sphinx() {
  echo ">> Running sphinx-build → $SPHINX_OUT"
  if ! command -v sphinx-build >/dev/null 2>&1; then
    echo "!! sphinx-build not found. Install the docs extras with:" >&2
    echo "     pip install -e \"$PROJECT_ROOT\"[docs]" >&2
    echo "   or pass --repl to skip the Sphinx build entirely." >&2
    exit 1
  fi
  if ! ( cd "$DOCS_DIR" && sphinx-build -b html -q . "$SPHINX_OUT" ); then
    echo "!! sphinx-build failed. If you see 'No module named sphinx_copybutton/myst_parser/furo'," >&2
    echo "   install the docs extras:" >&2
    echo "     pip install -e \"$PROJECT_ROOT\"[docs]" >&2
    echo "   or pass --repl to skip the Sphinx build entirely." >&2
    exit 1
  fi
}

stage_combined_site() {
  # Mirror the deployed layout: docs/_build/html/{sphinx output, repl/}.
  rm -rf "$SPHINX_OUT/repl"
  mkdir -p "$SPHINX_OUT/repl"
  # rsync if available (faster on re-runs); fall back to cp -R.
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete --exclude '__pycache__' "$REPL_DIR/" "$SPHINX_OUT/repl/"
  else
    cp -R "$REPL_DIR/." "$SPHINX_OUT/repl/"
    rm -rf "$SPHINX_OUT/repl/__pycache__"
  fi
}

if [[ "$SKIP_SPHINX" -eq 1 ]]; then
  SERVE_DIR="$REPL_DIR"
  URL_PATH="/index.html"
  MODE_LABEL="REPL only (Sphinx build skipped)"
else
  build_sphinx
  stage_combined_site
  SERVE_DIR="$SPHINX_OUT"
  URL_PATH="/repl/index.html"
  MODE_LABEL="Full site (Sphinx + REPL)"
fi

URL="http://127.0.0.1:${PORT}${URL_PATH}"
echo
echo "================================================================"
echo "  reASITIC — $MODE_LABEL"
echo "  Open:    $URL"
echo "  Serving: $SERVE_DIR"
echo "  Stop:    Ctrl-C"
echo "================================================================"
echo

# Hand off to the simple HTTP server. Bind to loopback only so we don't
# accidentally expose the wheel to the LAN.
exec "$PYTHON" -m http.server "$PORT" --directory "$SERVE_DIR" --bind 127.0.0.1
