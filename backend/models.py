"""
SQLAlchemy Database Models
Defines all database tables and relationships
"""

from sqlalchemy import Column, Integer, String, DateTime, Float, ForeignKey, Enum
from sqlalchemy.orm import relationship
from datetime import datetime
import enum
from database import Base


# Enum for Priority
class PriorityLevel(str, enum.Enum):
    LOW = "low"
    MID = "mid"
    HIGH = "high"


# Enum for Alert Types
class AlertType(str, enum.Enum):
    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


class Patient(Base):
    """
    Patient Model
    Stores patient demographic information
    """
    __tablename__ = "patients"

    patient_id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(255), nullable=False)
    age = Column(Integer, nullable=False)
    contact = Column(String(20), nullable=False)
    blood_group = Column(String(10), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    admissions = relationship("Admission", back_populates="patient", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Patient {self.patient_id}: {self.full_name}>"


class Hospital(Base):
    """
    Hospital Model
    Stores hospital information and capacity
    """
    __tablename__ = "hospitals"

    hospital_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, unique=True)
    location = Column(String(255), nullable=False)
    total_beds = Column(Integer, nullable=False)
    total_icu_beds = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    admissions = relationship("Admission", back_populates="hospital", cascade="all, delete-orphan")
    resources = relationship("Resource", back_populates="hospital", cascade="all, delete-orphan", uselist=False)
    predictions = relationship("Prediction", back_populates="hospital", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="hospital", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Hospital {self.hospital_id}: {self.name}>"


class Admission(Base):
    """
    Admission Model
    Records patient admissions to hospitals
    """
    __tablename__ = "admissions"

    admission_id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("patients.patient_id"), nullable=False)
    hospital_id = Column(Integer, ForeignKey("hospitals.hospital_id"), nullable=False)
    admission_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    discharge_time = Column(DateTime, nullable=True)
    priority = Column(Enum(PriorityLevel), default=PriorityLevel.MID, nullable=False)
    patient_condition = Column(String(255), nullable=False)
    department = Column(String(100), nullable=False)

    # Relationships
    patient = relationship("Patient", back_populates="admissions")
    hospital = relationship("Hospital", back_populates="admissions")

    def __repr__(self):
        return f"<Admission {self.admission_id}: Patient {self.patient_id} at Hospital {self.hospital_id}>"


class Resource(Base):
    """
    Resource Model
    Tracks available hospital resources (beds, ICU, ventilators, oxygen)
    """
    __tablename__ = "resources"

    resource_id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.hospital_id"), nullable=False, unique=True)
    available_beds = Column(Integer, nullable=False)
    available_icu_beds = Column(Integer, nullable=False)
    ventilators = Column(Integer, nullable=False)
    oxygen_units = Column(Integer, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    hospital = relationship("Hospital", back_populates="resources")

    def __repr__(self):
        return f"<Resource Hospital {self.hospital_id}>"


class Prediction(Base):
    """
    Prediction Model
    Stores ML predictions for hospital load forecasting
    """
    __tablename__ = "predictions"

    prediction_id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.hospital_id"), nullable=False)
    prediction_time = Column(DateTime, default=datetime.utcnow, nullable=False)
    predicted_patients = Column(Float, nullable=False)
    predicted_bed_usage = Column(Float, nullable=False)
    predicted_icu_usage = Column(Float, nullable=False)

    # Relationships
    hospital = relationship("Hospital", back_populates="predictions")

    def __repr__(self):
        return f"<Prediction {self.prediction_id} for Hospital {self.hospital_id}>"


class Alert(Base):
    """
    Alert Model
    Stores alerts for critical hospital conditions
    """
    __tablename__ = "alerts"

    alert_id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.hospital_id"), nullable=False)
    alert_type = Column(Enum(AlertType), nullable=False)
    message = Column(String(500), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_resolved = Column(Integer, default=0)  # 0 = unresolved, 1 = resolved

    # Relationships
    hospital = relationship("Hospital", back_populates="alerts")

    def __repr__(self):
        return f"<Alert {self.alert_id}: {self.alert_type}>"
