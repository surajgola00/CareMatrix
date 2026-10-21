"""
Patients Router
Handles all patient-related endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from schemas import PatientCreate, PatientResponse
import crud
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/patients",
    tags=["Patients"],
    responses={404: {"description": "Not found"}}
)


@router.post("/", response_model=PatientResponse, status_code=201)
def create_patient(
    patient: PatientCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new patient
    
    - **full_name**: Patient's full name (required)
    - **age**: Patient's age (required)
    - **contact**: Patient's contact number (required)
    - **blood_group**: Patient's blood group (required)
    """
    try:
        return crud.create_patient(db, patient)
    except Exception as e:
        logger.error(f"Error creating patient: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Error creating patient: {str(e)}"
        )


@router.get("/", response_model=list[PatientResponse])
def list_patients(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    db: Session = Depends(get_db)
):
    """
    List all patients with pagination
    
    - **skip**: Number of records to skip (default: 0)
    - **limit**: Number of records to return (default: 100, max: 1000)
    """
    try:
        patients = crud.get_all_patients(db, skip=skip, limit=limit)
        return patients
    except Exception as e:
        logger.error(f"Error listing patients: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving patients"
        )


@router.get("/{patient_id}", response_model=PatientResponse)
def get_patient(
    patient_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a specific patient by ID
    
    - **patient_id**: The ID of the patient (required)
    """
    try:
        patient = crud.get_patient(db, patient_id)
        if not patient:
            raise HTTPException(
                status_code=404,
                detail=f"Patient {patient_id} not found"
            )
        return patient
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving patient: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving patient"
        )


@router.get("/{patient_id}/admissions", response_model=list)
def get_patient_admissions(
    patient_id: int,
    db: Session = Depends(get_db)
):
    """
    Get all admissions for a patient
    
    - **patient_id**: The ID of the patient (required)
    """
    try:
        # Verify patient exists
        patient = crud.get_patient(db, patient_id)
        if not patient:
            raise HTTPException(
                status_code=404,
                detail=f"Patient {patient_id} not found"
            )
        
        admissions = crud.get_patient_admissions(db, patient_id)
        return admissions
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving patient admissions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving patient admissions"
        )
