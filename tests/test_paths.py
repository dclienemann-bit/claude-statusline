import os, subprocess, sys, unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
PROBE = "import statusline_cost as c; print(c.PROJECTS); print(c.STATE)"


def paths(**env):
    base = {k: v for k, v in os.environ.items()
            if k not in ("CLAUDE_CONFIG_DIR", "XDG_STATE_HOME", "CLAUDE_COST_PROJECTS", "CLAUDE_COST_STATE")}
    base.update(HOME="/h", **env)
    out = subprocess.run([sys.executable, "-c", PROBE], cwd=ROOT, env=base, capture_output=True, text=True)
    return out.stdout.split("\n")[:2]


class CostPaths(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(paths(), ["/h/.claude/projects", "/h/.local/state/claude"])

    def test_claude_config_dir(self):
        self.assertEqual(paths(CLAUDE_CONFIG_DIR="/cfg")[0], "/cfg/projects")

    def test_xdg_state_home(self):
        self.assertEqual(paths(XDG_STATE_HOME="/xs")[1], "/xs/claude")

    def test_relative_xdg_state_home_is_ignored(self):
        self.assertEqual(paths(XDG_STATE_HOME="rel")[1], "/h/.local/state/claude")

    def test_test_overrides_still_win(self):
        got = paths(CLAUDE_CONFIG_DIR="/cfg", XDG_STATE_HOME="/xs", CLAUDE_COST_PROJECTS="/p", CLAUDE_COST_STATE="/s")
        self.assertEqual(got, ["/p", "/s"])


if __name__ == "__main__":
    unittest.main()
