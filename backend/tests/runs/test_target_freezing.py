import json

import pytest

from app.modules.runs.dependencies import PreflightRejected
from app.modules.runs.models import CaseRef

from .conftest import FakeDependencies, case_snapshot, login_step, me_step
from .test_project_targets import start_target


def test_environment_change_never_sends_a_credentials_to_b(service_factory):
    password_a = "service-a-distinct-password"
    password_b = "service-b-distinct-password"
    target_b = start_target("service-b", password_b)
    target_a = start_target("service-a", password_a)
    try:
        snapshot = case_snapshot(
            "case-b",
            "环境变更后禁止串用凭据",
            [login_step(), me_step("service-b")],
        )
        dependencies = FakeDependencies(
            [snapshot],
            environment={"username": "account-b", "password": password_b},
            execution_target={
                "target": "local",
                "service_id": "service-b",
                "base_url": target_b.base_url,
                "environment_version": 1,
            },
        )
        service = service_factory(dependencies)
        run_id = service.create_run("project-1", [CaseRef(id="case-b", version=1)])

        # Switch both target and credentials to a new environment before execution.
        dependencies.execution_target = {
            "target": "local",
            "service_id": "service-a",
            "base_url": target_a.base_url,
            "environment_version": 2,
        }
        dependencies.environment = {"username": "account-a", "password": password_a}
        service.execute_run(run_id)

        detail = service.get_run("project-1", run_id)
        assert detail.counts.ERROR == 1
        assert detail.target.service_id == "service-b"
        assert detail.target.base_url == target_b.base_url
        assert detail.target.environment_version == 1
        assert all(
            step.error_stage == "environment_changed"
            and "重新预检" in step.response_summary
            for step in detail.results[0].steps
        )
        assert target_b.received() == []
        assert target_a.received() == []
        public_evidence = detail.model_dump_json() + json.dumps(
            service.get_frozen_snapshot("project-1", run_id), ensure_ascii=False
        )
        assert password_a not in public_evidence
        assert password_b not in public_evidence
        assert "account-a" not in public_evidence
        assert "account-b" not in public_evidence
    finally:
        target_a.stop()
        target_b.stop()


def test_legacy_null_target_batch_keeps_demo_behavior(service_factory, demo_server):
    snapshot = case_snapshot(
        "case-legacy", "历史无目标批次", [login_step(), me_step()]
    )
    service = service_factory(FakeDependencies([snapshot]), base_url=demo_server)
    run_id = service.repository.create_run("project-1", [snapshot], target=None)
    service.execute_run(run_id)
    detail = service.get_run("project-1", run_id)
    assert detail.counts.PASS == 1
    assert detail.target is None
    assert service.get_frozen_snapshot("project-1", run_id)["target"] is None


def test_incomplete_local_target_is_rejected_before_batch_creation(service_factory):
    snapshot = case_snapshot("case-invalid", "无效目标", [login_step(), me_step()])
    dependencies = FakeDependencies(
        [snapshot],
        execution_target={
            "target": "local",
            "service_id": "incomplete-service",
            "base_url": None,
        },
    )
    service = service_factory(dependencies)
    with pytest.raises(PreflightRejected, match="缺少服务标识或地址"):
        service.create_run("project-1", [CaseRef(id="case-invalid", version=1)])
    with service.repository._connect() as connection:
        assert connection.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0
