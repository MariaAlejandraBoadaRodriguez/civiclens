"""Give freed memory back to the OS after heavy work (free hosting has 512 MB of RAM).

pandas/DuckDB/scikit-learn jobs leave large freed blocks in the glibc heap; without a trim
the next job stacks on top of them and the instance is restarted for exceeding its limit.
"""

from __future__ import annotations

import ctypes
import gc
import logging

log = logging.getLogger(__name__)

try:
    _libc = ctypes.CDLL("libc.so.6")
except OSError:  # not glibc (macOS, musl): nothing to trim
    _libc = None


def release() -> None:
    gc.collect()
    if _libc is not None:
        try:
            _libc.malloc_trim(0)
        except AttributeError:
            log.debug("malloc_trim is not available")
