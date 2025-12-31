"""
FastAPI server for local experimentation and testing.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from ..core import BankStatementPipeline, PipelineConfig, DocumentAIConfig
from ..validators import ValidationConfig

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
OUTPUT_DIR = Path(os.getenv("BSC_OUTPUT_DIR", "output")).resolve()

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Bank Statement Converter", version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

DOC_AI_PROJECT_ID = ""
DOC_AI_PROCESSOR_ID = ""
DOC_AI_LOCATION = "us"
DOC_AI_CREDENTIALS_PATH = ""


def _load_docai_config() -> Optional[DocumentAIConfig]:
    project_id = DOC_AI_PROJECT_ID or os.getenv("DOC_AI_PROJECT_ID")
    location = DOC_AI_LOCATION or os.getenv("DOC_AI_LOCATION", "us")
    processor_id = DOC_AI_PROCESSOR_ID or os.getenv("DOC_AI_PROCESSOR_ID")
    credentials_path = DOC_AI_CREDENTIALS_PATH or os.getenv("DOC_AI_CREDENTIALS_PATH")

    if not project_id or not processor_id:
        return None

    return DocumentAIConfig(
        project_id=project_id,
        location=location,
        processor_id=processor_id,
        credentials_path=credentials_path or None
    )


def _sanitize_outputs(output_files: Optional[Dict[str, str]]) -> Dict[str, str]:
    if not output_files:
        return {}

    cleaned: Dict[str, str] = {}
    for key, path_str in output_files.items():
        if not path_str:
            continue
        try:
            resolved = Path(path_str).resolve()
            cleaned[key] = str(resolved.relative_to(OUTPUT_DIR))
        except Exception:
            cleaned[key] = Path(path_str).name

    return cleaned


@app.get("/", response_class=HTMLResponse)
async def index() -> str:
    return (STATIC_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/api/process")
async def process_document(
    file: UploadFile = File(...),
    confidence_threshold: float = Form(0.85),
    emit_summary: bool = Form(False),
) -> Dict[str, object]:
    if confidence_threshold < 0 or confidence_threshold > 1:
        raise HTTPException(status_code=400, detail="confidence_threshold must be between 0 and 1")

    docai_config = _load_docai_config()
    if not docai_config:
        raise HTTPException(
            status_code=400,
            detail="Missing Document AI config. Update DOC_AI_PROJECT_ID and DOC_AI_PROCESSOR_ID in web/app.py."
        )

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    suffix = Path(file.filename).suffix or ".pdf"
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name

        config = PipelineConfig()
        config.docai_config = docai_config
        config.output_dir = str(OUTPUT_DIR)
        config.emit_summary = emit_summary

        validation_config = ValidationConfig()
        validation_config.confidence_threshold = confidence_threshold
        config.validation_config = validation_config

        pipeline = BankStatementPipeline(config)
        result, report = await pipeline.process(temp_path)

        output_files = _sanitize_outputs(report.output_files)
        report.output_files = output_files

        return {
            "document": {
                "document_id": result.document_id,
                "engine": result.engine,
                "page_count": result.page_count,
                "total_rows": result.total_rows,
                "overall_confidence": result.overall_confidence,
            },
            "report": report.to_dict(),
            "output_files": output_files,
        }
    finally:
        if temp_path:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass


@app.get("/api/outputs/{filename:path}")
async def get_output(filename: str) -> FileResponse:
    candidate = (OUTPUT_DIR / filename).resolve()
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="Output file not found")

    if OUTPUT_DIR not in candidate.parents and candidate != OUTPUT_DIR:
        raise HTTPException(status_code=404, detail="Invalid output path")

    return FileResponse(candidate)
