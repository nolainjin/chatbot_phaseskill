"""Record locking across processes and simulated Windows without fcntl."""

import builtins
import errno
import importlib.util
import json
import multiprocessing
import os
import sys
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from app import filelock, storage


def _load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def windows_storage(monkeypatch):
    original_import = builtins.__import__

    def without_fcntl(name, *args, **kwargs):
        if name == "fcntl":
            raise ModuleNotFoundError("No module named 'fcntl'")
        if name == "app.filelock":
            return isolated_filelock
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_fcntl)
    # Execute both modules afresh so cached imports cannot hide a POSIX import.
    isolated_filelock = _load_module("isolated_filelock", filelock.__file__)
    isolated_storage = _load_module("isolated_storage", storage.__file__)
    monkeypatch.setattr(isolated_filelock, "os", SimpleNamespace(
        name="nt", lseek=os.lseek, SEEK_SET=os.SEEK_SET,
    ))
    calls = []
    backend = SimpleNamespace(
        LK_LOCK=1, LK_UNLCK=0,
        locking=Mock(side_effect=lambda fd, mode, size: calls.append(
            (fd, mode, size, os.lseek(fd, 0, os.SEEK_CUR))
        )),
    )
    monkeypatch.setitem(sys.modules, "msvcrt", backend)
    return isolated_storage, isolated_filelock, backend, calls


@pytest.mark.parametrize("fail_body", [False, True])
def test_import_and_windows_lock_work_without_fcntl(windows_storage, tmp_path, fail_body):
    records, _, backend, calls = windows_storage
    conversations = tmp_path / "conversations"

    def write():
        with records.data_lock(conversations):
            fd = calls[0][0]
            # Unlock must seek back to byte zero, even if the offset changed.
            os.lseek(fd, 8, os.SEEK_SET)
            with records.data_lock(conversations):
                records.append_turn("shared", "user", "synthetic", base_dir=conversations)
                records.update_metadata("shared", {"synthetic": True}, base_dir=conversations)
            if fail_body:
                raise RuntimeError("synthetic failure")

    if fail_body:
        with pytest.raises(RuntimeError, match="synthetic failure"):
            write()
    else:
        write()
    fd = calls[0][0]
    assert calls == [(fd, backend.LK_LOCK, 1, 0), (fd, backend.LK_UNLCK, 1, 0)]
    with pytest.raises(OSError):
        os.fstat(fd)
    assert not records._LOCK_STATE.active
    payload = json.loads(next(conversations.glob("*/shared.json")).read_text(encoding="utf-8"))
    assert payload["turns"] == [{"seq": 0, "role": "user", "text": "synthetic"}]
    assert payload["synthetic"] is True


@pytest.mark.parametrize("error", [errno.EACCES, errno.EAGAIN, errno.EDEADLK])
def test_windows_lock_keeps_waiting_after_lk_lock_retry_limit(windows_storage, tmp_path, monkeypatch, error):
    records, locks, backend, _ = windows_storage
    sleep = Mock()
    monkeypatch.setattr(locks, "time", SimpleNamespace(sleep=sleep))
    backend.locking.side_effect = [OSError(error, "synthetic contention"), None, None]
    with records.data_lock(tmp_path / "conversations"):
        fd = backend.locking.call_args[0][0]
    assert backend.locking.call_args_list == [
        call(fd, backend.LK_LOCK, 1), call(fd, backend.LK_LOCK, 1),
        call(fd, backend.LK_UNLCK, 1),
    ]
    sleep.assert_called_once_with(0.05)


@pytest.mark.parametrize("failure", ["acquire", "release"])
def test_windows_lock_errors_close_descriptor_and_reset_state(windows_storage, tmp_path, failure):
    records, _, backend, _ = windows_storage
    error = OSError(errno.EIO, "synthetic lock failure")
    backend.locking.side_effect = [error] if failure == "acquire" else [None, error]
    with pytest.raises(OSError, match="synthetic lock failure"):
        with records.data_lock(tmp_path / "conversations"):
            pass
    assert backend.locking.call_count == (1 if failure == "acquire" else 2)
    fd = backend.locking.call_args[0][0]
    with pytest.raises(OSError):
        os.fstat(fd)
    assert not getattr(records._LOCK_STATE, "active", False)
    backend.locking.side_effect = None
    with records.data_lock(tmp_path / "conversations"):
        assert records._LOCK_STATE.active


def test_posix_lock_is_exclusive_and_released_on_body_error(monkeypatch, tmp_path):
    backend = SimpleNamespace(LOCK_EX=2, LOCK_UN=8, flock=Mock())
    monkeypatch.setitem(sys.modules, "fcntl", backend)
    monkeypatch.setattr(filelock, "os", SimpleNamespace(name="posix"))
    fd = os.open(tmp_path / ".records.lock", os.O_CREAT | os.O_RDWR, 0o600)
    try:
        with pytest.raises(RuntimeError, match="synthetic failure"):
            with filelock.exclusive_file_lock(fd):
                raise RuntimeError("synthetic failure")
        assert backend.flock.call_args_list == [
            call(fd, backend.LOCK_EX), call(fd, backend.LOCK_UN),
        ]
        os.fstat(fd)  # The caller still owns the open descriptor.
    finally:
        os.close(fd)


def _append_worker(conversations, worker, barrier):
    # Widen the read/replace race so a missing OS lock reliably loses turns.
    write = storage._write_private_json

    def slow_write(path, payload):
        time.sleep(0.01)
        write(path, payload)

    storage._write_private_json = slow_write
    for turn in range(10):
        barrier.wait(timeout=15)
        storage.append_turn("shared", "user", f"worker-{worker}-turn-{turn}", base_dir=conversations)


def test_concurrent_processes_append_without_losing_turns(tmp_path):
    conversations = tmp_path / "conversations"
    # spawn exercises the Windows process model on every platform.
    context = multiprocessing.get_context("spawn")
    barrier = context.Barrier(2)
    workers = [context.Process(target=_append_worker, args=(conversations, worker, barrier))
               for worker in range(2)]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=20)
        assert [worker.exitcode for worker in workers] == [0, 0]
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
            if worker.pid is not None:
                worker.join(timeout=5)
    payload = json.loads((conversations / date.today().isoformat() / "shared.json").read_text(encoding="utf-8"))
    assert [turn["seq"] for turn in payload["turns"]] == list(range(20))
    assert {turn["text"] for turn in payload["turns"]} == {
        f"worker-{worker}-turn-{turn}" for worker in range(2) for turn in range(10)
    }
