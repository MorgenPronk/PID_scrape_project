import time
from typing import List, Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pid_extractor import PIDExtractor
from config_store import load_settings, save_settings, get_config_path


app = FastAPI(title="PID Equipment Tag Extractor", version="0.1.0")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

extractor_instance: Optional[PIDExtractor] = None


def get_extractor() -> PIDExtractor:
    global extractor_instance
    if extractor_instance is None:
        extractor_instance = PIDExtractor()
    return extractor_instance


def _precheck_ascii(settings: dict) -> dict:
    offenders = {}
    for key in ["endpoint_url", "deployment", "api_version", "api_key", "model"]:
        val = settings.get(key, "") or ""
        bad = []
        for idx, ch in enumerate(val):
            if ord(ch) > 127:
                bad.append((idx, ch, ord(ch)))
        if bad:
            offenders[key] = bad
    return offenders


def run_connectivity_tests(settings: dict) -> dict:
    result = {
        "ok": False,
        "error": None,
        "precheck": _precheck_ascii(settings),
        "chat": {"ok": False, "latency_ms": None, "preview": None, "error": None},
        "parse": {"ok": True, "latency_ms": 0, "parsed": {"note": "Structured parse test not implemented"}, "error": None},
        "embeddings": {"ok": True, "latency_ms": 0, "dimensions": 0, "error": "Not run"},
    }

    try:
        extractor = PIDExtractor(
            provider=settings.get("provider"),
            api_key=settings.get("api_key"),
            endpoint_url=settings.get("endpoint_url"),
            deployment=settings.get("deployment"),
            api_version=settings.get("api_version"),
            model=settings.get("model"),
        )
        client = extractor.client

        # Chat test
        try:
            start = time.time()
            resp = client.chat.completions.create(
                model=extractor.deployment if extractor.provider == "azure" else extractor.model,
                messages=[
                    {"role": "system", "content": "You are a ping service."},
                    {"role": "user", "content": "Reply with the word PONG."},
                ],
                temperature=0,
            )
            latency_ms = int((time.time() - start) * 1000)
            content = resp.choices[0].message.content if resp.choices else ""
            result["chat"] = {"ok": True, "latency_ms": latency_ms, "preview": content, "error": None}
        except Exception as exc:
            result["chat"] = {"ok": False, "latency_ms": None, "preview": None, "error": str(exc)}

        # Overall status: only chat is required for now
        result["ok"] = bool(result["chat"].get("ok"))

    except Exception as exc:
        result["error"] = str(exc)

    return result


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    settings = load_settings()
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "results": [],
            "error_message": None,
            "submitted": False,
            "settings": settings,
            "config_path": get_config_path(),
        },
    )


@app.post("/extract", response_class=HTMLResponse)
async def extract_tags(request: Request, files: List[UploadFile] = File(...)) -> HTMLResponse:
    results = []
    error_message = None
    settings = load_settings()

    try:
        extractor = get_extractor()
    except Exception as exc:  # surface Azure/OpenAI misconfiguration in UI
        error_message = f"Could not initialize model client: {exc}"
        return templates.TemplateResponse(
            "index.html",
            {
                "request": request,
                "results": results,
                "error_message": error_message,
                "submitted": True,
                "settings": settings,
            },
            status_code=500,
        )

    for upload in files:
        file_bytes = await upload.read()
        tags = extractor.extract_from_pdf_bytes(file_bytes, upload.filename)
        results.append(
            {
                "filename": upload.filename,
                "tags": tags or [],
                "error": None if tags is not None else "No tags returned",
            }
        )

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "results": results,
            "error_message": error_message,
            "submitted": True,
            "settings": settings,
            "config_path": get_config_path(),
        },
    )


@app.get("/azure-test", response_class=HTMLResponse)
async def azure_test_page(request: Request) -> HTMLResponse:
    settings = load_settings()
    return templates.TemplateResponse(
        "azure_test.html",
        {"request": request, "settings": settings, "config_path": get_config_path()},
    )


@app.post("/azure-test/run", response_class=HTMLResponse)
async def azure_test_run(request: Request) -> HTMLResponse:
    settings = load_settings()
    result = run_connectivity_tests(settings)
    return templates.TemplateResponse(
        "azure_test_result.html",
        {"request": request, "result": result},
    )


@app.get("/config", response_class=HTMLResponse)
async def get_config(request: Request) -> HTMLResponse:
    settings = load_settings()
    return templates.TemplateResponse(
        "config.html",
        {"request": request, "settings": settings, "saved": False, "config_path": get_config_path()},
    )


@app.post("/config", response_class=HTMLResponse)
async def post_config(
    request: Request,
    provider: str = Form(...),
    api_key: str = Form(...),
    endpoint_url: str = Form(""),
    deployment: str = Form(""),
    api_version: str = Form(""),
    model: str = Form("gpt-4.1"),
) -> HTMLResponse:
    settings = {
        "provider": provider.lower(),
        "api_key": api_key,
        "endpoint_url": endpoint_url,
        "deployment": deployment,
        "api_version": api_version,
        "model": model,
    }
    save_settings(settings)

    # Reset cached extractor so new settings take effect on next request
    global extractor_instance
    extractor_instance = None

    return templates.TemplateResponse(
        "config.html",
        {"request": request, "settings": settings, "saved": True, "config_path": get_config_path()},
    )


@app.get("/health")
async def healthcheck() -> dict:
    return {"status": "ok"}
