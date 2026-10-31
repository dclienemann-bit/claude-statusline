#!/usr/bin/env python3
"""A compact, labelled status line for Claude Code. Python 3 standard library only.

Claude Code pipes a JSON blob to this script on every refresh. We print up to four rows:

  WHERE    folder · git branch │ time │ model │ effort
  LIMITS   5-hour and weekly meters (plus an optional cost box on the right)
  BANKED   how far ahead of (or behind) an even weekly pace you are
  CONTEXT  context-window meter

Rows with no data are left out. Any error prints nothing rather than garbage.
Set NO_COLOR=1 to turn colours off. Set STATUSLINE_COST=0 to turn the cost box off.
Set STATUSLINE_DEBUG=1 to find out why the line is blank: the error goes to stderr (visible with
`claude --debug`) and to statusline-debug.log in the state directory (~/.local/state/claude).
"""
import json
import os
import re
import subprocess
import sys
import time
import traceback

WEEK_H = 168.0
COLOR = "NO_COLOR" not in os.environ


def c(r, g, b):
    return f"\x1b[38;2;{r};{g};{b}m" if COLOR else ""


DIM, LABEL, VALUE = c(71, 85, 105), c(148, 163, 184), c(59, 130, 246)
GREEN, AMBER, RED = c(34, 197, 94), c(245, 158, 11), c(239, 68, 68)
RESET = "\x1b[0m" if COLOR else ""
SEP = f" {DIM}│{RESET} "
ANSI = re.compile(r"\x1b\[[0-9;]*m")


def plain(s):
    return ANSI.sub("", s)


def debug_log():
    """Only when STATUSLINE_DEBUG is set: say what went wrong, since the line itself stays blank."""
    if os.environ.get("STATUSLINE_DEBUG") in (None, "", "0"):
        return
    try:
        tb = traceback.format_exc()
        sys.stderr.write(tb)
        xdg = os.environ.get("XDG_STATE_HOME")
        base = xdg if xdg and os.path.isabs(xdg) else os.path.join(os.path.expanduser("~"), ".local/state")
        state = os.environ.get("CLAUDE_COST_STATE") or os.path.join(base, "claude")
        log = os.path.join(state, "statusline-debug.log")
        os.makedirs(state, exist_ok=True)
        too_big = os.path.exists(log) and os.path.getsize(log) > 200000
        with open(log, "w" if too_big else "a", encoding="utf-8") as f:
            f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} statusline.py\n{tb}")
    except Exception:
        pass


def heat(pct):
    """Blue normally, amber from 70%, red from 90%."""
    return RED if pct >= 90 else AMBER if pct >= 70 else VALUE


def bar(pct, width=20):
    n = min(width, max(1 if pct > 0 else 0, round(pct / 100 * width)))
    return f"{heat(pct)}{'█' * n}{RESET}{DIM}{'░' * (width - n)}{RESET}"


def pace(used, reset, now):
    """'+36% ≈60h ahead' / 'behind 21% · even in 36h' / 'on pace', from the weekly window.
    gap = share of the week already gone minus share of the allowance used."""
    if used is None or not reset:
        return None
    into = WEEK_H - max(0.0, (float(reset) - now) / 3600)
    gap = into / WEEK_H * 100 - float(used)
    back = f" {DIM}↻{time.strftime('%a', time.localtime(float(reset)))}{RESET}"
    if abs(gap) < 1:
        return f"{GREEN}on pace{RESET}{back}"
    if gap > 0:
        return f"{GREEN}+{gap:.0f}% ≈{gap * WEEK_H / 100:.0f}h ahead{RESET}{back}"
    even_in = float(used) / 100 * WEEK_H - into
    return f"{RED if gap < -10 else AMBER}behind {-gap:.0f}% · even in {even_in:.0f}h{RESET}{back}"


def meter(name, pct, when):
    return f"{LABEL}{name:<12}{RESET}{bar(pct)} {heat(pct)}{pct:>3.0f}%{RESET}  {DIM}{when}{RESET}"


