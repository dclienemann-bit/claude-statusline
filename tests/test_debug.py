import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SCRIPT = os.path.join(ROOT, "statusline.py")
SAMPLE = {"session_id": "t", "model": {"display_name": "Sonnet 5.5"},
          "workspace": {"current_dir": "/x/my-project"}, "context_window": {"used_percentage": 18.4}}


class Debug(unittest.TestCase):
    def setUp(self):
        self.state = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.state, True)
        self.env = {k: v for k, v in os.environ.items() if k != "STATUSLINE_DEBUG"}
        self.env.update(XDG_STATE_HOME=self.state, STATUSLINE_COST="0")
        self.log = os.path.join(self.state, "claude", "statusline-debug.log")

    def run_script(self, data, **extra):
        return subprocess.run([sys.executable, SCRIPT], input=data, capture_output=True,
                              env=dict(self.env, **extra))

    def test_silent_by_default(self):
        r = self.run_script(b"not json")
        self.assertEqual((r.stdout, r.stderr, r.returncode), (b"", b"", 0))
        self.assertFalse(os.path.exists(self.log))

    def test_debug_leaves_a_breadcrumb_but_still_prints_nothing(self):
        r = self.run_script(b"not json", STATUSLINE_DEBUG="1")
        self.assertEqual((r.stdout, r.returncode), (b"", 0))
        self.assertIn(b"JSONDecodeError", r.stderr)
        with open(self.log) as f:
            self.assertIn("JSONDecodeError", f.read())

    def test_debug_zero_is_off(self):
        self.run_script(b"not json", STATUSLINE_DEBUG="0")
        self.assertFalse(os.path.exists(self.log))

    def test_output_is_utf8_whatever_the_locale(self):
        r = self.run_script(json.dumps(SAMPLE).encode(), PYTHONIOENCODING="latin-1", NO_COLOR="1")
        self.assertEqual(r.returncode, 0)
        self.assertIn("█".encode("utf-8"), r.stdout)

    def test_non_ascii_input_is_read_as_utf8(self):
        d = dict(SAMPLE, model={"display_name": "Sønnet ≈"})
        r = self.run_script(json.dumps(d, ensure_ascii=False).encode("utf-8"), PYTHONIOENCODING="latin-1",
                            NO_COLOR="1")
        self.assertIn("SØNNET ≈".encode("utf-8"), r.stdout)


if __name__ == "__main__":
    unittest.main()
