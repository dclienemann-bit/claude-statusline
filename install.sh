#!/bin/bash
# Copies the status line into ~/.claude and points Claude Code at it.
#   ./install.sh            install; leaves an existing, different statusLine alone
#   ./install.sh --force    replace an existing statusLine
set -euo pipefail

FORCE=0
for arg in "$@"; do
  case "$arg" in
    --force) FORCE=1 ;;
    -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
    *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
  esac
done

HERE="$(cd "$(dirname "$0")" && pwd)"
DEST="$HOME/.claude/statusline"
SETTINGS="$HOME/.claude/settings.json"
mkdir -p "$DEST"
cp "$HERE/statusline.py" "$HERE/statusline_cost.py" "$DEST/"

python3 - "$SETTINGS" "$FORCE" <<'PY'
import json, os, shutil, sys, tempfile

path, force = sys.argv[1], sys.argv[2] == "1"
# $HOME is expanded by the shell Claude Code runs the command in, so this stays correct if the
# settings file is ever copied to another machine or user.
command = 'python3 "$HOME/.claude/statusline/statusline.py"'
ours = {"type": "command", "command": command}

data = {}
if os.path.exists(path):
    try:
        with open(path) as f:
            data = json.load(f)
    except ValueError as e:
        sys.exit(f"Could not read {path} as JSON ({e}). Nothing was changed in it.")
    if not isinstance(data, dict):
        sys.exit(f"{path} is not a JSON object. Nothing was changed in it.")

old = data.get("statusLine")
installed_before = isinstance(old, dict) and "statusline/statusline.py" in str(old.get("command", ""))
if old is not None and old != ours and not installed_before and not force:
    print(f"Files copied, but {path} already has a statusLine, so I left it alone:")
    print(f"  {json.dumps(old)}")
    print("Run ./install.sh --force to replace it.")
    sys.exit(0)

if old != ours:
    if os.path.exists(path):
        backup = path + ".bak-before-statusline"
        if not os.path.exists(backup):  # keep the first backup: it is the original
            shutil.copy(path, backup)
    data["statusLine"] = dict(old, **ours) if isinstance(old, dict) and installed_before else ours
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".settings.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        if os.path.exists(path):
            shutil.copymode(path, tmp)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
print("Installed. Restart Claude Code.")
if os.path.exists(path + ".bak-before-statusline"):
    print(f"Your original settings are saved as {path}.bak-before-statusline")
PY
