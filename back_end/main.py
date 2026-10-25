from typing import Any
import datetime
import os

from fastapi import FastAPI, Depends, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

import models
from database import Base, engine, get_db
from ai_report_service import generate_ai_report, GROQ_REPORT_MODEL, MissingReportApiKey
from gemini_service import revise_transcript
from care_guide import generate_care_guide
from ml import inference


app = FastAPI(
    title="ANATOME API",
    version="2.0.0",
)


Base.metadata.create_all(bind=engine)


def add_missing_columns():
    # create_all() never alters existing tables; add columns introduced
    # after a database was first created.
    with engine.begin() as conn:
        columns = {c["name"] for c in inspect(conn).get_columns("patient_reports")}
        if "analysis" not in columns:
            conn.execute(text("ALTER TABLE patient_reports ADD COLUMN analysis JSON"))


add_missing_columns()


origins = [
    "http://localhost:5173",
    "http://localhost",
]


app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": "ANATOME API is running",
    }


@app.get("/api/health")
def health_check():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        row = result.fetchone()

    return {
        "status": "healthy",
        "database_connected": row[0] == 1,
        "models": {
            "triage": inference.triage() is not None,
            "painbert": inference.painbert() is not None,
        },
    }


# --------------------------------------------------------------------------
# Decision-support models
# --------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    age: int | None = Field(default=None, ge=0, le=120)
    sex: str | None = None
    questionnaire: dict[str, Any] = {}
    pain_regions: dict[str, Any] = {}
    global_note: str | None = Field(default=None, max_length=4000)


class TagRequest(BaseModel):
    text: str = Field(max_length=4000)


@app.post("/api/analyze")
def analyze(request: AnalyzeRequest):
    return inference.analyze_intake(request.model_dump())


class CareGuideRequest(BaseModel):
    age: int | None = Field(default=None, ge=0, le=120)
    questionnaire: dict[str, Any] = {}
    pain_regions: dict[str, Any] = {}


@app.post("/api/care-guide")
def care_guide(request: CareGuideRequest):
    """Patient-facing tips for while they wait to be seen, plus the analysis
    the tips were selected from."""
    payload = request.model_dump()
    if not payload["pain_regions"]:
        raise HTTPException(status_code=400, detail="Mark and save at least one pain spot first.")
    analysis = inference.analyze_intake(payload)
    return {"guide": generate_care_guide(analysis, payload), "analysis": analysis}


@app.post("/api/nlp/tag")
def tag_note(request: TagRequest):
    result = inference.tag_text(request.text)
    if result is None:
        raise HTTPException(status_code=503, detail="PainBERT model artifact is not installed.")
    return result


@app.get("/api/models")
def model_cards():
    return inference.model_cards()


@app.post("/api/transcribe")
async def transcribe(audio: UploadFile = File(...), translate: bool = Form(False)):
    """Speech to text with Whisper on Groq. ``translate`` turns any spoken
    language into English text so PainBERT can read it."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="GROQ_API_KEY is not configured on the server.")
    data = await audio.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Recording is too long.")

    from openai import OpenAI

    client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key, timeout=60.0)
    upload = (audio.filename or "speech.webm", data, audio.content_type or "audio/webm")
    try:
        if translate:
            result = client.audio.translations.create(model="whisper-large-v3", file=upload)
        else:
            result = client.audio.transcriptions.create(model="whisper-large-v3-turbo", file=upload)
    except Exception as exc:
        raise HTTPException(status_code=502, detail="The transcription service is unavailable.") from exc
    return {"text": result.text.strip(), "translated": translate}


class ReviseRequest(BaseModel):
    text: str


@app.post("/api/revise-transcript")
def revise_patient_transcript(request: ReviseRequest):
    text = request.text.strip()

    if not text:
        raise HTTPException(status_code=400, detail="There is no text to revise.")

    if len(text) > 10000:
        raise HTTPException(status_code=400, detail="The description is too long to revise.")

    try:
        revised = revise_transcript(text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"revised": revised}


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------

class ReportRequest(BaseModel):
    patient_name: str
    patient_age: int
    report_date: datetime.date
    questionnaire: dict[str, Any]
    pain_regions: dict[str, Any]
    sex: str | None = None
    global_note: str | None = None


def report_regions(pain_regions: dict, analysis: dict) -> dict:
    """Spots as the report writer sees them: plain fields, no 3D coordinates,
    and for body-area spots the structures the localizer found under the spot."""
    out = {}
    for spot_id, spot in pain_regions.items():
        loc = (analysis.get("localization") or {}).get(spot_id)
        entry = {
            "region_name": spot.get("areaLabel") or spot.get("regionName"),
            "severity": spot.get("severity"),
            "pain_type": spot.get("painType") or "Not reported",
            "frequency": spot.get("frequency") or "Not reported",
            "onset": spot.get("onset") or spot.get("startDate") or "Not reported",
            "patient_note": spot.get("notes") or "",
        }
        if loc:
            entry["location_within_area"] = loc.get("where") or "Not recorded"
            entry["screening_structures_under_spot"] = [c["display"] for c in loc["candidates"][:3]]
        out[spot_id] = entry
    return out


def decision_support_summary(analysis: dict) -> dict:
    """The subset of model output the report writer may reference."""
    triage = analysis.get("triage") or {}
    return {
        "care_level": (analysis.get("care_level") or {}).get("title"),
        "red_flags": [flag["title"] for flag in analysis.get("red_flags", [])],
        "estimated_emergent_probability": triage.get("p_emergent"),
        "neuropathic_descriptor_count": analysis["language"]["dn4"]["score"],
        "pain_descriptors_detected": analysis["language"]["descriptors"],
        "widespread_pain_index": analysis["anatomy"]["wpi"]["score"],
        "segmental_pattern": (analysis["anatomy"].get("segment_pattern") or {}).get("note"),
        "peripheral_nerve_pattern": (analysis["anatomy"].get("peripheral_nerve_pattern") or {}).get("note"),
    }


@app.post("/api/reports")
@app.post("/reports", include_in_schema=False)
def create_report(request: ReportRequest, db: Session = Depends(get_db)):
    analysis = inference.analyze_intake({
        "age": request.patient_age,
        "sex": request.sex,
        "questionnaire": request.questionnaire,
        "pain_regions": request.pain_regions,
        "global_note": request.global_note,
    })
    try:
        ai_report = generate_ai_report(
            patient_age=request.patient_age,
            report_date=request.report_date.isoformat(),
            questionnaire=request.questionnaire,
            pain_regions=report_regions(request.pain_regions, analysis),
            decision_support=decision_support_summary(analysis),
        )
    except MissingReportApiKey as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        # Provider errors can contain request details. Never return them to
        # the browser, which may be shared during a patient intake session.
        raise HTTPException(
            status_code=502,
            detail="The AI report service is unavailable. Please try again later.",
        ) from exc

    db_report = models.PatientReport(
        patient_name=request.patient_name,
        patient_age=request.patient_age,
        report_date=request.report_date,
        questionnaire=request.questionnaire,
        pain_regions=request.pain_regions,
        ai_report=ai_report,
        ai_model=GROQ_REPORT_MODEL,
        ai_generated_at=datetime.datetime.utcnow(),
        analysis=analysis,
    )

    db.add(db_report)
    db.commit()
    db.refresh(db_report)

    return {
        "message": "Report generated successfully",
        "patient_id": db_report.patient_id,
        "ai_report": ai_report,
        "analysis": analysis,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
