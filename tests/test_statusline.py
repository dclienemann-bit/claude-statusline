import json, os, re, subprocess, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["NO_COLOR"] = "1"
os.environ["STATUSLINE_COST"] = "0"
import statusline as s

ROOT = os.path.join(os.path.dirname(__file__), "..")
NOW = 1_900_000_000
WEEK = 168 * 3600


class Pace(unittest.TestCase):
    def test_ahead(self):  # half the week gone, 14% used -> 36% ahead = ~60h
        out = s.pace(14, NOW + WEEK / 2, NOW)
        self.assertIn("+36%", out); self.assertIn("≈60h ahead", out)

    def test_behind(self):  # half gone, 70% used -> behind 20%, even in 34h
        out = s.pace(70, NOW + WEEK / 2, NOW)
        self.assertIn("behind 20%", out); self.assertIn("even in 34h", out)

    def test_on_pace(self):
        self.assertIn("on pace", s.pace(50, NOW + WEEK / 2, NOW))

    def test_missing(self):
        self.assertIsNone(s.pace(None, NOW, NOW)); self.assertIsNone(s.pace(5, None, NOW))


class Build(unittest.TestCase):
    def sample(self):
        return {"session_id": "t", "model": {"display_name": "Sonnet 5.5"}, "effort": {"level": "medium"},
                "workspace": {"current_dir": "/x/my-project"}, "context_window": {"used_percentage": 18.4},
                "rate_limits": {"five_hour": {"used_percentage": 31, "resets_at": NOW + 13000},
                                "seven_day": {"used_percentage": 12, "resets_at": NOW + 360000}}}

    def test_rows(self):
        out = s.build(self.sample(), NOW)
        for label in ("WHERE", "LIMITS", "BANKED", "CONTEXT"):
            self.assertIn(label, out)
        self.assertIn("SONNET 5.5", out); self.assertIn("18.4%", out)

    def test_no_rate_limits(self):  # API-key users have none: rows just disappear
        d = self.sample(); del d["rate_limits"]
        out = s.build(d, NOW)
        self.assertNotIn("LIMITS", out); self.assertNotIn("BANKED", out); self.assertIn("CONTEXT", out)

    def test_empty_input_prints_nothing_bad(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "statusline.py")], input="not json",
                           capture_output=True, text=True)
        self.assertEqual(r.stdout, ""); self.assertEqual(r.returncode, 0)

    def test_end_to_end(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "statusline.py")],
                           input=json.dumps(self.sample()), capture_output=True, text=True)
        self.assertIn("CONTEXT", r.stdout)


class NoPersonalDetails(unittest.TestCase):
    def test_scan(self):
        bad = re.compile(r"/Users/|danielclienemann|@gmail|liam|lifeos|clarity|control-plane", re.I)
        for f in os.listdir(ROOT):
            p = os.path.join(ROOT, f)
            if os.path.isfile(p) and not f.startswith("."):
                self.assertIsNone(bad.search(open(p, errors="ignore").read()), f)


if __name__ == "__main__":
    unittest.main()
