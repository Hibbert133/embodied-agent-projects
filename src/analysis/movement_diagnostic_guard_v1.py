"""Process-local fail-closed boundary for the read-only diagnostic entry points."""
import builtins
from contextlib import contextmanager
import sys

BLOCKED = ("metaworld", "mujoco", "gym", "gymnasium", "requests", "httpx", "openai", "zhipuai", "scipy.optimize")


@contextmanager
def read_only_analysis_guard():
    original = builtins.__import__
    active = [True]

    def guarded(name, *args, **kwargs):
        if any(name == x or name.startswith(x+".") for x in BLOCKED):
            raise RuntimeError("diagnostic forbids simulator / network / optimizer import: "+name)
        return original(name, *args, **kwargs)

    def audit(event, args):
        if active[0] and (event.startswith("socket.") or event in ("subprocess.Popen", "os.system", "os.exec", "os.posix_spawn")):
            raise RuntimeError("diagnostic forbids network / child process: "+event)

    builtins.__import__ = guarded
    sys.addaudithook(audit)
    try:
        yield
    finally:
        active[0] = False
        builtins.__import__ = original
