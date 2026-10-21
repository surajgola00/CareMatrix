"""
Pydantic Schemas for Request/Response Validation
Defines data validation schemas for all API endpoints
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List
from models import PriorityLevel, AlertType


# ===================== PATIENT SCHEMAS =====================

class PatientBase(BaseModel):
    """Base patient schema with common fields"""
    full_name: str = Field(..., min_length=1, max_length=255)
    age: int = Field(..., ge=0, le=150)
    contact: str = Field(..., min_length=10, max_length=20)
    blood_group: str = Field(..., min_length=2, max_length=10)


class PatientCreate(PatientBase):
    """Schema for creating a new patient"""
    pass


class PatientResponse(PatientBase):
    """Schema for patient response"""
    patient_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ===================== HOSPITAL SCHEMAS =====================

class HospitalBase(BaseModel):
    """Base hospital schema with common fields"""
    name: str = Field(..., min_length=1, max_length=255)
    location: str = Field(..., min_length=1, max_length=255)
    total_beds: int = Field(..., ge=1)
    total_icu_beds: int = Field(..., ge=0)


class HospitalCreate(HospitalBase):
    """Schema for creating a new hospital"""
    pass


class HospitalResponse(HospitalBase):
    """Schema for hospital response"""
    hospital_id: int
    created_at: datetime

    class Config:
        from_attributes = True


# ===================== ADMISSION SCHEMAS =====================

class AdmissionBase(BaseModel):
    """Base admission schema with common fields"""
    patient_id: int = Field(..., gt=0)
    hospital_id: int = Field(..., gt=0)
    priority: PriorityLevel = Field(default=PriorityLevel.MID)
    patient_condition: str = Field(..., min_length=1, max_length=255)
    department: str = Field(..., min_length=1, max_length=100)


class AdmissionCreate(AdmissionBase):
    """Schema for creating a new admission"""
    pass


class AdmissionDischarge(BaseModel):
    """Schema for discharging a patient"""
    discharge_notes: Optional[str] = Field(None, max_length=500)


class AdmissionResponse(AdmissionBase):
    """Schema for admission response"""
    admission_id: int
    admission_time: datetime
    discharge_time: Optional[datetime] = None

    class Config:
        from_attributes = True


# ===================== RESOURCE SCHEMAS =====================

class ResourceBase(BaseModel):
    """Base resource schema with common fields"""
    available_beds: int = Field(..., ge=0)
    available_icu_beds: int = Field(..., ge=0)
    ventilators: int = Field(..., ge=0)
    oxygen_units: int = Field(..., ge=0)


class ResourceCreate(ResourceBase):
    """Schema for creating resources"""
    hospital_id: int = Field(..., gt=0)


class ResourceUpdate(BaseModel):
    """Schema for updating resources"""
    available_beds: Optional[int] = Field(None, ge=0)
    available_icu_beds: Optional[int] = Field(None, ge=0)
    ventilators: Optional[int] = Field(None, ge=0)
    oxygen_units: Optional[int] = Field(None, ge=0)


class ResourceResponse(ResourceBase):
    """Schema for resource response"""
    resource_id: int
    hospital_id: int
    updated_at: datetime

    class Config:
        from_attributes = True


# ===================== PREDICTION SCHEMAS =====================

class PredictionBase(BaseModel):
    """Base prediction schema with common fields"""
    predicted_patients: float = Field(..., ge=0)
    predicted_bed_usage: float = Field(..., ge=0, le=100)
    predicted_icu_usage: float = Field(..., ge=0, le=100)


class PredictionCreate(PredictionBase):
    """Schema for creating predictions"""
    hospital_id: int = Field(..., gt=0)


class PredictionResponse(PredictionBase):
    """Schema for prediction response"""
    prediction_id: int
    hospital_id: int
    prediction_time: datetime

    class Config:
        from_attributes = True


# ===================== ALERT SCHEMAS =====================

class AlertBase(BaseModel):
    """Base alert schema with common fields"""
    alert_type: AlertType
    message: str = Field(..., min_length=1, max_length=500)


class AlertCreate(AlertBase):
    """Schema for creating alerts"""
    hospital_id: int = Field(..., gt=0)


class AlertResponse(AlertBase):
    """Schema for alert response"""
    alert_id: int
    hospital_id: int
    created_at: datetime
    is_resolved: bool

    class Config:
        from_attributes = True


# ===================== ANALYTICS SCHEMAS =====================

class HospitalLoadResponse(BaseModel):
    """Response schema for hospital load analytics"""
    hospital_id: int
    hospital_name: str
    active_patients: int
    total_beds: int
    bed_occupancy_percentage: float = Field(..., ge=0, le=100)
    total_icu_beds: int
    icu_occupancy_percentage: float = Field(..., ge=0, le=100)
    alert_status: str  # "normal", "warning", "critical"


class ResourceStatusResponse(BaseModel):
    """Response schema for resource status"""
    hospital_id: int
    hospital_name: str
    available_beds: int
    total_beds: int
    available_icu_beds: int
    total_icu_beds: int
    ventilators: int
    oxygen_units: int
    updated_at: datetime


class LoadBalanceRecommendation(BaseModel):
    """Response schema for load balance recommendation"""
    recommended_hospital_id: int
    recommended_hospital_name: str
    current_load: int
    available_beds: int
    bed_occupancy_percentage: float
    reason: str


class AnalyticsSummaryResponse(BaseModel):
    """Overall analytics summary"""
    total_hospitals: int
    total_active_patients: int
    average_bed_occupancy: float
    critical_alerts_count: int
    timestamp: datetime


# ===================== ERROR SCHEMAS =====================

class ErrorResponse(BaseModel):
    """Schema for error responses"""
    detail: str
    status_code: int
    timestamp: datetime


# ===================== SUCCESS SCHEMAS =====================

class SuccessResponse(BaseModel):
    """Generic success response"""
    message: str
    data: Optional[dict] = None
