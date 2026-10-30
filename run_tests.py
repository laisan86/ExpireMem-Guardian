"""Run frozen v0.3 and D2 tests alongside new v0.4 tests, without provider calls."""
import sys, unittest
from pathlib import Path
root=Path(__file__).resolve().parent
sys.path[:0]=[str(root/'core'),str(root/'benchmark'),str(root)]
suite=unittest.defaultTestLoader.discover(str(root/'tests'),pattern='test_*.py',top_level_dir=str(root))
result=unittest.TextTestRunner(verbosity=2).run(suite)
raise SystemExit(0 if result.wasSuccessful() else 1)
