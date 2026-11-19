"""Build model context from the current requirement and its selected import."""

import re


SECRET_LINE = re.compile(
    r"""(?im)^(\s*(?:[-*]\s+)?["']?(?:authorization|password|passwd|"""
    r"""(?:[\w-]*[_-])?(?:api[_-]?key|access[_-]?token|client[_-]?secret))["']?\s*[:=]\s*).+$"""
)


def model_text(value: str) -> str:
    return SECRET_LINE.sub(r"\1[已隐藏]", value)


def project_context(repository, project_id, requirement, endpoints):
    """Only include the selected text and metadata for confirmed endpoints."""
    context = {
        "requirement": {**requirement, "text": model_text(requirement["text"])},
        "endpoints": endpoints,
    }
    source = repository.get_requirement_source(project_id, requirement["id"])
    if source is None:
        return context

    preview = repository.preview_import_document(
        project_id, source["import_id"], source["path"], source["start"],
        min(source["end"], source["start"] + 4000),
    )
    context["source_excerpt"] = {
        "path": preview["path"], "start": preview["start"], "end": preview["end"],
        "text": model_text(preview["text"]),
    }
    manifest = repository.get_import(project_id, source["import_id"])
    registered = {(endpoint["id"], endpoint["version"]) for endpoint in endpoints}
    candidates = {item["candidate_id"]: item for item in manifest["endpoint_candidates"]}
    descriptions = []
    for confirmed in manifest["confirmed_endpoints"]:
        endpoint = confirmed["endpoint"]
        key = endpoint["id"], endpoint["version"]
        if key not in registered:
            continue
        candidate = candidates[confirmed["candidate_id"]]
        descriptions.append({
            "endpoint_id": key[0], "endpoint_version": key[1],
            "source_path": candidate["source_path"],
            "summary": model_text(candidate["summary"]),
            "parameters": [
                {**parameter, "description": model_text(parameter["description"])}
                for parameter in candidate["parameters"][:4]
            ],
            "responses": [
                {**response, "description": model_text(response["description"])}
                for response in candidate["responses"][:4]
            ],
        })
        if len(descriptions) == 12:
            break
    context["interface_descriptions"] = descriptions
    return context
