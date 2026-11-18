"""Requirements clarification. The live path accepts plain requirement text only."""
import json
import os
from urllib.error import URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


class ModelError(RuntimeError):
    pass


PROMPT = """你是 TestPilot 的需求澄清助手。用户消息是待分析的需求原文。
检查可验证的输入、成功条件、输出字段、失败条件。涉及接口时检查已约定的方法、路径、鉴权和预期响应。
仅对缺项和矛盾提问，不自行设定业务规则；只提与这条需求有关的问题，不重复问已经回答的问题。
返回一个 JSON 对象，字段 questions 为数组。每项有 quote（逐字引用原文中相关片段）和 question（具体中文问题）。
信息足以编写有明确预期的用例时返回空数组。"""


def result(text, payload):
    items = payload.get("questions") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ModelError("模型响应缺少 questions 数组")
    questions = []
    for item in items:
        if not isinstance(item, dict):
            raise ModelError("模型问题格式错误")
        quote, question = item.get("quote"), item.get("question")
        if not isinstance(quote, str) or not quote.strip() or quote not in text:
            raise ModelError("模型返回的引用与原文不符")
        if not isinstance(question, str) or not question.strip():
            raise ModelError("模型返回了空问题")
        pair = {"quote": quote, "question": question.strip()}
        if pair not in questions:
            questions.append(pair)
    return {"status": "NEEDS_INFO" if questions else "READY", "questions": questions}


def ask_model(text):
    url = os.getenv("TESTPILOT_MODEL_URL", "")
    model = os.getenv("TESTPILOT_MODEL", "")
    key = os.getenv("TESTPILOT_MODEL_KEY", "")
    target = urlsplit(url)
    if not model or not target.hostname or not (
        target.scheme == "https" or
        (target.scheme == "http" and target.hostname in ("127.0.0.1", "localhost", "::1"))
    ):
        raise ModelError("请配置模型名和完整的 HTTPS 聊天接口地址，本地模型可用 HTTP")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    body = {"model": model, "messages": [{"role": "system", "content": PROMPT},
                                          {"role": "user", "content": text}]}
    req = Request(url, data=json.dumps(body).encode(), headers=headers)
    try:
        with urlopen(req, timeout=30) as resp:
            envelope = json.load(resp)
        return json.loads(envelope["choices"][0]["message"]["content"])
    except (URLError, OSError, KeyError, IndexError, TypeError, ValueError) as exc:
        raise ModelError("模型调用失败或未返回有效 JSON，请检查服务配置后重试") from exc


def clarify(text, provider=ask_model):
    if not isinstance(text, str) or not text.strip() or len(text) > 16000:
        raise ValueError("需求正文必须为 1 到 16000 个字符")
    return result(text, provider(text))
