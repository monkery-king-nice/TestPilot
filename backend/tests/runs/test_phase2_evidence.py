import sqlite3

import pytest

from .phase2_evidence import loopback_no_proxy, temporary_sqlite_directory, verify


def test_phase2_four_outcomes_are_reproducible(tmp_path, monkeypatch):
    # Reproduce a machine-wide proxy without allowing ambient NO_PROXY settings
    # to hide the problem. Both this test and verify() explicitly bypass loopback.
    proxy_names = (
        "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY",
        "http_proxy", "https_proxy", "all_proxy",
    )
    for name in proxy_names:
        monkeypatch.setenv(name, "http://127.0.0.1:9")
    monkeypatch.setenv("NO_PROXY", "")
    monkeypatch.setenv("no_proxy", "")

    with loopback_no_proxy():
        evidence = verify(tmp_path)

    assert evidence["summary"] == {
        "PASS": "PASS",
        "FAIL": "FAIL",
        "BLOCKED": "BLOCKED",
        "ERROR": "ERROR",
    }

    results = {item["scenario"]: item for item in evidence["results"]}
    assert results["PASS"]["steps"][0]["http_status"] == 401
    assert results["FAIL"]["steps"][1]["error_stage"] == "assertion"
    assert results["BLOCKED"]["demo_requests_received"] == ["POST /auth/login"]
    assert results["BLOCKED"]["steps"][1]["error_stage"] == "setup_failed"
    assert results["ERROR"]["steps"][0]["error_stage"] == "connection"
    assert results["ERROR"]["failure_source"].startswith("单独且已停止")
    assert evidence["timeout_control"]["counted_as_stopped_instance_evidence"] is False


def test_sqlite_cleanup_does_not_mask_original_assertion():
    class LeakedConnection:
        def __init__(self, path):
            self.connection = sqlite3.connect(path)
            self.cycle = self

        def __del__(self):
            self.connection.close()

    with pytest.raises(AssertionError, match="original assertion"):
        with temporary_sqlite_directory() as temp:
            # An unreachable cycle simulates a sqlite finalizer that needs gc.
            LeakedConnection(temp + "/active.sqlite3")
            raise AssertionError("original assertion")
