"""Use CPython's existing Win32 API fallback without launching optional ver."""
from contextlib import contextmanager
from pathlib import Path
import hashlib,os,sys

ROOT=Path(__file__).resolve().parents[2]
PLATFORM_PATH=ROOT/'.python310/Lib/platform.py'


def module_sha256():return hashlib.sha256(PLATFORM_PATH.read_bytes()).hexdigest()


@contextmanager
def in_process_queries(expected_sha256):
    import platform
    from unittest.mock import patch
    try:known_module=os.name=='nt' and Path(platform.__file__).samefile(PLATFORM_PATH)
    except OSError as error:raise RuntimeError('unknown platform module') from error
    if not known_module:raise RuntimeError('locked Windows platform module required')
    if module_sha256()!=expected_sha256:raise RuntimeError('platform module hash changed')
    try:version=tuple(sys.getwindowsversion().platform_version)
    except (AttributeError,TypeError) as error:raise RuntimeError('unknown native Windows version') from error
    if len(version)!=3 or any(type(v) is not int or v<0 for v in version):raise RuntimeError('unknown native Windows version')
    receipt=dict(schema='OCCAM_PLATFORM_BOOTSTRAP_V1',platform_module_sha256=expected_sha256,native_windows_version=list(version),
        optional_command_calls_suppressed=0,optional_shell_probe_disabled=True,original_function_restored=False)
    original=platform._syscmd_ver
    def unavailable_command(system='',release='',version='',supported_platforms=('win32','win16','dos')):
        # Empty defaults trigger the unmodified win32_ver ValueError fallback.
        # Caller-provided defaults keep the original helper's fallback meaning.
        receipt['optional_command_calls_suppressed']+=1
        return system,release,version
    try:
        with patch.object(platform,'_syscmd_ver',unavailable_command):yield receipt
    finally:receipt['original_function_restored']=platform._syscmd_ver is original
