"""
CRUD Operations Module
Handles all database Create, Read, Update, Delete operations
"""

from sqlalchemy.orm import Session
from sqlalchemy import desc
from models import Patient, Hospital, Admission, Resource, Prediction, Alert, PriorityLevel, AlertType
from schemas import (
    PatientCreate, HospitalCreate, AdmissionCreate, ResourceCreate, 
    ResourceUpdate, PredictionCreate, AlertCreate
)
from datetime import datetime
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


# ==================== PATIENT OPERATIONS ====================

def create_patient(db: Session, patient: PatientCreate) -> Patient:
    """Create a new patient"""
    try:
        db_patient = Patient(**patient.dict())
        db.add(db_patient)
        db.commit()
        db.refresh(db_patient)
        logger.info(f"Patient created: {db_patient.patient_id}")
        return db_patient
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating patient: {str(e)}")
        raise


def get_patient(db: Session, patient_id: int) -> Optional[Patient]:
    """Get patient by ID"""
    return db.query(Patient).filter(Patient.patient_id == patient_id).first()


def get_all_patients(db: Session, skip: int = 0, limit: int = 100) -> List[Patient]:
    """Get all patients with pagination"""
    return db.query(Patient).offset(skip).limit(limit).all()


def update_patient(db: Session, patient_id: int, patient_data: dict) -> Optional[Patient]:
    """Update patient information"""
    try:
        db_patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
        if not db_patient:
            return None
        
        for key, value in patient_data.items():
            setattr(db_patient, key, value)
        
        db.commit()
        db.refresh(db_patient)
        logger.info(f"Patient updated: {patient_id}")
        return db_patient
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating patient: {str(e)}")
        raise


# ==================== HOSPITAL OPERATIONS ====================

def create_hospital(db: Session, hospital: HospitalCreate) -> Hospital:
    """Create a new hospital"""
    try:
        db_hospital = Hospital(**hospital.dict())
        db.add(db_hospital)
        db.commit()
        db.refresh(db_hospital)
        logger.info(f"Hospital created: {db_hospital.hospital_id}")
        return db_hospital
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating hospital: {str(e)}")
        raise


def get_hospital(db: Session, hospital_id: int) -> Optional[Hospital]:
    """Get hospital by ID"""
    return db.query(Hospital).filter(Hospital.hospital_id == hospital_id).first()


def get_all_hospitals(db: Session, skip: int = 0, limit: int = 100) -> List[Hospital]:
    """Get all hospitals with pagination"""
    return db.query(Hospital).offset(skip).limit(limit).all()


def hospital_exists(db: Session, hospital_id: int) -> bool:
    """Check if hospital exists"""
    return db.query(Hospital).filter(Hospital.hospital_id == hospital_id).first() is not None


# ==================== ADMISSION OPERATIONS ====================

def create_admission(db: Session, admission: AdmissionCreate) -> Admission:
    """Create a new admission"""
    try:
        # Verify patient and hospital exist
        patient = db.query(Patient).filter(Patient.patient_id == admission.patient_id).first()
        hospital = db.query(Hospital).filter(Hospital.hospital_id == admission.hospital_id).first()
        
        if not patient:
            raise ValueError(f"Patient {admission.patient_id} not found")
        if not hospital:
            raise ValueError(f"Hospital {admission.hospital_id} not found")
        
        db_admission = Admission(**admission.dict())
        db.add(db_admission)
        db.commit()
        db.refresh(db_admission)
        logger.info(f"Admission created: {db_admission.admission_id}")
        return db_admission
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating admission: {str(e)}")
        raise


def get_admission(db: Session, admission_id: int) -> Optional[Admission]:
    """Get admission by ID"""
    return db.query(Admission).filter(Admission.admission_id == admission_id).first()


