"""引用定位：允许表格竖线、全半角和标点差异，但结果必须出自原文。"""
import pytest
from fastapi.testclient import TestClient

from backend.app.core.config import Settings
from backend.app.main import create_app
from backend.app.modules.agent import workflow
from backend.app.modules.agent.clarify import ModelError, clarify, locate_basis, locate_quote

TABLE = (
    "| 编号 | 要求 | 计划 |\n"
    "|---|---|---|\n"
    "| R03 | 检测整条行/列路径直到边界 | 独立纯逻辑模块 |\n"
    "| R04 | 畅通飞出、阻挡保留并反馈 | 飞出动画、碰撞晃动 |\n"
    "| R05 | 失误扣减并显示、用尽失败 | 每关 3 次失误机会 |\n"
)


@pytest.fixture
def settings(tmp_path):
    return Settings(database_path=tmp_path / "test.sqlite3")


def project(client, name="引用测试"):
    response = client.post("/api/projects", json={"name": name})
    return response.json()["id"]


def test_exact_quote_is_returned_unchanged():
    assert locate_quote("畅通飞出、阻挡保留并反馈", TABLE) == "畅通飞出、阻挡保留并反馈"


def test_table_pipes_are_tolerated_and_quote_is_cut_from_source():
    # 模型读表格常把竖线去掉，这不是编造，但返回的引用必须带原文的竖线
    located = locate_quote("R04 畅通飞出、阻挡保留并反馈", TABLE)
    assert located == "R04 | 畅通飞出、阻挡保留并反馈"
    assert located in TABLE


def test_punctuation_and_width_differences_are_tolerated():
    assert locate_quote("检测整条行/列路径直到边界", TABLE) == "检测整条行/列路径直到边界"
    assert locate_quote("R03检测整条行列路径直到边界", TABLE) == "R03 | 检测整条行/列路径直到边界"


def test_light_paraphrase_still_anchors_to_real_text():
    # 中间多写两个字，仍应锚定到原文，而不是把模型的话当成原文
    located = locate_quote("畅通飞出、阻挡保留并且及时反馈", TABLE)
    assert located is not None and located in TABLE


def test_fabricated_quote_is_rejected():
    assert locate_quote("支持微信支付并导出 PDF 报表", TABLE) is None


def test_too_short_quote_is_rejected():
    assert locate_quote("ab", TABLE) is None


def test_clarify_corrects_quote_and_keeps_questions():
    def provider(text):
        return {"questions": [{"quote": "R05 失误扣减并显示", "question": "扣到 0 之后如何表现？"}]}

    result = clarify(TABLE, provider)
    assert result["status"] == "NEEDS_INFO"
    assert result["questions"][0]["quote"] in TABLE
    assert "dropped" not in result


def test_clarify_drops_only_unlocatable_question():
    def provider(text):
        return {"questions": [
            {"quote": "畅通飞出、阻挡保留并反馈", "question": "保留时是否扣失误？"},
            {"quote": "支持微信支付并导出 PDF 报表", "question": "支付失败怎么提示？"},
        ]}

    result = clarify(TABLE, provider)
    assert len(result["questions"]) == 1
    assert result["dropped"] == 1


def test_clarify_retries_once_then_reports_actionable_error():
    calls = []

    def provider(text):
        calls.append(text)
        return {"questions": [{"quote": "支持微信支付并导出 PDF 报表", "question": "支付失败怎么提示？"}]}

    with pytest.raises(ModelError) as exc:
        clarify(TABLE, provider)
    assert len(calls) == 2
    assert "上一次返回的引用在原文中找不到" in calls[1]
    assert "精简" in str(exc.value)


def test_clarify_api_accepts_flattened_table_quote(settings):
    def provider(text):
        return {"questions": [{"quote": "R04 畅通飞出、阻挡保留并反馈", "question": "保留时是否扣失误？"}]}

    with TestClient(create_app(settings, agent_provider=provider)) as client:
        pid = project(client)
        rid = client.post(f"/api/projects/{pid}/requirements", json={"text": TABLE}).json()["id"]
        response = client.post(f"/api/projects/{pid}/agent/clarify", json={"requirement_id": rid})
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["questions"][0]["quote"] in TABLE
        assert body["status"] == "NEEDS_INFO"


