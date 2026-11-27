"""Read bounded ZIP metadata, selected text and OpenAPI declarations without extraction."""

import json
import re
import stat
import unicodedata
import zlib
from collections.abc import Iterator
from contextlib import contextmanager
from io import BytesIO
from pathlib import PurePosixPath
from zipfile import ZIP_DEFLATED, ZIP_STORED, BadZipFile, ZipFile, ZipInfo

from fastapi import HTTPException
from pydantic import ValidationError

from .models import EndpointInput

MAX_UPLOAD = 40 * 1024 * 1024
MAX_EXPANDED = 48 * 1024 * 1024
MAX_ENTRIES = 512
MAX_TEXT = 1024 * 1024
MAX_PREVIEW = 16000
MAX_CANDIDATES = 256
CHUNK_SIZE = 64 * 1024
TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


class UnsupportedText(HTTPException):
    def __init__(self, detail: str):
        super().__init__(422, detail)


@contextmanager
def open_zip(data: bytes) -> Iterator[ZipFile]:
    try:
        with ZipFile(BytesIO(data)) as archive:
            yield archive
    except UnicodeDecodeError as exc:
        raise HTTPException(422, "ZIP 文件名编码无效，请用 UTF-8 文件名重新打包") from exc
    except (BadZipFile, EOFError, RuntimeError, NotImplementedError, zlib.error) as exc:
        raise HTTPException(422, "ZIP 内容损坏或压缩格式不受支持，请重新打包") from exc


def safe_name(name: str, *, directory: bool = False) -> str:
    trimmed = name.removesuffix("/") if directory else name
    if (
        len(trimmed) > 512
        or any(part in {"", ".", ".."} or part.endswith((" ", ".")) for part in trimmed.split("/"))
        or any(char in "\\:" or unicodedata.category(char) == "Cc" for char in trimmed)
    ):
        raise HTTPException(422, "ZIP 含非法路径，请使用普通的相对文件名")
    return trimmed


def upload_name(filename: str) -> str:
    if "/" in filename or not filename.lower().endswith(".zip"):
        raise HTTPException(422, "请选择 ZIP 文件，并传递不带目录的文件名")
    return safe_name(filename)


def entries(archive: ZipFile) -> list[ZipInfo]:
    infos = archive.infolist()
    if len(infos) > MAX_ENTRIES:
        raise HTTPException(413, f"ZIP 最多允许 {MAX_ENTRIES} 个条目")
    if sum(info.file_size for info in infos) > MAX_EXPANDED:
        raise HTTPException(413, "ZIP 展开总大小超过 48 MiB")
    seen = set()
    files = []
    for info in infos:
        name = safe_name(info.orig_filename, directory=info.is_dir())
        if not info.flag_bits & 0x800 and not name.isascii():
            raise HTTPException(422, "ZIP 含非 UTF-8 文件名，请用支持 UTF-8 的工具重新打包")
        key = unicodedata.normalize("NFC", name).casefold()
        if key in seen:
            raise HTTPException(422, "ZIP 含重复文件路径，请去重后重新上传")
        seen.add(key)
        mode = stat.S_IFMT(info.external_attr >> 16)
        if mode not in {0, stat.S_IFREG, stat.S_IFDIR} or info.external_attr & 0x400:
            raise HTTPException(422, "ZIP 不接受链接或其他特殊文件")
        if info.flag_bits & 1 or info.compress_type not in {ZIP_STORED, ZIP_DEFLATED}:
            raise HTTPException(422, "ZIP 不接受加密条目，仅支持 Stored 或 Deflate 压缩")
        # Validate local headers and overlapping entries without reading unrelated source files.
        with archive.open(info):
            pass
        if not info.is_dir():
            files.append(info)
    return files


def read_text(archive: ZipFile, info: ZipInfo, remaining: list[int]) -> str:
    if info.file_size > MAX_TEXT:
        raise HTTPException(413, "单个可读文件最多 1 MiB，请改选文档或上传较小文档")
    limit = min(MAX_TEXT, remaining[0])
    payload = bytearray()
    with archive.open(info) as stream:
        while chunk := stream.read(min(CHUNK_SIZE, limit - len(payload) + 1)):
            payload.extend(chunk)
            if len(payload) > limit:
                raise HTTPException(413, "实际解压数据超过读取限额")
    remaining[0] -= len(payload)
    if len(payload) != info.file_size:
        raise HTTPException(422, "ZIP 条目大小与实际内容不一致")
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UnsupportedText("文件正文须为 UTF-8 或 UTF-8 BOM，请转码后重试") from exc
    if "\0" in text:
        raise UnsupportedText("文件包含二进制数据，请改选文本文件")
    return text


def as_object(value) -> dict:
    return value if isinstance(value, dict) else {}


def snippet(value) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()[:240].encode("utf-8", errors="replace").decode("utf-8")


def resolve_component(spec: dict, value, section: str) -> dict:
    item = as_object(value)
    reference = item.get("$ref")
    prefix = f"#/components/{section}/"
    if "$ref" not in item:
        return item
    if isinstance(reference, str) and reference.startswith(prefix):
        name = reference[len(prefix) :]
        if name and "/" not in name:
            components = as_object(as_object(spec.get("components")).get(section))
            return as_object(components.get(name.replace("~1", "/").replace("~0", "~")))
    return {}


