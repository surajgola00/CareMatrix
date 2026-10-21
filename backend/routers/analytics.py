"""
Analytics Router
Handles analytics and load balancing endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from database import get_db
from schemas import HospitalLoadResponse, ResourceStatusResponse, LoadBalanceRecommendation, AnalyticsSummaryResponse
import crud
import logging
from datetime import datetime
from typing import List

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"],
    responses={404: {"description": "Not found"}}
)


@router.get("/hospital-load", response_model=List[HospitalLoadResponse])
def get_hospital_load(
    hospital_id: int = Query(None, description="Filter by specific hospital ID (optional)"),
    db: Session = Depends(get_db)
):
    """
    Get current patient load for all hospitals
    
    Returns:
    - active_patients: Number of currently admitted patients
    - bed_occupancy_percentage: Percentage of beds currently occupied
    - icu_occupancy_percentage: Percentage of ICU beds currently occupied
    - alert_status: "normal", "warning", or "critical" (>85% occupancy)
    
    - **hospital_id**: Filter by specific hospital (optional)
    """
    try:
        if hospital_id:
            # Specific hospital
            hospitals = [crud.get_hospital(db, hospital_id)]
            if not hospitals[0]:
                raise HTTPException(
                    status_code=404,
                    detail=f"Hospital {hospital_id} not found"
                )
        else:
            # All hospitals
            hospitals = crud.get_all_hospitals(db, skip=0, limit=1000)
        
        load_data = []
        
        for hospital in hospitals:
            # Count active admissions
            active_admissions = crud.get_active_admissions(db, hospital_id=hospital.hospital_id)
            active_count = len(active_admissions)
            
            # Count active ICU admissions
            icu_count = len([a for a in active_admissions if a.department.lower() == "icu"])
            
            # Calculate occupancy percentages
            bed_occupancy = (active_count / hospital.total_beds * 100) if hospital.total_beds > 0 else 0
            icu_occupancy = (icu_count / hospital.total_icu_beds * 100) if hospital.total_icu_beds > 0 else 0
            
            # Determine alert status
            if bed_occupancy >= 85:
                alert_status = "critical"
                # Generate alert if needed
                crud.generate_alert_if_needed(db, hospital.hospital_id, bed_occupancy)
            elif bed_occupancy >= 70:
                alert_status = "warning"
            else:
                alert_status = "normal"
            
            load_data.append(HospitalLoadResponse(
                hospital_id=hospital.hospital_id,
                hospital_name=hospital.name,
                active_patients=active_count,
                total_beds=hospital.total_beds,
                bed_occupancy_percentage=round(bed_occupancy, 2),
                total_icu_beds=hospital.total_icu_beds,
                icu_occupancy_percentage=round(icu_occupancy, 2),
                alert_status=alert_status
            ))
        
        return load_data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating hospital load: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error calculating hospital load"
        )


@router.get("/resource-status", response_model=List[ResourceStatusResponse])
def get_resource_status(
    hospital_id: int = Query(None, description="Filter by specific hospital ID (optional)"),
    db: Session = Depends(get_db)
):
    """
    Get current resource availability across hospitals
    
    Returns resource information including:
    - available_beds and ICU beds
    - ventilators and oxygen units
    - last updated timestamp
    
    - **hospital_id**: Filter by specific hospital (optional)
    """
    try:
        if hospital_id:
            hospitals = [crud.get_hospital(db, hospital_id)]
            if not hospitals[0]:
                raise HTTPException(
                    status_code=404,
                    detail=f"Hospital {hospital_id} not found"
                )
        else:
            hospitals = crud.get_all_hospitals(db, skip=0, limit=1000)
        
        resource_data = []
        
        for hospital in hospitals:
            resource = crud.get_hospital_resource(db, hospital.hospital_id)
            
            if resource:
                resource_data.append(ResourceStatusResponse(
                    hospital_id=hospital.hospital_id,
                    hospital_name=hospital.name,
                    available_beds=resource.available_beds,
                    total_beds=hospital.total_beds,
                    available_icu_beds=resource.available_icu_beds,
                    total_icu_beds=hospital.total_icu_beds,
                    ventilators=resource.ventilators,
                    oxygen_units=resource.oxygen_units,
                    updated_at=resource.updated_at
                ))
        
        return resource_data
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving resource status: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving resource status"
        )


@router.get("/load-balance", response_model=LoadBalanceRecommendation)
def get_load_balance_recommendation(
    exclude_hospital_id: int = Query(None, description="Hospital ID to exclude from recommendation (optional)"),
    db: Session = Depends(get_db)
):
    """
    Recommend the hospital with the lowest patient load for transfer/admission
    
    KEY FEATURE: Load Balancing across hospitals
    
    Logic:
    - Hospital load = count of active admissions / total beds * 100
    - Finds hospital with minimum active patients
    - Excludes option to filter out specific hospital
    
    - **exclude_hospital_id**: Exclude a specific hospital from recommendation (optional)
    """
    try:
        hospitals = crud.get_all_hospitals(db, skip=0, limit=1000)
        
        if not hospitals:
            raise HTTPException(
                status_code=404,
                detail="No hospitals found in system"
            )
        
        best_hospital = None
        min_load = float('inf')
        loads = {}
        
        for hospital in hospitals:
            # Skip excluded hospital
            if exclude_hospital_id and hospital.hospital_id == exclude_hospital_id:
                continue
            
            # Count active admissions
            active_admissions = crud.get_active_admissions(db, hospital_id=hospital.hospital_id)
            active_count = len(active_admissions)
            
            # Calculate load percentage
            load_percentage = (active_count / hospital.total_beds * 100) if hospital.total_beds > 0 else 0
            loads[hospital.hospital_id] = {
                'hospital': hospital,
                'active_count': active_count,
                'load_percentage': load_percentage
            }
            
            # Find hospital with minimum load
            if load_percentage < min_load:
                min_load = load_percentage
                best_hospital = hospital
                best_active_count = active_count
        
        if not best_hospital:
            raise HTTPException(
                status_code=400,
                detail="No suitable hospital found for recommendation"
            )
        
        resource = crud.get_hospital_resource(db, best_hospital.hospital_id)
        available_beds = resource.available_beds if resource else (best_hospital.total_beds - best_active_count)
        
        return LoadBalanceRecommendation(
            recommended_hospital_id=best_hospital.hospital_id,
            recommended_hospital_name=best_hospital.name,
            current_load=best_active_count,
            available_beds=available_beds,
            bed_occupancy_percentage=round(min_load, 2),
            reason=f"Hospital with lowest occupancy ({min_load:.1f}%) and {available_beds} available beds"
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error calculating load balance: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error calculating load balance recommendation"
        )


@router.get("/summary", response_model=AnalyticsSummaryResponse)
def get_analytics_summary(
    db: Session = Depends(get_db)
):
    """
    Get overall analytics summary across all hospitals
    
    Returns:
    - Total number of hospitals in system
    - Total active patients across all hospitals
    - Average bed occupancy percentage
    - Number of critical alerts
    """
    try:
        hospitals = crud.get_all_hospitals(db, skip=0, limit=1000)
        
        total_hospitals = len(hospitals)
        total_active_patients = 0
        total_beds = 0
        critical_alerts = len(crud.get_unresolved_alerts(db, skip=0, limit=10000))
        
        for hospital in hospitals:
            active_admissions = crud.get_active_admissions(db, hospital_id=hospital.hospital_id)
            total_active_patients += len(active_admissions)
            total_beds += hospital.total_beds
        
        average_occupancy = (total_active_patients / total_beds * 100) if total_beds > 0 else 0
        
        return AnalyticsSummaryResponse(
            total_hospitals=total_hospitals,
            total_active_patients=total_active_patients,
            average_bed_occupancy=round(average_occupancy, 2),
            critical_alerts_count=critical_alerts,
            timestamp=datetime.utcnow()
        )
    
    except Exception as e:
        logger.error(f"Error retrieving analytics summary: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving analytics summary"
        )


@router.get("/alerts/unresolved", response_model=list)
def get_unresolved_alerts(
    hospital_id: int = Query(None, description="Filter by specific hospital ID (optional)"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db)
):
    """
    Get all unresolved alerts
    
    - **hospital_id**: Filter by specific hospital (optional)
    - **skip**: Number of records to skip
    - **limit**: Number of records to return
    """
    try:
        alerts = crud.get_unresolved_alerts(db, hospital_id=hospital_id, skip=skip, limit=limit)
        return alerts
    except Exception as e:
        logger.error(f"Error retrieving alerts: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Error retrieving alerts"
        )


@router.post("/alerts/{alert_id}/resolve")
def resolve_alert(
    alert_id: int,
    db: Session = Depends(get_db)
):
    """
    Mark an alert as resolved
    
    - **alert_id**: The ID of the alert to resolve
    """
    try:
        alert = crud.resolve_alert(db, alert_id)
        if not alert:
            raise HTTPException(
                status_code=404,
                detail=f"Alert {alert_id} not found"
            )
        return {"message": "Alert resolved successfully", "alert_id": alert_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resolving alert: {str(e)}")
        raise HTTPException(
            status_code=400,
            detail=f"Error resolving alert: {str(e)}"
        )
