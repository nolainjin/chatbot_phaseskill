"""Shared test environment for the explicit loopback-only application surface."""

import os
from pathlib import Path

import pytest


os.environ.setdefault("PRIVATE_LOCAL_UI", "1")

_REPO_DATA_DIR = Path(__file__).resolve().parents[1] / "data"
_DATA_BASELINE = pytest.StashKey[dict[str, int]]()


def _data_snapshot(root):
    return {
        path.relative_to(root).as_posix(): path.stat().st_mtime_ns
        for path in root.rglob("*") if path.is_file()
    }


def pytest_sessionstart(session):
    # Capture before collection, including tests which write during import.
    session.config.stash[_DATA_BASELINE] = _data_snapshot(_REPO_DATA_DIR)


def pytest_sessionfinish(session, exitstatus):
    before = session.config.stash[_DATA_BASELINE]
    after = _data_snapshot(_REPO_DATA_DIR)
    changes = []
    for name in sorted(before.keys() | after.keys()):
        if name not in before:
            changes.append(f"new: {name}")
        elif name not in after:
            changes.append(f"deleted: {name}")
        elif before[name] != after[name]:
            changes.append(f"modified: {name}")
    if changes:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        message = "Repository data/ changed during tests:\n" + "\n".join(changes)
        if reporter is not None:
            reporter.write_sep("=", message, red=True)
        else:
            print(message)
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


@pytest.fixture(autouse=True)
def isolated_data_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))
