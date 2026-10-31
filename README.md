# claude-statusline

A labelled, four-row status line for Claude Code. It shows where you are, how much of your
5-hour and weekly limits you've used, whether you're **ahead of or behind an even weekly pace**
(the "banked hours" row), and how full the context window is.

```
WHERE   my-project · main │ 10:29 │ SONNET 5.5 │ effort MEDIUM
LIMITS  Claude 5h   ██████░░░░░░░░░░░░░░  31%  3h41m left      Chat ≈$0.73  Project ≈$62.30
        Claude week ██░░░░░░░░░░░░░░░░░░  12%  Wed 14:17       7d ≈$1.40  avg ≈$0.20/day
BANKED  Claude +28% ≈47h ahead ↻Wed
CONTEXT ████░░░░░░░░░░░░░░░░ 18.4%
```

- Python 3 standard library only. No dependencies, no network calls, nothing leaves your machine.
- Meters turn amber at 70% and red at 90%.
- Rows with no data disappear (for example, API-key users have no rate limits, so LIMITS and BANKED are hidden).
- If anything goes wrong it prints nothing instead of garbage.

## Install

```bash
git clone https://github.com/<you>/claude-statusline
cd claude-statusline
./install.sh
```

The installer copies two files into `~/.claude/statusline/`, saves a backup of your
`settings.json`, and sets the `statusLine` command. Restart Claude Code. To see it with made-up
numbers first, run `python3 demo.py`.

Manual install: copy `statusline.py` (and `statusline_cost.py` if you want the cost box) somewhere,
then add this to `~/.claude/settings.json`:

```json
{ "statusLine": { "type": "command", "command": "python3 /path/to/statusline.py" } }
```

## What "banked" means

The weekly limit is 168 hours. Banked compares the share of the week that has already passed with
the share of your allowance you've used:

| Reading | Meaning |
|---|---|
| `+28% ≈47h ahead` | You've used 28 points less than an even pace would have by now (about 47 hours' worth). |
| `behind 20% · even in 34h` | You're burning faster than even. Stop for 34 hours and you'd be back on pace. |
| `on pace` | Within 1% of even. |

The arrow and weekday (`↻Wed`) is when the weekly window resets. The idea comes from Fred Nix's status line.

## The cost box (optional)

Estimates what your work would cost at Claude API list prices, read from the token counts in
Claude Code's own transcripts under `~/.claude/projects`. It is **not** your subscription bill. It
shows this chat, this project, the last 7 days and the daily average. The first run builds a cache in
`~/.local/state/claude/` in the background, so the box appears a few seconds later. Prices live in the
`PRICES` table at the top of `statusline_cost.py`; edit it when prices or models change.
Turn the box off with `STATUSLINE_COST=0`. Turn colours off with `NO_COLOR=1`.

## Test

```bash
python3 tests/test_statusline.py
```

## Notes

- Needs a terminal that does 24-bit colour and Unicode block characters.
- `rate_limits` only appears for Claude.ai subscribers, and only after the first reply in a session.
- Field names come from the [Claude Code status line docs](https://code.claude.com/docs/en/statusline).

MIT licensed.