def parameter_notes(spec: dict, path_item: dict, operation: dict) -> list[dict]:
    parameters = {}
    for item in (path_item, operation):
        raw = item.get("parameters")
        if not isinstance(raw, list):
            continue
        for entry in raw[:32]:
            parameter = resolve_component(spec, entry, "parameters")
            name, location = snippet(parameter.get("name")), parameter.get("in")
            if name and location in ("query", "header", "path", "cookie"):
                parameters[(location, name)] = {
                    "name": name,
                    "in": location,
                    "required": location == "path" or parameter.get("required") is True,
                    "type": snippet(as_object(parameter.get("schema")).get("type")),
                    "description": snippet(parameter.get("description")),
                }
    return list(parameters.values())[:32]


def request_fields(spec: dict, operation: dict) -> list[dict]:
    """List only JSON property names and types. Keep examples and defaults private."""
    body = resolve_component(spec, operation.get("requestBody"), "requestBodies")
    media = as_object(as_object(body.get("content")).get("application/json"))
    schema = resolve_component(spec, media.get("schema"), "schemas")
    required = schema.get("required")
    fields = []
    for name, definition in as_object(schema.get("properties")).items():
        definition = resolve_component(spec, definition, "schemas")
        fields.append({
            "name": snippet(name), "type": snippet(definition.get("type")),
            "required": isinstance(required, list) and name in required,
        })
        if len(fields) == 32:
            break
    return fields


def response_notes(spec: dict, operation: dict) -> list[dict]:
    return [
        {
            "status": code,
            "description": snippet(resolve_component(spec, item, "responses").get("description")),
        }
        for code, item in as_object(operation.get("responses")).items()
        if re.fullmatch(r"[1-5](?:\d\d|XX)|default", code, flags=re.ASCII)
    ][:32]


def extract_candidates(spec: dict, source: str, candidates: list[dict]) -> bool:
    incomplete = False
    for path, value in as_object(spec.get("paths")).items():
        item = as_object(value)
        if not item or "$ref" in item or "trace" in item:
            incomplete = True
        for method in METHODS:
            operation = item.get(method)
            if not isinstance(operation, dict):
                continue
            try:
                validated = EndpointInput(method=method, path=path)
                validated.path.encode("utf-8")
            except (ValidationError, ValueError):
                incomplete = True
                continue
            if len(candidates) >= MAX_CANDIDATES:
                raise HTTPException(413, f"最多预览 {MAX_CANDIDATES} 个接口，请拆分项目资料包")
            # Registered paths are executed literally. Show templates to the user but
            # require a concrete relative path in the existing manual registration form.
            manual = any(char in path for char in "{}?")
            incomplete |= manual
            candidates.append(
                {
                    "candidate_id": str(len(candidates) + 1),
                    "source_path": source,
                    "method": validated.method,
                    "path": validated.path,
                    "requires_manual_registration": manual,
                    "summary": snippet(operation.get("summary"))
                    or snippet(operation.get("description")),
                    "parameters": parameter_notes(spec, item, operation),
                    "request_fields": request_fields(spec, operation),
                    "responses": response_notes(spec, operation),
                }
            )
    return incomplete


def inspect_archive(data: bytes) -> dict:
    documents, candidates, warnings = [], [], []
    remaining = [MAX_EXPANDED]
    openapi_found = json_skipped = incomplete = False
    with open_zip(data) as archive:
        for info in entries(archive):
            suffix = PurePosixPath(info.filename).suffix.lower()
            if suffix in TEXT_SUFFIXES and info.file_size <= MAX_TEXT:
                documents.append({"path": info.filename, "size": info.file_size})
            elif suffix in TEXT_SUFFIXES:
                warnings.append(f"文档超过 1 MiB，无法预览：{info.filename}")
            elif suffix == ".json":
                if info.file_size > MAX_TEXT:
                    json_skipped = True
                    continue
                try:
                    text = read_text(archive, info, remaining)
                    spec = as_object(json.loads(text))
                except (UnsupportedText, ValueError, RecursionError):
                    json_skipped = True
                    continue
                version = spec.get("openapi")
                if isinstance(version, str) and re.fullmatch(r"3\.\d+\.\d+(?:[-+].+)?", version):
                    openapi_found = True
                    if extract_candidates(spec, info.filename, candidates):
                        incomplete = True
    if not documents:
        warnings.append("没有可选的 MD/TXT 文档，可以单独导入文本或手工填写需求")
    if json_skipped:
        warnings.append("部分 JSON 超限、编码不支持或格式无效，已跳过")
    if not openapi_found:
        warnings.append("未找到可读取的 OpenAPI 3 JSON，请手工登记接口")
    elif not candidates or incomplete:
        warnings.append("部分接口无法直接登记，例如模板路径或未展开的引用，请手工补录")
    return {
        "documents": documents,
        "endpoint_candidates": candidates,
        "needs_manual_endpoints": not candidates or incomplete or json_skipped,
        "warnings": warnings,
    }


def preview_text(data: bytes, path: str, start: int, end: int | None) -> dict:
    with open_zip(data) as archive:
        text = read_text(archive, archive.getinfo(path), [MAX_TEXT])
    length = len(text)
    if end is None:
        end = min(start + MAX_PREVIEW, length)
    if not 0 <= start <= end <= length or end - start > MAX_PREVIEW or (start == end and length):
        raise HTTPException(422, "片段范围无效，每次最多选取 16000 个字符")
    return {
        "path": path,
        "start": start,
        "end": end,
        "total_chars": length,
        "text": text[start:end],
    }
