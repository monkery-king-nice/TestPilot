"""Create two handoff ZIPs and check the imported data against a running local API."""

import argparse
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

import httpx

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "project_import"


def write_samples(output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = {}
    for directory in sorted(FIXTURES.iterdir()):
        output = output_dir / f"{directory.name}.zip"
        with ZipFile(output, "w", compression=ZIP_DEFLATED) as archive:
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    archive.write(path, arcname=path.relative_to(directory).as_posix())
        samples[directory.name] = output
    return samples


def verify(samples: dict[str, Path]) -> dict:
    with httpx.Client(base_url="http://127.0.0.1:8000", trust_env=False, timeout=10) as client:

        def call(method, path, *, status=200, **kwargs):
            response = client.request(method, path, **kwargs)
            if response.status_code != status:
                raise RuntimeError(
                    f"{method} {path}: expected {status}, got {response.status_code}: {response.text[:300]}"
                )
            return response.json()

        assert call("GET", "/api/health") == {"status": "ok"}
        evidence = {}
        for name, sample in samples.items():
            project = call("POST", "/api/projects", status=201, json={"name": f"导入验收 {name}"})
            base = f"/api/projects/{project['id']}"
            upload_args = {
                "params": {"filename": sample.name},
                "headers": {"Content-Type": "application/zip"},
            }
            import_route = f"{base}/imports"
            manifest = call(
                "POST", import_route, status=201, content=sample.read_bytes(), **upload_args
            )
            archive = f"{import_route}/{manifest['id']}"
            assert call("GET", f"{base}/requirements") == []
            assert call("GET", f"{base}/endpoints") == []
            preview = call(
                "POST", f"{archive}/preview", json={"path": manifest["documents"][0]["path"]}
            )
            source = {key: preview[key] for key in ("import_id", "path", "start", "end")}
            requirement = call(
                "POST",
                f"{base}/requirements",
                status=201,
                json={"text": preview["text"], "source": source},
            )
            assert requirement["version"] == 1 and requirement["source"] == source
            candidates = manifest["endpoint_candidates"]
            if name == "book-catalog":
                assert not manifest["needs_manual_endpoints"] and candidates
                selected = {"candidate_ids": [candidates[0]["candidate_id"]]}
                confirmation = call("POST", f"{archive}/confirm-endpoints", json=selected)
                assert call("POST", f"{archive}/confirm-endpoints", json=selected) == confirmation
                assert call("GET", archive)["confirmed_endpoints"] == confirmation["endpoints"]
                registered = confirmation["endpoints"][0]["endpoint"]
            else:
                assert manifest["needs_manual_endpoints"] and not candidates
                registered = call(
                    "POST",
                    f"{base}/endpoints",
                    status=201,
                    json={"method": "GET", "path": "/rooms"},
                )
            assert call("GET", f"{base}/endpoints") == [registered]
            invalid = call("POST", import_route, status=422, content=b"not a zip", **upload_args)
            assert call("GET", f"{base}/requirements") == [requirement]
            assert call("GET", f"{base}/endpoints") == [registered]
            evidence[name] = {
                "project": project,
                "import": manifest,
                "preview": preview,
                "requirement": requirement,
                "registered_endpoint": registered,
                "bad_upload": invalid,
            }
        a, b = evidence["book-catalog"], evidence["room-schedule"]
        derive = f"/api/projects/{b['project']['id']}/imports/{a['import']['id']}"
        rejected = call(
            "POST", f"{derive}/preview", status=404, json={"path": a["preview"]["path"]}
        )
        return {
            "mode": "real local HTTP API with independent sample projects",
            "samples": evidence,
            "cross_project_preview": rejected,
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/project-import"))
    parser.add_argument(
        "--samples-only",
        action="store_true",
        help="write the two ZIP files without calling the API",
    )
    args = parser.parse_args()
    samples = write_samples(args.output_dir)
    if not args.samples_only:
        result = verify(samples)
        (args.output_dir / "http-evidence.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(
            "PASS: both sample ZIPs, requirement v1, repeat confirmation, manual registration, corrupt ZIP, project isolation"
        )
    else:
        print("Created book-catalog.zip and room-schedule.zip")


if __name__ == "__main__":
    main()
