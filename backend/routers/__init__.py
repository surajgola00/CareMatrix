"""
Routers Package
Initializes all API route modules
"""

from .patients import router as patients_router
from .admissions import router as admissions_router
from .hospitals import router as hospitals_router
from .analytics import router as analytics_router

__all__ = ["patients_router", "admissions_router", "hospitals_router", "analytics_router"]
