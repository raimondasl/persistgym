import pytest


@pytest.fixture(autouse=True)
def git_file_protocol_only(monkeypatch):
    """The guard's `git fetch` runs in a subprocess. Tests point origin at a local bare repo;
    this makes git refuse any network transport, so a misconfigured test cannot fetch from
    a real remote."""
    monkeypatch.setenv("GIT_ALLOW_PROTOCOL", "file")
