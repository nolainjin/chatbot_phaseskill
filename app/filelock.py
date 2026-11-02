"""Blocking, exclusive file locks using the host platform's standard library."""

import errno
import os
import time
from contextlib import contextmanager


@contextmanager
def exclusive_file_lock(fd: int):
    """Lock an open descriptor; the caller retains ownership of the descriptor."""
    if os.name == "nt":
        import msvcrt

        while True:
            os.lseek(fd, 0, os.SEEK_SET)
            try:
                # Windows permits locking a byte range beyond EOF, including
                # byte zero of a newly created, empty .records.lock file.
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
                break
            except OSError as exc:
                if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                    raise
                # LK_LOCK gives up after ten retries. Keep waiting, as flock
                # without LOCK_NB does, even for long-running imports/purges.
                time.sleep(0.05)
        try:
            yield
        finally:
            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