def git_branch(cwd):
    try:
        out = subprocess.run(["git", "-C", cwd, "branch", "--show-current"],
                             capture_output=True, text=True, timeout=1).stdout.strip()
        return out or None
    except Exception:
        debug_log()
        return None


def build(d, now=None):
    now = time.time() if now is None else now
    pad = lambda name, body: f"{LABEL}{name:<8}{RESET}{body}"
    rows = []

    # WHERE
    cwd = (d.get("workspace") or {}).get("current_dir") or d.get("cwd") or ""
    where = []
    if cwd:
        branch = git_branch(cwd)
        where.append(f"{VALUE}{os.path.basename(cwd.rstrip('/')) or '/'}{RESET}"
                     + (f" {DIM}·{RESET} {LABEL}{branch}{RESET}" if branch else ""))
    where.append(f"{LABEL}{time.strftime('%H:%M', time.localtime(now))}{RESET}")
    model = (d.get("model") or {}).get("display_name")
    if model:
        where.append(f"{VALUE}{model.upper()}{RESET}")
    effort = (d.get("effort") or {}).get("level")
    if effort:
        where.append(f"{LABEL}effort{RESET} {VALUE}{effort.upper()}{RESET}")
    rows.append(pad("WHERE", SEP.join(where)))

    # LIMITS (+ cost box on the right, if it fits)
    rl = d.get("rate_limits") or {}
    cells = []
    for name, key in (("Claude 5h", "five_hour"), ("Claude week", "seven_day")):
        w = rl.get(key) or {}
        if w.get("used_percentage") is None:
            continue
        reset = float(w.get("resets_at") or 0)
        if key == "five_hour" and reset:
            mins = max(0, int(reset - now) // 60)
            when = f"{mins // 60}h{mins % 60:02d}m left"
        else:
            when = time.strftime("%a %H:%M", time.localtime(reset)) if reset else ""
        cells.append(meter(name, float(w["used_percentage"]), when))
    box = cost_box(d)
    for i in range(max(len(cells), min(len(box), 2))):
        left = cells[i] if i < len(cells) else ""
        right = box[i] if i < len(box) else ""
        rows.append(pad("LIMITS" if i == 0 else "", left + ("      " + right if right and left else right)))

    # BANKED
    wk = rl.get("seven_day") or {}
    p = pace(wk.get("used_percentage"), wk.get("resets_at"), now)
    if p:
        rows.append(pad("BANKED", f"{LABEL}Claude{RESET} {p}"))

    # CONTEXT
    used = (d.get("context_window") or {}).get("used_percentage")
    if used is not None:
        rows.append(pad("CONTEXT", f"{bar(float(used))} {heat(float(used))}{float(used):>4.1f}%{RESET}"))
    return "\n".join(rows)


def cost_box(d):
    """Up to two short lines from statusline_cost.py (sits next to this file). [] if off or unavailable."""
    if os.environ.get("STATUSLINE_COST") == "0":
        return []
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        sid = d.get("session_id") or ""
        proj = (d.get("workspace") or {}).get("project_dir") or d.get("cwd") or ""
        if not sid or not proj:
            return []
        out = subprocess.run([sys.executable, "-I", os.path.join(here, "statusline_cost.py"), sid, proj],
                             capture_output=True, encoding="utf-8", errors="replace", timeout=3).stdout
        return [l for l in out.split("\n") if l.strip()]
    except Exception:
        debug_log()
        return []


def main():
    try:
        if hasattr(sys.stdout, "reconfigure"):  # the bars and arrows are not ASCII; do not depend on the locale
            sys.stdout.reconfigure(encoding="utf-8")
        d = json.loads(sys.stdin.buffer.read().decode("utf-8", "replace"))
        sys.stdout.write(build(d))
    except Exception:
        debug_log()


if __name__ == "__main__":
    main()
