"""Shared test environment for the explicit loopback-only application surface."""

import os


os.environ.setdefault("PRIVATE_LOCAL_UI", "1")
