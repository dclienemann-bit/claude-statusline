#!/usr/bin/env python3
"""API-price cost box for the status bar.

Prints two lines (or nothing):
  Chat ≈$X  Project ≈$Y        this chat incl. its helpers / everything in this project
  7d ≈$Z  avg ≈$W/day          rolling 7 days, this project only (same in every chat of the project)
Estimates from the token counts in Claude Code's own transcripts (~/.claude/projects, or $CLAUDE_CONFIG_DIR/projects), priced at the
Claude API list prices. Not the Max plan bill: what the same work would cost per token.

Per-file cache (path, size, mtime -> per-day, per-model token tallies) in ~/.local/state/claude/cost-cache.json ($XDG_STATE_HOME/claude if set),
so a warm run only reads files that grew. A cold cache is filled by a detached background run (lock file);
meanwhile only the parts that are fully ready are shown. Any problem: prints nothing.

usage: statusline-cost.py <session_id> <project_dir>
       statusline-cost.py --refresh        (background fill, used by itself)
"""
import json, os, re, subprocess, sys, time, traceback
from datetime import datetime

HOME = os.path.expanduser("~")
CONFIG = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(HOME, ".claude")
XDG_STATE = os.environ.get("XDG_STATE_HOME")
if not (XDG_STATE and os.path.isabs(XDG_STATE)):  # the XDG spec says a relative value must be ignored
    XDG_STATE = os.path.join(HOME, ".local/state")
PROJECTS = os.environ.get("CLAUDE_COST_PROJECTS") or os.path.join(CONFIG, "projects")  # CLAUDE_COST_* are for tests
STATE = os.environ.get("CLAUDE_COST_STATE") or os.path.join(XDG_STATE, "claude")
CACHE = os.path.join(STATE, "cost-cache.json")
LOCK = os.path.join(STATE, "cost-refresh.lock")
INLINE_BUDGET_S = 0.8     # most the status line itself spends parsing changed files
INLINE_MAX_BYTES = 30e6   # a bigger backlog goes to the background run
LOCK_STALE_S = 600

# $ per million tokens: input, output, cache read, cache write 5m, cache write 1h.
# From the Claude API price table, then fitted against Claude Code's own cost records (Oct 2026).
PRICES = {
    "claude-fable-5-1": (10, 50, 0.25, 12.5, 20), "claude-fable-5": (10, 50, 0.25, 12.5, 20),
    "claude-opus-5-5": (4, 20, 0.2, 5, 8), "claude-opus-5": (5, 25, 0.5, 6.25, 10),
    "claude-sonnet-5-5": (2, 10, 0.2, 2.5, 4), "claude-sonnet-5": (2, 10, 0.2, 2.5, 4),
    "claude-haiku-5-5": (0.1, 0.5, 0.01, 0.125, 0.2),
}

LABEL = "\x1b[38;2;148;163;184m"
VALUE = "\x1b[38;2;59;130;246m"
RESET = "\x1b[0m"


# ---------- maths ----------

def usage_tokens(u):
    """[input, output, cache read, cache write 5m, cache write 1h] from one usage record."""
    cc = u.get("cache_creation") or {}
    w1 = cc.get("ephemeral_1h_input_tokens", 0) or 0
    w5 = cc.get("ephemeral_5m_input_tokens", (u.get("cache_creation_input_tokens", 0) or 0) - w1) or 0
    return [u.get("input_tokens", 0) or 0, u.get("output_tokens", 0) or 0,
            u.get("cache_read_input_tokens", 0) or 0, w5, w1]


def dollars(tok, model):
    r = PRICES.get(model)
    return sum(a * b for a, b in zip(tok, r)) / 1e6 if r else 0.0


def parse_lines(lines, days, seen):
    """Add each priced, de-duplicated usage record in `lines` (bytes) into days[day][model]. Returns bytes used
    up to the last complete line."""
    used = 0
    for line in lines:
        if not line.endswith(b"\n"):
            break
        used += len(line)
        if b'"usage"' not in line:
            continue
        try:
            d = json.loads(line)
            m = d.get("message") or {}
            u = m.get("usage")
            model = m.get("model")
            if not u or model not in PRICES:
                continue
            key = f"{m.get('id')}|{d.get('requestId')}"
            if m.get("id"):
                if key in seen:
                    continue
                seen[key] = 1
                if len(seen) > 4000:
                    for old in list(seen)[:2000]:
                        del seen[old]
            day = datetime.fromisoformat(d["timestamp"].replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d")
        except Exception:
            continue
        slot = days.setdefault(day, {}).setdefault(model, [0, 0, 0, 0, 0])
        for i, v in enumerate(usage_tokens(u)):
            slot[i] += v
    return used


def update_entry(path, ent, size, mtime):
    """Bring one cache entry up to date by reading only the new bytes (transcripts only ever grow)."""
    if not ent or ent["off"] > size or ent.get("m", 0) > mtime + 1:
        ent = {"off": 0, "days": {}, "tail": []}
    seen = dict.fromkeys(ent["tail"], 1)
    with open(path, "rb") as f:
        f.seek(ent["off"])
        used = parse_lines(f, ent["days"], seen)
    ent["off"] += used
    ent["tail"] = list(seen)[-8:]
    ent["s"], ent["m"] = size, mtime
    return ent


def cost_of(ents, days_wanted=None):
    tot = 0.0
    for e in ents:
        for day, models in e["days"].items():
            if days_wanted is not None and day not in days_wanted:
                continue
            for model, tok in models.items():
                tot += dollars(tok, model)
    return tot


# ---------- files ----------

def slug_of(path):
    return re.sub(r"[^A-Za-z0-9]", "-", path.rstrip("/"))


def list_files():
    """{path: (size, mtime, slug_dir_name)} for every transcript, subagents included."""
    out = {}
    for slug in os.listdir(PROJECTS):
        base = os.path.join(PROJECTS, slug)
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if fn.endswith(".jsonl"):
                    p = os.path.join(root, fn)
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                    out[p] = (st.st_size, st.st_mtime, slug)
    return out


def load_cache():
    try:
        with open(CACHE) as f:
            c = json.load(f)
        if not isinstance(c, dict):
            return {}
        ok = lambda e: (isinstance(e, dict) and isinstance(e.get("days"), dict) and isinstance(e.get("off"), int)
                        and isinstance(e.get("tail"), list))
        return {p: e for p, e in c.items() if ok(e)}  # malformed/old-format entries are rebuilt
    except Exception:
        return {}


def save_cache(cache):
    os.makedirs(STATE, exist_ok=True)
    tmp = CACHE + f".tmp{os.getpid()}"
    with open(tmp, "w") as f:
        json.dump(cache, f)
    os.replace(tmp, CACHE)


def is_stale(cache, p, size, mtime):
    e = cache.get(p)
    return not e or e.get("s") != size or e.get("m") != mtime


def start_background():
    try:
        os.makedirs(STATE, exist_ok=True)
        try:
            if time.time() - os.path.getmtime(LOCK) > LOCK_STALE_S:
                os.remove(LOCK)
        except OSError:
            pass
        fd = os.open(LOCK, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except OSError:
        return  # another refresh is running (or the lock cannot be made)
    try:
        subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), "--refresh"],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
    except Exception:
        try:
            os.remove(LOCK)
        except OSError:
            pass


