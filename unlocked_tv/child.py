"""Apply child restrictions after exec, avoiding preexec hooks in a threaded GUI."""
import ctypes
import os
import resource
import sys

if sys.platform == "linux":
    if ctypes.CDLL(None).prctl(38, 1, 0, 0, 0) != 0:
        raise SystemExit("Unable to restrict privilege escalation")
resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
os.execvpe(sys.argv[1], sys.argv[1:], os.environ)
