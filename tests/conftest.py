"""Suite-wide fixtures."""
import os

import pytest


@pytest.fixture(autouse=True)
def _restore_environ():
    """Snapshot ``os.environ`` before every test and restore it afterwards, so a test that
    sets, pops or forgets a variable (a backend switch, a probe read from a .env file, an
    API key) cannot leak it into the tests that run after it."""
    saved = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(saved)
