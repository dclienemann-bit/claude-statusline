import json, os, shutil, subprocess, sys, tempfile, unittest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
INSTALL = os.path.join(ROOT, "install.sh")
LINE = 'python3 "$HOME/.claude/statusline/statusline.py"'


@unittest.skipUnless(shutil.which("bash"), "needs bash")
class Installer(unittest.TestCase):
    def setUp(self):
        self.home = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.home, True)
        self.settings = os.path.join(self.home, ".claude", "settings.json")

    def run_install(self, *args):
        env = dict(os.environ, HOME=self.home)
        return subprocess.run(["bash", INSTALL, *args], env=env, capture_output=True, text=True)

    def write(self, data):
        os.makedirs(os.path.dirname(self.settings), exist_ok=True)
        with open(self.settings, "w") as f:
            json.dump(data, f)

    def read(self):
        with open(self.settings) as f:
            return json.load(f)

    def test_fresh_install_uses_home_not_a_baked_path(self):
        r = self.run_install()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.read()["statusLine"], {"type": "command", "command": LINE})
        self.assertNotIn(self.home, self.read()["statusLine"]["command"])
        self.assertTrue(os.path.exists(os.path.join(self.home, ".claude", "statusline", "statusline.py")))

    def test_keeps_other_settings_and_first_backup(self):
        self.write({"theme": "dark", "statusLine": {"type": "command", "command": "echo hi"}})
        self.assertEqual(self.run_install("--force").returncode, 0)
        self.assertEqual(self.run_install("--force").returncode, 0)  # second run must not overwrite the backup
        self.assertEqual(self.read()["theme"], "dark")
        with open(self.settings + ".bak-before-statusline") as f:
            self.assertEqual(json.load(f)["statusLine"]["command"], "echo hi")

    def test_does_not_clobber_existing_status_line(self):
        mine = {"type": "command", "command": "echo hi"}
        self.write({"statusLine": mine})
        r = self.run_install()
        self.assertEqual(r.returncode, 0)
        self.assertEqual(self.read()["statusLine"], mine)
        self.assertIn("--force", r.stdout)

    def test_force_replaces(self):
        self.write({"statusLine": {"type": "command", "command": "echo hi"}})
        self.assertEqual(self.run_install("--force").returncode, 0)
        self.assertEqual(self.read()["statusLine"]["command"], LINE)

    def test_rerun_is_idempotent_and_upgrades_an_old_absolute_path(self):
        self.write({"statusLine": {"type": "command",
                                   "command": f"python3 {self.home}/.claude/statusline/statusline.py"}})
        self.assertEqual(self.run_install().returncode, 0)
        self.assertEqual(self.read()["statusLine"]["command"], LINE)
        self.assertEqual(self.run_install().returncode, 0)
        self.assertEqual(self.read()["statusLine"]["command"], LINE)

    def test_bad_settings_file_is_left_untouched(self):
        os.makedirs(os.path.dirname(self.settings))
        with open(self.settings, "w") as f:
            f.write('{"a": 1,}')
        r = self.run_install()
        self.assertNotEqual(r.returncode, 0)
        with open(self.settings) as f:
            self.assertEqual(f.read(), '{"a": 1,}')


if __name__ == "__main__":
    unittest.main()
