import datetime
import uuid

from sqlalchemy import Column, Integer, String, Date, JSON, DateTime
from database import Base

class PatientReport(Base):
    __tablename__ = "patient_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(String(36), default=lambda: str(uuid.uuid4()), nullable=False)
    patient_name = Column(String(150), nullable=False)
    patient_age = Column(Integer, nullable=False)
    report_date = Column(Date, nullable=False)
    questionnaire = Column(JSON, nullable=False)
    pain_regions = Column(JSON, nullable=False)
    ai_report = Column(JSON, nullable=False)
    ai_model = Column(String(100), nullable=False)
    ai_generated_at = Column(DateTime, nullable=False)
    analysis = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
