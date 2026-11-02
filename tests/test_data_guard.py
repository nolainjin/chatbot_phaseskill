"""Exercise the real pytest hooks against disposable repository data only."""

import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.parametrize("mutation", ["none", "new", "modified", "deleted", "collection", "teardown"])
def test_repository_data_guard_reports_file_changes(tmp_path, mutation):
    sandbox = tmp_path / "sandbox"
    tests = sandbox / "tests"
    tests.mkdir(parents=True)
    shutil.copyfile(Path(__file__).with_name("conftest.py"), tests / "conftest.py")
    data = sandbox / "data"
    data.mkdir()
    (data / "existing.txt").write_text("preserved")
    operations = {
        "none": "pass",
        "new": "(root / 'new.txt').write_text('synthetic')",
        "modified": "p = root / 'existing.txt'; s = p.stat(); os.utime(p, ns=(s.st_atime_ns, s.st_mtime_ns + 1000000))",
        "deleted": "(root / 'existing.txt').unlink()",
        "collection": "pass",
        "teardown": "pass",
    }
    source = "import os\nfrom pathlib import Path\nimport pytest\nroot = Path(__file__).resolve().parents[1] / 'data'\n"
    if mutation == "collection":
        source += "(root / 'collection.txt').write_text('synthetic')\n"
    if mutation == "teardown":
        source += "@pytest.fixture(autouse=True)\ndef final_write():\n    yield\n    (root / 'teardown.txt').write_text('synthetic')\n"
    source += "def test_probe():\n    " + operations[mutation] + "\n"
    (tests / "test_probe.py").write_text(source)
    process = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=sandbox,
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        capture_output=True, text=True, timeout=30,
    )
    if mutation == "none":
        assert process.returncode == 0, process.stdout + process.stderr
    else:
        assert process.returncode == 1, process.stdout + process.stderr
        assert "Repository data/ changed during tests:" in process.stdout
        filename = {"new": "new.txt", "modified": "existing.txt", "deleted": "existing.txt",
                    "collection": "collection.txt", "teardown": "teardown.txt"}[mutation]
        assert filename in process.stdout
