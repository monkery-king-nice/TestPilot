from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

from ..runs.repository import RunNotFound
from .service import ReportService

router = APIRouter(prefix="/api/projects/{project_id}/runs", tags=["测试报告"])


@router.get("/{run_id}/report", response_class=HTMLResponse)
def download_report(project_id: str, run_id: str, request: Request):
    try:
        content = ReportService(request.app.state.run_service).render(project_id, run_id)
    except RunNotFound as exc:
        raise HTTPException(404, "项目下没有这个运行批次") from exc
    # run_id comes from a successful stored-run lookup, not directly from the URL.
    return HTMLResponse(content, headers={
        "Content-Disposition": f'attachment; filename="testpilot-{run_id}.html"',
        "Cache-Control": "no-store",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'",
    })