def test_generate_corrects_expected_basis_to_source(monkeypatch, settings):
    draft_basis = "R04 畅通飞出、阻挡保留并反馈"

    def fake_ask_json(prompt, text, *, max_tokens=0):
        return {"drafts": [{
            "title": "阻挡时保留箭头",
            "expected_basis": draft_basis,
            "steps": [{
                "name": "move", "phase": "test", "endpoint_id": endpoint_id, "endpoint_version": 1,
                "headers": {}, "body": {"board": ["R.U"], "row": 0, "col": 0},
                "assertions": [{"type": "status", "expected": 200}], "extract": {},
            }],
        }]}

    with TestClient(create_app(settings)) as client:
        pid = project(client)
        rid = client.post(f"/api/projects/{pid}/requirements", json={"text": TABLE}).json()["id"]
        endpoint_id = client.post(
            f"/api/projects/{pid}/endpoints", json={"method": "POST", "path": "/game/move"}
        ).json()["id"]
        monkeypatch.setattr(workflow, "ask_json", fake_ask_json)
        response = client.post(
            f"/api/projects/{pid}/agent/generate",
            json={"requirement_id": rid, "requirement_version": 1},
        )
        assert response.status_code == 200, response.text
        basis = response.json()["drafts"][0]["expected_basis"]
        assert basis in TABLE and basis != draft_basis


REQUIREMENT = (
    "# 一箭又一箭 · 想要的功能\n\n"
    "- 点一支箭头，如果它前面没有别的箭头挡着，这支箭头就飞出去、从棋盘上消掉。\n"
    "- 如果前面有别的箭头挡着，这支箭头就留在原地，并算一次失误。\n"
    "- 每关一开始给 3 次失误机会。\n"
)


def test_paraphrased_basis_falls_back_to_closest_sentence():
    # 模型常把规则改写成自己的话，返回的仍应是需求里的原句
    located = locate_basis("被挡时箭头保留在棋盘上并扣一次失误", REQUIREMENT)
    assert located == "- 如果前面有别的箭头挡着，这支箭头就留在原地，并算一次失误。"
    assert located in REQUIREMENT


def test_basis_far_from_requirement_is_not_invented():
    assert locate_basis("喜欢用红色主题", REQUIREMENT) is None


def test_generate_keeps_paraphrased_basis_as_closest_source_sentence(monkeypatch, settings):
    def fake_ask_json(prompt, text, *, max_tokens=0):
        return {"drafts": [{
            "title": "被挡时扣一次机会",
            "expected_basis": "被挡时箭头留在原地并扣一次机会",
            "steps": [{
                "name": "move", "phase": "test", "endpoint_id": endpoint_id, "endpoint_version": 1,
                "headers": {}, "body": {"board": ["R.U"], "row": 0, "col": 0},
                "assertions": [{"type": "status", "expected": 200}], "extract": {},
            }],
        }]}

    with TestClient(create_app(settings)) as client:
        pid = project(client)
        rid = client.post(f"/api/projects/{pid}/requirements", json={"text": REQUIREMENT}).json()["id"]
        endpoint_id = client.post(
            f"/api/projects/{pid}/endpoints", json={"method": "POST", "path": "/game/move"}
        ).json()["id"]
        monkeypatch.setattr(workflow, "ask_json", fake_ask_json)
        response = client.post(
            f"/api/projects/{pid}/agent/generate",
            json={"requirement_id": rid, "requirement_version": 1},
        )
        assert response.status_code == 200, response.text
        basis = response.json()["drafts"][0]["expected_basis"]
        assert basis in REQUIREMENT


def test_generate_does_not_reject_batch_when_basis_is_unlocatable(monkeypatch, settings):
    # 引文对不上原文属于「依据写得不准」，不该让整批候选生成失败
    def fake_ask_json(prompt, text, *, max_tokens=0):
        return {"drafts": [{
            "title": "随手写的依据",
            "expected_basis": "总之点下去要有反馈",
            "steps": [{
                "name": "move", "phase": "test", "endpoint_id": endpoint_id, "endpoint_version": 1,
                "headers": {}, "body": {"board": ["R.U"], "row": 0, "col": 0},
                "assertions": [{"type": "status", "expected": 200}], "extract": {},
            }],
        }]}

    with TestClient(create_app(settings)) as client:
        pid = project(client)
        rid = client.post(f"/api/projects/{pid}/requirements", json={"text": REQUIREMENT}).json()["id"]
        endpoint_id = client.post(
            f"/api/projects/{pid}/endpoints", json={"method": "POST", "path": "/game/move"}
        ).json()["id"]
        monkeypatch.setattr(workflow, "ask_json", fake_ask_json)
        response = client.post(
            f"/api/projects/{pid}/agent/generate",
            json={"requirement_id": rid, "requirement_version": 1},
        )
        assert response.status_code == 200, response.text
        assert response.json()["drafts"][0]["expected_basis"] == "总之点下去要有反馈"
