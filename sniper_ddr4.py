"""
DDR4 2x8 3200MHz Deal Sniper — Canonical Forwarder.
Delegates execution to universal_sniper.py using Preset 1.
Ensures full backward compatibility while eliminating code duplication.
"""

import os
import sys
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

if __name__ == "__main__":
    script_path = os.path.join(PROJECT_ROOT, "universal_sniper.py")
    cmd = [sys.executable, script_path, "--preset", "1"] + sys.argv[1:]
    sys.exit(subprocess.call(cmd))
