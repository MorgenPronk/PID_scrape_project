from typing import List, Optional

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pid_extractor import PIDExtractor


app = FastAPI(title="PID Equipment Tag Extractor", version="0.1.0")
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

extractor_instance: Optional[PIDExtractor] = None


def get_extractor() -> PIDExtractor:
    global extractor_instance
    if extractor_instance is None:
        extractor_instance = PIDExtractor()
    return extractor_instance


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "results": [], "error_message": None, "submitted": False},
    )


@app.post("/extract", response_class=HTMLResponse)
async def extract_tags(request: Request, files: List[UploadFile] = File(...)) -> HTMLResponse:
    results = []
    error_message = None

    try:
        extractor = get_extractor()
    except Exception as exc:  # surface Azure/OpenAI misconfiguration in UI
        error_message = f"Could not initialize model client: {exc}"
        return templates.TemplateResponse(
            "index.html",
            {"request": request, "results": results, "error_message": error_message, "submitted": True},
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
        {"request": request, "results": results, "error_message": error_message, "submitted": True},
    )


@app.get("/health")
async def healthcheck() -> dict:
    return {"status": "ok"}
