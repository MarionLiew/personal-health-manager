from __future__ import annotations

import hmac
import html
import mimetypes
import os
import secrets
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)
from sqlalchemy import select

from health_agent.database.models import Lesion, LesionSourceLink, SourceDocument
from health_agent.database.session import session_scope

MAX_DOWNLOAD_BYTES = 1_073_741_824

_PAGE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>个人医疗证据管理</title>
<style>
  :root { --ink:#1a1a1a; --muted:#6b7280; --line:#e5e7eb; --accent:#0f6b5c; --warn:#b45309; }
  * { box-sizing:border-box; margin:0; }
  body { font-family:-apple-system,"PingFang SC","Microsoft YaHei",sans-serif; color:var(--ink);
         font-size:17px; line-height:1.55; padding:16px; max-width:980px; margin:0 auto; }
  h1 { font-size:22px; margin-bottom:2px; }
  .sub { color:var(--muted); font-size:14px; margin-bottom:18px; }
  .filters { display:flex; gap:8px; flex-wrap:wrap; margin-bottom:14px; }
  .filters a { text-decoration:none; color:var(--accent); border:1px solid var(--line);
               padding:6px 14px; border-radius:18px; font-size:15px; }
  .event { border:1px solid var(--line); border-radius:10px; padding:12px 14px;
          margin-bottom:10px; }
  .event h3 { font-size:17px; margin-bottom:4px; }
  .date { color:var(--accent); font-weight:600; font-size:15px; }
  .meta { color:var(--muted); font-size:14px; }
  .quote { background:#f8f7f4; border-left:3px solid var(--accent); padding:8px 10px;
           margin:8px 0; font-size:15px; white-space:pre-wrap; }
  .btn { display:inline-block; margin-top:6px; background:var(--accent); color:#fff;
         text-decoration:none; padding:7px 16px; border-radius:8px; font-size:15px; }
  .tag { display:inline-block; font-size:12px; border:1px solid var(--line); color:var(--muted);
         border-radius:4px; padding:1px 6px; margin-left:6px; vertical-align:2px; }
  .warn { color:var(--warn); }
  footer { color:var(--muted); font-size:13px; margin-top:20px;
          border-top:1px solid var(--line); padding-top:10px; }
</style>
</head>
<body>
<h1>个人医疗证据管理</h1>
<div class="sub">检查记录时间线 —— 点「查看原件」核对报告原文；本页只读，不改变任何记录。</div>
<div class="filters">
  <a href="/">全部</a>
  {filters}
</div>
{events}
<footer>数据来自本地健康档案库；报告原文以原件为准。本页不作诊断。</footer>
</body></html>"""

_EVENT = """<div class="event">
  <div class="date">{date}</div>
  <h3>{title}<span class="tag">{kind}</span></h3>
  <div class="meta">{institution}</div>
  {quote}
  {download}
</div>"""


def _events(lesion: str | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with session_scope() as session:
        sources = {s.id: s for s in session.scalars(select(SourceDocument)).all()}
        if lesion:
            links = session.scalars(
                select(LesionSourceLink).where(
                    LesionSourceLink.lesion_id == lesion,
                    LesionSourceLink.unlinked_at.is_(None),
                )
            ).all()
            keep = {link.source_document_id for link in links}
        else:
            keep = set(sources)
        for source in sources.values():
            if source.id not in keep or source.revoked:
                continue
            rows.append(
                {
                    "date": (source.generated_at or source.imported_at).date().isoformat(),
                    "title": source.original_filename,
                    "kind": "报告原件",
                    "institution": source.institution or "机构未标注",
                    "quote": "",
                    "source_id": source.id,
                    "mime_type": source.mime_type,
                }
            )
    rows.sort(key=lambda row: row["date"], reverse=True)
    return rows


def _render_html(lesion: str | None = None) -> str:
    with session_scope() as session:
        lesions = session.scalars(select(Lesion).where(Lesion.verified.is_(True))).all()
    filters = "".join(
        f'<a href="/?lesion={quote(str(item.details.get("display_code", item.id)))}">'
        f'{html.escape(str(item.details.get("display_code", item.id)))}</a>'
        for item in lesions
    )
    lesion_id = None
    if lesion:
        with session_scope() as session:
            found = session.scalars(
                select(Lesion).where(Lesion.verified.is_(True))
            ).all()
        for item in found:
            if item.details.get("display_code") == lesion or item.id == lesion:
                lesion_id = item.id
    events_html = ""
    for row in _events(lesion_id):
        download = (
            f'<a class="btn" href="/api/sources/{row["source_id"]}/download">查看原件</a>'
            if row["mime_type"]
            else ""
        )
        events_html += _EVENT.format(
            date=html.escape(str(row["date"])),
            title=html.escape(str(row["title"])),
            kind=html.escape(str(row["kind"])),
            institution=html.escape(str(row["institution"])),
            quote=f'<div class="quote">{row["quote"]}</div>' if row["quote"] else "",
            download=download,
        )
    return _PAGE.replace("{filters}", filters).replace("{events}", events_html or "<p>暂无记录</p>")


_LOGIN = """<!doctype html>
<html lang="zh-CN"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta charset="utf-8"><title>病历查看登录</title>
<style>body{font:18px -apple-system,sans-serif;max-width:420px;margin:12vh auto;padding:20px}
input,button{font:inherit;padding:12px;width:100%;box-sizing:border-box;margin:8px 0}
button{background:#0f6b5c;color:white;border:0;border-radius:8px}</style>
<h1>个人医疗证据管理</h1><p>请输入访问密码</p>
<form method="post" action="/login"><input name="password" type="password"
autocomplete="current-password" required><button>进入病历</button></form></html>"""


def create_app(password: str | None = None) -> FastAPI:
    password = password if password is not None else os.getenv("HEALTH_WEB_PASSWORD")
    if not password:
        raise RuntimeError("HEALTH_WEB_PASSWORD is required")
    token = secrets.token_urlsafe(48)
    failures: dict[str, list[float]] = {}
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.middleware("http")
    async def require_login(request: Request, call_next):
        if request.url.path in {"/health", "/login"}:
            return await call_next(request)
        if not hmac.compare_digest(request.cookies.get("health_session", ""), token):
            if request.url.path.startswith("/api/"):
                return JSONResponse({"error": "unauthorized"}, status_code=401)
            return RedirectResponse("/login", status_code=303)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    @app.get("/login", response_class=HTMLResponse)
    def login_page() -> str:
        return _LOGIN

    @app.post("/login")
    def login(request: Request, password: str = Form(...)) -> RedirectResponse:
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        recent = [t for t in failures.get(client, []) if now - t < 900]
        failures[client] = recent
        if len(recent) >= 5:
            raise HTTPException(429, "Too many attempts")
        if not hmac.compare_digest(password, app.state.password):
            recent.append(now)
            raise HTTPException(401, "Invalid password")
        failures.pop(client, None)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            "health_session", token, httponly=True, secure=True,
            samesite="strict", max_age=8 * 3600,
        )
        return response

    app.state.password = password

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    def index(lesion: str | None = None) -> str:
        return _render_html(lesion)

    @app.get("/api/timeline")
    def timeline(lesion: str | None = None) -> JSONResponse:
        return JSONResponse({"status": "success", "data": {"events": _events(lesion)}})

    @app.get("/api/sources/{source_id}/download")
    def download(source_id: str) -> FileResponse:
        with session_scope() as session:
            source = session.get(SourceDocument, source_id)
            if source is None or source.revoked:
                raise HTTPException(404, "Source not found")
            path = Path(source.local_path)
            mime = (
                source.mime_type
                or mimetypes.guess_type(path.name)[0]
                or "application/octet-stream"
            )
        if not path.is_file():
            raise HTTPException(404, "Original file not available")
        if path.stat().st_size > MAX_DOWNLOAD_BYTES:
            raise HTTPException(413, "File too large")
        return FileResponse(path, media_type=mime, filename=source.original_filename)

    @app.get("/api/case-bundle.zip")
    def case_bundle() -> StreamingResponse:
        import io
        import zipfile

        buffer = io.BytesIO()
        with session_scope() as session:
            sources = session.scalars(select(SourceDocument)).all()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as bundle:
                for source in sources:
                    if source.revoked:
                        continue
                    path = Path(source.local_path)
                    if path.is_file() and path.stat().st_size <= MAX_DOWNLOAD_BYTES:
                        bundle.write(path, f"originals/{source.id}{path.suffix}")
        buffer.seek(0)
        return StreamingResponse(
            buffer,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=case-bundle.zip"},
        )

    return app
