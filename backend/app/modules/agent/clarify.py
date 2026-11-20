"""Clarify plain requirements or requirements grounded in a project import."""
import difflib
import json
import os
import re
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urlsplit


class ModelError(RuntimeError):
    pass


class UnlocatedQuote(ModelError):
    """模型的引用在原文里定位不到；保留原话，重试时提示模型。"""

    def __init__(self, quote):
        super().__init__("模型返回的引用与原文不符")
        self.quote = quote


PROMPT = """你是 TestPilot 的需求澄清助手。用户消息里有当前需求原文，可能还有项目自带的接口说明（interface_descriptions）。

背景：这个被测项目是别人（或 AI）照着一句功能需求做出来的。做项目时遇到需求没说清的地方，往往会自己拍板、直接写进实现里，需求原文里压根没提。这些「已经替需求方做了决定、却没跟他确认过」的功能点，就是你要找出来的东西：把它们翻成大白话问一句「你想要的是不是这样」，让不懂技术的人也能确认。

只针对功能/业务规则，不针对代码怎么写。对照需求原文和接口说明，重点留意这几类最容易被自己拍板的情况：点到空白或无效位置算不算一次操作、次数或机会用完后会怎样、判断范围只看紧挨着的一格还是一路看到边界、完成或通关后是否自动继续、重新开始是否恢复原状，以及任何实现里定了、需求里却没写的选择。接口说明里定了不等于用户同意过，恰恰要问。

必须让完全不懂技术的人能看懂并回答：用日常大白话，不出现字段名、状态码、请求头、鉴权、接口路径、坐标基准、数据格式等实现术语；接口说明只用来发现这些决定，不要照抄里面的细节，也不要向用户索取字段、状态码、登录方式之类的实现信息。

quote 必须逐字来自需求原文（或选中的原始片段），挂到相关那句话上，不要引用接口说明里的话。仅对确实没交代的功能点提问，不自行设定业务规则，不重复问已经回答的问题。

返回一个 JSON 对象，字段 questions 为数组。每项有 quote（逐字引用原文中相关片段）和 question（具体中文大白话问题）。功能都确认清楚、足以编写有明确预期的用例时返回空数组。"""

RETRY_NOTE = """

【上一次返回的引用在原文中找不到：{sample}】
请重新输出完整结果：quote 必须从原文里直接复制连续片段。表格行要保留原文的 | 分隔符，
不要改写、不要合并单元格、不要补写标点。"""


def _fold(text):
    """只保留字母、数字和汉字，返回折叠串及每个字符对应的原文下标。

    模型读 Markdown 表格时经常把 | 去掉、把全角标点换成半角，这些差异不算编造，
    但引用必须是原文里真实存在的片段，所以先折叠再匹配，最后回切原文。
    """
    folded, spans = [], []
    for index, raw in enumerate(text):
        for char in unicodedata.normalize("NFKC", raw):
            if char.isalnum():
                folded.append(char.lower())
                spans.append(index)
    return "".join(folded), spans


def locate_quote(quote, text):
    """在 text 里定位 quote，返回原文中的连续片段；定位不到返回 None。"""
    if not isinstance(quote, str) or not isinstance(text, str):
        return None
    quote = quote.strip()
    if not quote:
        return None
    if quote in text:
        return quote
    folded_text, spans = _fold(text)
    folded_quote, _ = _fold(quote)
    if len(folded_quote) < 4 or not folded_text:
        return None
    position = folded_text.find(folded_quote)
    if position >= 0:
        return text[spans[position]:spans[position + len(folded_quote) - 1] + 1]
    # 允许模型改写少量字：取最长公共片段，覆盖六成以上才采用，返回的仍是原文
    matcher = difflib.SequenceMatcher(None, folded_text, folded_quote, autojunk=False)
    block = matcher.find_longest_match(0, len(folded_text), 0, len(folded_quote))
    if block.size < max(8, int(len(folded_quote) * 0.6)):
        return None
    return text[spans[block.a]:spans[block.a + block.size - 1] + 1]


_SENTENCE_BREAK = re.compile(r"[。！？；\n]+")