def get_active_admissions(db: Session, hospital_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> List[Admission]:
    """Get all active admissions (discharge_time is NULL)"""
    query = db.query(Admission).filter(Admission.discharge_time.is_(None))
    
    if hospital_id:
        query = query.filter(Admission.hospital_id == hospital_id)
    
    return query.offset(skip).limit(limit).all()


def discharge_patient(db: Session, admission_id: int) -> Optional[Admission]:
    """Discharge a patient"""
    try:
        admission = db.query(Admission).filter(Admission.admission_id == admission_id).first()
        if not admission:
            return None
        
        admission.discharge_time = datetime.utcnow()
        db.commit()
        db.refresh(admission)
        logger.info(f"Patient discharged: {admission_id}")
        return admission
    except Exception as e:
        db.rollback()
        logger.error(f"Error discharging patient: {str(e)}")
        raise


def get_patient_admissions(db: Session, patient_id: int) -> List[Admission]:
    """Get all admissions for a patient"""
    return db.query(Admission).filter(Admission.patient_id == patient_id).all()


# ==================== RESOURCE OPERATIONS ====================

def create_resource(db: Session, resource: ResourceCreate) -> Resource:
    """Create hospital resources"""
    try:
        # Check if hospital exists
        if not hospital_exists(db, resource.hospital_id):
            raise ValueError(f"Hospital {resource.hospital_id} not found")
        
        # Check if resource already exists for hospital
        existing = db.query(Resource).filter(Resource.hospital_id == resource.hospital_id).first()
        if existing:
            raise ValueError(f"Resource already exists for hospital {resource.hospital_id}")
        
        db_resource = Resource(**resource.dict())
        db.add(db_resource)
        db.commit()
        db.refresh(db_resource)
        logger.info(f"Resource created for hospital: {resource.hospital_id}")
        return db_resource
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating resource: {str(e)}")
        raise


def get_hospital_resource(db: Session, hospital_id: int) -> Optional[Resource]:
    """Get resource for a hospital"""
    return db.query(Resource).filter(Resource.hospital_id == hospital_id).first()


def get_all_resources(db: Session, skip: int = 0, limit: int = 100) -> List[Resource]:
    """Get all resources with pagination"""
    return db.query(Resource).offset(skip).limit(limit).all()


def update_hospital_resource(db: Session, hospital_id: int, resource_update: ResourceUpdate) -> Optional[Resource]:
    """Update hospital resources"""
    try:
        resource = db.query(Resource).filter(Resource.hospital_id == hospital_id).first()
        if not resource:
            return None
        
        update_data = resource_update.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(resource, key, value)
        
        resource.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(resource)
        logger.info(f"Resource updated for hospital: {hospital_id}")
        return resource
    except Exception as e:
        db.rollback()
        logger.error(f"Error updating resource: {str(e)}")
        raise


# ==================== PREDICTION OPERATIONS ====================

def create_prediction(db: Session, prediction: PredictionCreate) -> Prediction:
    """Create a prediction"""
    try:
        if not hospital_exists(db, prediction.hospital_id):
            raise ValueError(f"Hospital {prediction.hospital_id} not found")
        
        db_prediction = Prediction(**prediction.dict())
        db.add(db_prediction)
        db.commit()
        db.refresh(db_prediction)
        logger.info(f"Prediction created for hospital: {prediction.hospital_id}")
        return db_prediction
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating prediction: {str(e)}")
        raise


def get_latest_predictions(db: Session, hospital_id: Optional[int] = None, limit: int = 10) -> List[Prediction]:
    """Get latest predictions"""
    query = db.query(Prediction).order_by(desc(Prediction.prediction_time))
    
    if hospital_id:
        query = query.filter(Prediction.hospital_id == hospital_id)
    
    return query.limit(limit).all()


# ==================== ALERT OPERATIONS ====================

def create_alert(db: Session, alert: AlertCreate) -> Alert:
    """Create an alert"""
    try:
        if not hospital_exists(db, alert.hospital_id):
            raise ValueError(f"Hospital {alert.hospital_id} not found")
        
        db_alert = Alert(**alert.dict())
        db.add(db_alert)
        db.commit()
        db.refresh(db_alert)
        logger.info(f"Alert created: {db_alert.alert_id}")
        return db_alert
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating alert: {str(e)}")
        raise


def get_alert(db: Session, alert_id: int) -> Optional[Alert]:
    """Get alert by ID"""
    return db.query(Alert).filter(Alert.alert_id == alert_id).first()


def get_unresolved_alerts(db: Session, hospital_id: Optional[int] = None, skip: int = 0, limit: int = 100) -> List[Alert]:
    """Get unresolved alerts"""
    query = db.query(Alert).filter(Alert.is_resolved == 0).order_by(desc(Alert.created_at))
    
    if hospital_id:
        query = query.filter(Alert.hospital_id == hospital_id)
    
    return query.offset(skip).limit(limit).all()


def resolve_alert(db: Session, alert_id: int) -> Optional[Alert]:
    """Mark alert as resolved"""
    try:
        alert = db.query(Alert).filter(Alert.alert_id == alert_id).first()
        if not alert:
            return None
        
        alert.is_resolved = 1
        db.commit()
        db.refresh(alert)
        logger.info(f"Alert resolved: {alert_id}")
        return alert
    except Exception as e:
        db.rollback()
        logger.error(f"Error resolving alert: {str(e)}")
        raise


def generate_alert_if_needed(db: Session, hospital_id: int, occupancy_percentage: float) -> Optional[Alert]:
    """Generate alert if hospital load exceeds 85%"""
    try:
        if occupancy_percentage >= 85:
            # Check if alert already exists
            existing_alert = db.query(Alert).filter(
                Alert.hospital_id == hospital_id,
                Alert.alert_type == AlertType.CRITICAL,
                Alert.is_resolved == 0
            ).first()
            
            if not existing_alert:
                alert = AlertCreate(
                    hospital_id=hospital_id,
                    alert_type=AlertType.CRITICAL,
                    message=f"Hospital bed occupancy at {occupancy_percentage:.1f}% - exceeds 85% threshold"
                )
                return create_alert(db, alert)
    except Exception as e:
        logger.error(f"Error generating alert: {str(e)}")
    
    return None
