"""
Admissions Router
Handles all admission-related endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from schemas import AdmissionCreate, AdmissionResponse, AdmissionDischarge, SuccessResponse
import crud
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admissions",
    tags=["Admissions"],
    responses={404: {"description": "Not found"}}
)


@router.post("/", response_model=AdmissionResponse, status_code=201)
def create_admission(
    admission: AdmissionCreate,
    db: Session = Depends(get_db)
):
    """
    Admit a patient to a hospital
    
    - **patient_id**: The ID of the patient (required)
    - **hospital_id**: The ID of the hospital (required)
    - **priority**: Priority level - low, mid, high (default: mid)
    - **patient_condition**: Description of patient's condition (required)
    - **department**: Department for admission (required)
    """
    try:
        return crud.create_admission(db, admission)
    except ValueError as ve:
        logger.error(f"Validation error: {str(ve)}")
        raise HTTPException(
            status_code=404,
            detail=str(ve)
        )
    except Exception as e:
        logger.error(f"Error creating admission: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Error creating admission: {str(e)}"
        )


@router.get("/active", response_model=list[AdmissionResponse])
def get_active_admissions(
    hospital_id: int = Query(None, description="Filter by hospital ID (optional)"),
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    db: Session = Depends(get_db)
):
    """
    Get all active admissions (patients not yet discharged)
    
    - **hospital_id**: Filter by hospital ID (optional)
    - **skip**: Number of records to skip (default: 0)
    - **limit**: Number of records to return (default: 100)
    """
    try:
        admissions = crud.get_active_admissions(
            db,
            hospital_id=hospital_id,
            skip=skip,
            limit=limit
        )
        return admissions
    except Exception as e:
        logger.error(f"Error retrieving active admissions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving active admissions"
        )


@router.get("/{admission_id}", response_model=AdmissionResponse)
def get_admission(
    admission_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a specific admission by ID
    
    - **admission_id**: The ID of the admission (required)
    """
    try:
        admission = crud.get_admission(db, admission_id)
        if not admission:
            raise HTTPException(
                status_code=404,
                detail=f"Admission {admission_id} not found"
            )
        return admission
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving admission: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving admission"
        )


@router.post("/{admission_id}/discharge", response_model=AdmissionResponse)
def discharge_patient(
    admission_id: int,
    discharge_data: AdmissionDischarge = None,
    db: Session = Depends(get_db)
):
    """
    Discharge a patient from hospital
    
    - **admission_id**: The ID of the admission (required)
    - **discharge_notes**: Optional discharge notes
    """
    try:
        admission = crud.discharge_patient(db, admission_id)
        if not admission:
            raise HTTPException(
                status_code=404,
                detail=f"Admission {admission_id} not found"
            )
        return admission
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error discharging patient: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Error discharging patient: {str(e)}"
        )


@router.get("/hospital/{hospital_id}/active", response_model=list[AdmissionResponse])
def get_hospital_active_admissions(
    hospital_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """
    Get all active admissions at a specific hospital
    
    - **hospital_id**: The ID of the hospital (required)
    """
    try:
        # Verify hospital exists
        if not crud.hospital_exists(db, hospital_id):
            raise HTTPException(
                status_code=404,
                detail=f"Hospital {hospital_id} not found"
            )
        
        admissions = crud.get_active_admissions(
            db,
            hospital_id=hospital_id,
            skip=skip,
            limit=limit
        )
        return admissions
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving hospital admissions: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving hospital admissions"
        )
