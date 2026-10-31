#!/usr/bin/env python3
"""Prints the status line for made-up numbers: python3 demo.py"""
import json, os, subprocess, sys, time

now = time.time()
fake = {
    "session_id": "demo", "model": {"display_name": "Sonnet 5.5"}, "effort": {"level": "medium"},
    "workspace": {"current_dir": os.getcwd(), "project_dir": os.getcwd()},
    "context_window": {"used_percentage": 18.4},
    "rate_limits": {"five_hour": {"used_percentage": 31, "resets_at": now + 3.7 * 3600},
                    "seven_day": {"used_percentage": 12, "resets_at": now + 4.2 * 86400}},
}
here = os.path.dirname(os.path.abspath(__file__))
subprocess.run([sys.executable, os.path.join(here, "statusline.py")], input=json.dumps(fake), text=True)
print()
