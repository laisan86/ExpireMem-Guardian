"""Deliberately offline fixture replay; NEVER claims VERIFED_LIVE or live Muse."""
from pathlib import Path
import sys
# The frozen v0.3 core imports muse_baseten by its historical module name.
# Make the public wrapper work without the Streamlit/test-runner path bootstrap.
_CORE_DIR = str(Path(__file__).resolve().parent / 'core')
if _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)
from tempfile import TemporaryDirectory
from core.guardian_core import run_demo


def run_offline():
    def offline_fetch(url, timeout):
        raise ConnectionError("Deliberate offline mode: no network request")
    with TemporaryDirectory(prefix="expiremem_studio_replay_") as temp:
        result = run_demo(Path(temp) / "run", fetch=offline_fetch, allow_offline_replay=True)
    if result["outcome"] != "GREEN_OFFLINE_REPLAY":
        raise AssertionError("Offline replay must not claim a verified-live outcome")
    return result
