from typing import Any
import datetime

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from pydantic import BaseModel

import models
from database import Base, engine, get_db
from ai_report_service import generate_ai_report, GROQ_REPORT_MODEL, MissingReportApiKey
from gemini_service import revise_transcript


app = FastAPI(
    title="ANATOME API",
    version="1.0.0",
)


Base.metadata.create_all(bind=engine)


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
    }


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


class ReportRequest(BaseModel):
    patient_name: str
    patient_age: int
    report_date: datetime.date
    questionnaire: dict[str, Any]
    pain_regions: dict[str, Any]


@app.post("/api/reports")
@app.post("/reports", include_in_schema=False)
def create_report(request: ReportRequest, db: Session = Depends(get_db)):
    try:
        ai_report = generate_ai_report(
            patient_age=request.patient_age,
            report_date=request.report_date.isoformat(),
            questionnaire=request.questionnaire,
            pain_regions=request.pain_regions,
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
    )

    db.add(db_report)
    db.commit()
    db.refresh(db_report)

    return {
        "message": "Report generated successfully",
        "patient_id": db_report.patient_id,
        "ai_report": ai_report,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