def _sentences(text):
    """按句末标点和换行切成句，保留原文、去掉首尾空白。"""
    parts, start = [], 0
    for match in _SENTENCE_BREAK.finditer(text):
        segment = text[start:match.end()].strip()
        if segment:
            parts.append(segment)
        start = match.end()
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def locate_basis(claim, text, *, threshold=0.4):
    """给用例的预期依据找原文出处。

    模型常常把规则改写成自己的话（「被挡时箭头保留并扣一次失误」），逐字匹配
    和长片段匹配都会落空。这里退一步：把原文切成句，挑跟 claim 重合度最高的
    一整句，只要重合够多就采用——存下来的依然是原文句子，不是模型的改写。
    """
    located = locate_quote(claim, text)
    if located is not None:
        return located
    if not isinstance(claim, str) or not isinstance(text, str):
        return None
    folded_claim, _ = _fold(claim)
    if len(folded_claim) < 4:
        return None
    best, best_score = None, 0.0
    for sentence in _sentences(text):
        folded_sentence, _ = _fold(sentence)
        if not folded_sentence:
            continue
        matcher = difflib.SequenceMatcher(None, folded_sentence, folded_claim, autojunk=False)
        matched = sum(block.size for block in matcher.get_matching_blocks())
        score = matched / len(folded_claim)
        if score > best_score:
            best, best_score = sentence, score
    if best is None or best_score < threshold:
        return None
    return best


def result(text, payload, *, source_excerpt=None):
    items = payload.get("questions") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ModelError("模型响应缺少 questions 数组")
    questions, dropped, sample = [], 0, None
    for item in items:
        if not isinstance(item, dict):
            raise ModelError("模型问题格式错误")
        quote, question = item.get("quote"), item.get("question")
        if not isinstance(quote, str) or not quote.strip():
            raise ModelError("模型返回的引用与原文不符")
        if not isinstance(question, str) or not question.strip():
            raise ModelError("模型返回了空问题")
        located = locate_quote(quote, text)
        path = None
        if located is None and source_excerpt is not None:
            located = locate_quote(quote, source_excerpt["text"])
            if located is not None:
                path = source_excerpt["path"]
        if located is None:
            # 单条引用定位不到不拖垮整批，丢弃并计数，最后如实告知
            dropped += 1
            sample = sample or quote
            continue
        pair = {"quote": located, "question": question.strip()}
        if path:
            pair["source_path"] = path
        if pair not in questions:
            questions.append(pair)
    if dropped and not questions:
        raise UnlocatedQuote(sample)
    response = {"status": "NEEDS_INFO" if questions else "READY", "questions": questions}
    if dropped:
        response["dropped"] = dropped
    return response


def _retry(run, first):
    try:
        return run(RETRY_NOTE.format(sample=first.quote[:120]))
    except UnlocatedQuote:
        raise ModelError(
            "模型两次给出的引用都定位不到原文，请把需求精简成几句关键描述后重试"
        ) from None


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
只检查当前需求指定范围。没有接口说明时，就按需求里没交代、但玩这个功能一定会遇到的情况提问。
测试账号密码若由环境配置提供，视为已说明，不索取具体值。明确标为范围外的行为不追问。""", text)


def clarify(text, provider=ask_model):
    if not isinstance(text, str) or not text.strip() or len(text) > 16000:
        raise ValueError("需求正文必须为 1 到 16000 个字符")
    try:
        return result(text, provider(text))
    except UnlocatedQuote as first:
        return _retry(lambda note: result(text, provider(text + note)), first)


def clarify_project(context, provider=None):
    prompt = PROMPT + """
用户消息为 JSON 数据。requirement.text 是当前已保存的需求，包含用户补充答案，优先于旧文档，也优先于接口说明里的实现选择。
source_excerpt 是选中的原始片段。interface_descriptions 是项目自带的接口说明，记录做项目时自己拍板的实现选择；用它对照需求，找出需求没写、实现却已经定了的功能点，但不要照抄它的字段名和状态码去问人。
quote 须逐字来自当前需求或选中片段，不要引用 interface_descriptions。沿用已明确的答案，不索取凭据，只分析该需求涉及的功能范围。
"""
    raw = json.dumps(context, ensure_ascii=False)
    source_excerpt = context.get("source_excerpt")

    def run(note=""):
        payload = ask_json(prompt + note, raw) if provider is None else provider(raw + note)
        return result(context["requirement"]["text"], payload, source_excerpt=source_excerpt)

    try:
        return run()
    except UnlocatedQuote as first:
        return _retry(run, first)
