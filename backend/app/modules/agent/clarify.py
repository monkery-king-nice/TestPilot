"""Clarify plain requirements or requirements grounded in a project import."""
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


class ModelError(RuntimeError):
    pass


PROMPT = """你是 TestPilot 的需求澄清助手。用户消息是待分析的需求原文。
检查可验证的输入、成功条件、输出字段、失败条件。涉及接口时检查已约定的方法、路径、鉴权和预期响应。
仅对缺项和矛盾提问，不自行设定业务规则；只提与这条需求有关的问题，不重复问已经回答的问题。
返回一个 JSON 对象，字段 questions 为数组。每项有 quote（逐字引用原文中相关片段）和 question（具体中文问题）。
信息足以编写有明确预期的用例时返回空数组。"""


def result(text, payload, *, source_excerpt=None):
    items = payload.get("questions") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ModelError("模型响应缺少 questions 数组")
    questions = []
    for item in items:
        if not isinstance(item, dict):
            raise ModelError("模型问题格式错误")
        quote, question = item.get("quote"), item.get("question")
        if not isinstance(quote, str) or not quote.strip():
            raise ModelError("模型返回的引用与原文不符")
        if not isinstance(question, str) or not question.strip():
            raise ModelError("模型返回了空问题")
        pair = {"quote": quote, "question": question.strip()}
        if quote not in text:
            if source_excerpt is None or quote not in source_excerpt["text"]:
                raise ModelError("模型返回的引用与原文不符")
            pair["source_path"] = source_excerpt["path"]
        if pair not in questions:
            questions.append(pair)
    return {"status": "NEEDS_INFO" if questions else "READY", "questions": questions}


def ask_json(prompt, text, *, max_tokens=2400):
    official_url = "https://api.deepseek.com/chat/completions"
    url = os.getenv("TESTPILOT_MODEL_URL", official_url)
    model = os.getenv("TESTPILOT_MODEL", "deepseek-flash" if url == official_url else "")
    key = os.getenv("TESTPILOT_MODEL_KEY", "")
    if url == official_url:
        key = os.getenv("DEEPSEEK_API_KEY") or key
        if not key:
            raise ModelError("请在本机设置 DEEPSEEK_API_KEY 后重试")
    target = urlsplit(url)
    if not model or not target.hostname or not (
        target.scheme == "https" or
        (target.scheme == "http" and target.hostname in ("127.0.0.1", "localhost", "::1"))
    ):
        raise ModelError("请配置模型名和完整的 HTTPS 聊天接口地址，本地模型可用 HTTP")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text},
        ],
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
    }
    if url == official_url:
        body["thinking"] = {"type": "disabled"}
    req = Request(url, data=json.dumps(body).encode(), headers=headers)
    try:
        with urlopen(req, timeout=45) as resp:
            envelope = json.load(resp)
        return json.loads(envelope["choices"][0]["message"]["content"])
    except HTTPError as exc:
        exc.close()
        raise ModelError(f"模型服务返回 HTTP {exc.code}，请核对服务配置后重试") from exc
    except (URLError, OSError) as exc:
        raise ModelError("未能连接模型服务，请检查网络后重试") from exc
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ModelError("模型未返回可用的 JSON，请检查模型名和输出配置后重试") from exc


def ask_model(text):
    return ask_json(PROMPT + """
例如 {"questions":[{"quote":"原文片段","question":"待确认的条件是什么？"}]}。
只检查当前需求指定范围。测试账号密码若由环境配置提供，视为已说明，不索取具体值。
明确标为范围外的行为不追问。""", text)


def clarify(text, provider=ask_model):
    if not isinstance(text, str) or not text.strip() or len(text) > 16000:
        raise ValueError("需求正文必须为 1 到 16000 个字符")
    return result(text, provider(text))


def clarify_project(context, provider=None):
    prompt = PROMPT + """
用户消息为 JSON 数据。requirement.text 是当前已保存的需求，包含用户补充答案，优先于旧文档。
source_excerpt 是选中的原始片段。接口说明可用于判断是否缺项。quote 须逐字来自当前需求或选中片段。
沿用已明确的答案，不索取凭据。只分析该需求涉及的范围。
"""
    raw = json.dumps(context, ensure_ascii=False)
    response = ask_json(prompt, raw) if provider is None else provider(raw)
    return result(context["requirement"]["text"], response, source_excerpt=context.get("source_excerpt"))
