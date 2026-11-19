from .phase2_evidence import verify


def test_phase2_four_outcomes_are_reproducible(tmp_path):
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
