"""
Hospitals Router
Handles all hospital-related endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from schemas import HospitalCreate, HospitalResponse, ResourceCreate, ResourceResponse, ResourceUpdate
import crud
import logging

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/hospitals",
    tags=["Hospitals"],
    responses={404: {"description": "Not found"}}
)


@router.post("/", response_model=HospitalResponse, status_code=201)
def create_hospital(
    hospital: HospitalCreate,
    db: Session = Depends(get_db)
):
    """
    Create a new hospital
    
    - **name**: Hospital name (required, must be unique)
    - **location**: Hospital location (required)
    - **total_beds**: Total number of beds (required)
    - **total_icu_beds**: Total number of ICU beds (required)
    """
    try:
        return crud.create_hospital(db, hospital)
    except Exception as e:
        logger.error(f"Error creating hospital: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Error creating hospital: {str(e)}"
        )


@router.get("/", response_model=list[HospitalResponse])
def list_hospitals(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    db: Session = Depends(get_db)
):
    """
    List all hospitals with pagination
    
    - **skip**: Number of records to skip (default: 0)
    - **limit**: Number of records to return (default: 100, max: 1000)
    """
    try:
        hospitals = crud.get_all_hospitals(db, skip=skip, limit=limit)
        return hospitals
    except Exception as e:
        logger.error(f"Error listing hospitals: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving hospitals"
        )


@router.get("/{hospital_id}", response_model=HospitalResponse)
def get_hospital(
    hospital_id: int,
    db: Session = Depends(get_db)
):
    """
    Get a specific hospital by ID
    
    - **hospital_id**: The ID of the hospital (required)
    """
    try:
        hospital = crud.get_hospital(db, hospital_id)
        if not hospital:
            raise HTTPException(
                status_code=404,
                detail=f"Hospital {hospital_id} not found"
            )
        return hospital
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving hospital: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving hospital"
        )


# ==================== RESOURCE ENDPOINTS ====================

@router.post("/{hospital_id}/resources", response_model=ResourceResponse, status_code=201)
def create_hospital_resources(
    hospital_id: int,
    resources: dict,
    db: Session = Depends(get_db)
):
    """
    Create resources for a hospital
    
    - **hospital_id**: The ID of the hospital (required)
    - **available_beds**: Number of available beds (required)
    - **available_icu_beds**: Number of available ICU beds (required)
    - **ventilators**: Number of ventilators (required)
    - **oxygen_units**: Number of oxygen units (required)
    """
    try:
        resource_create = ResourceCreate(hospital_id=hospital_id, **resources)
        return crud.create_resource(db, resource_create)
    except ValueError as ve:
        logger.error(f"Validation error: {str(ve)}")
        raise HTTPException(
            status_code=400,
            detail=str(ve)
        )
    except Exception as e:
        logger.error(f"Error creating resources: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Error creating resources: {str(e)}"
        )


@router.get("/{hospital_id}/resources", response_model=ResourceResponse)
def get_hospital_resources(
    hospital_id: int,
    db: Session = Depends(get_db)
):
    """
    Get resource information for a hospital
    
    - **hospital_id**: The ID of the hospital (required)
    """
    try:
        # Verify hospital exists
        if not crud.hospital_exists(db, hospital_id):
            raise HTTPException(
                status_code=404,
                detail=f"Hospital {hospital_id} not found"
            )
        
        resource = crud.get_hospital_resource(db, hospital_id)
        if not resource:
            raise HTTPException(
                status_code=404,
                detail=f"Resources not found for hospital {hospital_id}"
            )
        return resource
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving resources: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving resources"
        )


@router.put("/{hospital_id}/resources", response_model=ResourceResponse)
def update_hospital_resources(
    hospital_id: int,
    resource_update: ResourceUpdate,
    db: Session = Depends(get_db)
):
    """
    Update resource information for a hospital
    
    - **hospital_id**: The ID of the hospital (required)
    - All fields are optional - only provided fields will be updated
    """
    try:
        # Verify hospital exists
        if not crud.hospital_exists(db, hospital_id):
            raise HTTPException(
                status_code=404,
                detail=f"Hospital {hospital_id} not found"
            )
        
        resource = crud.update_hospital_resource(db, hospital_id, resource_update)
        if not resource:
            raise HTTPException(
                status_code=404,
                detail=f"Resources not found for hospital {hospital_id}"
            )
        return resource
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating resources: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Error updating resources: {str(e)}"
        )
