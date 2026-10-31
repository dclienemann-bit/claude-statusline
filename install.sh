#!/bin/bash
# Copies the status line into ~/.claude and points Claude Code at it.
set -e
DEST="$HOME/.claude/statusline"
SETTINGS="$HOME/.claude/settings.json"
mkdir -p "$DEST"
cp "$(dirname "$0")/statusline.py" "$(dirname "$0")/statusline_cost.py" "$DEST/"
python3 - "$SETTINGS" "$DEST/statusline.py" <<'PY'
import json, os, shutil, sys
path, script = sys.argv[1], sys.argv[2]
data = {}
if os.path.exists(path):
    shutil.copy(path, path + ".bak-before-statusline")
    with open(path) as f:
        data = json.load(f)
data["statusLine"] = {"type": "command", "command": f"python3 {script}"}
with open(path, "w") as f:
    json.dump(data, f, indent=2)
PY
echo "Installed. Your old settings were saved as $SETTINGS.bak-before-statusline. Restart Claude Code."