def refresh():
    try:
        files = list_files()
        cache = load_cache()
        for p in list(cache):
            if p not in files:
                del cache[p]
        n = 0
        # newest files first: they matter most for the Chat and 7d numbers
        for p, (size, mtime, _s) in sorted(files.items(), key=lambda kv: -kv[1][1]):
            if is_stale(cache, p, size, mtime):
                try:
                    cache[p] = update_entry(p, cache.get(p), size, mtime)
                except OSError:
                    continue
                n += 1
                if n % 150 == 0:
                    save_cache(cache)
        save_cache(cache)
    finally:
        try:
            os.remove(LOCK)
        except OSError:
            pass


# ---------- output ----------

def money(x):
    return f"${x:,.0f}" if x >= 100 else f"${x:,.2f}"


def cell(label, val, suffix=""):
    return f"{LABEL}{label}{RESET} {VALUE}≈{money(val)}{suffix}{RESET}"


def build(session_id, project_dir):
    files = list_files()
    cache = load_cache()
    fam = slug_of(project_dir)
    in_proj = lambda slug: slug == fam or slug.startswith(fam + "--claude-worktrees-")
    in_sess = lambda p: ("/" + session_id + ".jsonl") in p or ("/" + session_id + "/") in p
    week = {datetime.fromtimestamp(time.time() - i * 86400).strftime("%Y-%m-%d") for i in range(7)}
    horizon = time.time() - 8 * 86400

    stale = [p for p, (s, m, _) in files.items() if is_stale(cache, p, s, m)]
    # inline catch-up for small backlogs (e.g. the active chat grew by a few KB)
    if stale:
        locked = os.path.exists(LOCK)
        todo = sorted(stale, key=lambda p: -files[p][1])
        cost_bytes = sum(max(0, files[p][0] - (cache.get(p) or {}).get("off", 0)) for p in todo)
        if not locked and cost_bytes <= INLINE_MAX_BYTES:
            t0, changed = time.time(), False
            for p in todo:
                if time.time() - t0 > INLINE_BUDGET_S:
                    break
                try:
                    cache[p] = update_entry(p, cache.get(p), files[p][0], files[p][1])
                    changed = True
                except OSError:
                    pass
            if changed:
                save_cache(cache)
        elif not locked:
            start_background()
        stale = [p for p, (s, m, _) in files.items() if is_stale(cache, p, s, m)]
    stale_set = set(stale)

    def ready(pred):
        return not any(pred(p) for p in stale_set)

    sess_files = {p for p in files if in_sess(p)}
    proj_files = {p for p, (_s, _m, slug) in files.items() if in_proj(slug)}
    wk_files = [p for p in proj_files if files[p][1] >= horizon]  # this project only
    l1, l2 = [], []
    if sess_files and ready(lambda p: p in sess_files):
        l1.append(cell("Chat", cost_of([cache[p] for p in sess_files if p in cache])))
    if proj_files and ready(lambda p: p in proj_files):
        l1.append(cell("Project", cost_of([cache[p] for p in proj_files if p in cache])))
    if proj_files and ready(lambda p: p in proj_files and files[p][1] >= horizon):
        wk = cost_of([cache[p] for p in wk_files if p in cache], week)
        l2.append(cell("7d", wk))
        l2.append(cell("avg", wk / 7, "/day"))
    return [("  ").join(l) for l in (l1, l2) if l]


def debug_log():
    """Only when STATUSLINE_DEBUG is set: record the error (this module's own output is otherwise dropped)."""
    if os.environ.get("STATUSLINE_DEBUG") in (None, "", "0"):
        return
    try:
        tb = traceback.format_exc()
        sys.stderr.write(tb)
        os.makedirs(STATE, exist_ok=True)
        with open(os.path.join(STATE, "statusline-debug.log"), "a", encoding="utf-8") as f:
            f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} statusline_cost.py\n{tb}")
    except Exception:
        pass


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) >= 2 and sys.argv[1] == "--refresh":
        refresh()
        return
    session_id, project_dir = sys.argv[1], sys.argv[2]
    if not session_id or not project_dir:
        return
    lines = build(session_id, project_dir)
    if lines:
        sys.stdout.write("\n".join(lines))


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        debug_log()
