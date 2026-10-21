# CareMatrix Backend API

**Predictive Hospital Flow & Patient Optimization System**

A production-ready FastAPI backend for managing hospital patient flows, resource allocation, and predictive analytics.

---

## 🚀 Quick Start

### Prerequisites
- Python 3.8+
- MySQL 5.7+
- pip or conda

### Installation

1. **Clone/Navigate to the project:**
   ```bash
   cd Server
   ```

2. **Create a virtual environment:**
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate
   
   # Linux/Mac
   python3 -m venv venv
   source venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure environment:**
   ```bash
   # Copy the example file
   cp .env.example .env
   
   # Edit .env with your database credentials
   # DATABASE_URL=mysql+mysqlconnector://root:password@localhost:3306/carematrix
   ```

5. **Create database:**
   ```bash
   # Using MySQL CLI
   mysql -u root -p
   > CREATE DATABASE carematrix CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   > EXIT;
   ```

6. **Run the server:**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000 --reload
   ```

   Server will start at: `http://localhost:8000`

---

## 📚 API Documentation

### Interactive Documentation
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI Schema**: http://localhost:8000/openapi.json

### API Endpoints

#### Health & Info
```
GET  /health              - Health check
GET  /                    - API information
```

#### Patients (`/api/v1/patients`)
```
POST   /                          - Create patient
GET    /                          - List patients
GET    /{patient_id}              - Get patient details
GET    /{patient_id}/admissions   - Get patient admission history
```

#### Admissions (`/api/v1/admissions`)
```
POST   /                                    - Admit patient
GET    /active                              - Get active admissions
GET    /{admission_id}                      - Get admission details
POST   /{admission_id}/discharge            - Discharge patient
GET    /hospital/{hospital_id}/active       - Get hospital's active admissions
```

#### Hospitals (`/api/v1/hospitals`)
```
POST   /                         - Create hospital
GET    /                         - List hospitals
GET    /{hospital_id}            - Get hospital details
POST   /{hospital_id}/resources  - Add hospital resources
GET    /{hospital_id}/resources  - Get hospital resources
PUT    /{hospital_id}/resources  - Update hospital resources
```

#### Analytics (`/api/v1/analytics`) ⭐ KEY FEATURES
```
GET    /hospital-load           - Get active patient load per hospital
GET    /resource-status         - Get resource availability per hospital
GET    /load-balance            - Get load balancing recommendation 🎯
GET    /summary                 - Get overall analytics summary
GET    /alerts/unresolved       - Get unresolved alerts
POST   /alerts/{alert_id}/resolve - Resolve an alert
```

---

## 🏗️ Project Structure

```
Server/
├── main.py              # FastAPI application entry point
├── database.py          # Database connection & session management
├── models.py            # SQLAlchemy ORM models
├── schemas.py           # Pydantic request/response schemas
├── crud.py              # Database CRUD operations
├── requirements.txt     # Python dependencies
├── .env.example         # Environment configuration template
├── app.log              # Application logs (auto-generated)
└── routers/
    ├── __init__.py
    ├── patients.py      # Patient management endpoints
    ├── admissions.py    # Admission/discharge endpoints
    ├── hospitals.py     # Hospital & resource endpoints
    └── analytics.py     # Analytics & load balancing endpoints
```

---

## 🗄️ Database Schema

### Patients Table
```
- patient_id (PK)
- full_name (VARCHAR 255)
- age (INT)
- contact (VARCHAR 20)
- blood_group (VARCHAR 10)
- created_at (DATETIME)
```

### Hospitals Table
```
- hospital_id (PK)
- name (VARCHAR 255)
- location (VARCHAR 255)
- total_beds (INT)
- total_icu_beds (INT)
- created_at (DATETIME)
```

### Admissions Table
```
- admission_id (PK)
- patient_id (FK → Patients)
- hospital_id (FK → Hospitals)
- admission_time (DATETIME)
- discharge_time (DATETIME nullable)
- priority (ENUM: low, mid, high)
- patient_condition (VARCHAR 255)
- department (VARCHAR 100)
```

### Resources Table
```
- resource_id (PK)
- hospital_id (FK → Hospitals)
- available_beds (INT)
- available_icu_beds (INT)
- ventilators (INT)
- oxygen_units (INT)
- updated_at (DATETIME)
```

### Predictions Table
```
- prediction_id (PK)
- hospital_id (FK → Hospitals)
- prediction_time (DATETIME)
- predicted_patients (FLOAT)
- predicted_bed_usage (FLOAT)
- predicted_icu_usage (FLOAT)
```

### Alerts Table
```
- alert_id (PK)
- hospital_id (FK → Hospitals)
- alert_type (ENUM: critical, warning, info)
- message (VARCHAR 500)
- created_at (DATETIME)
- is_resolved (INT: 0=not resolved, 1=resolved)
```

---

## 📊 Analytics & Load Balancing

### Hospital Load Calculation
```
Bed Occupancy % = (Active Patients / Total Beds) × 100
```

### Alert Thresholds
```
Normal:    0-70% occupancy
Warning:   70-85% occupancy
Critical:  ≥85% occupancy → Auto-generates alert
```

### Load Balancing Algorithm
```
1. Get all hospitals and their active patient counts
2. Calculate occupancy percentage for each
3. Find hospital with MINIMUM occupancy
4. Return recommended hospital with available beds
```

**Use Case**: When a patient arrives, call `/api/v1/analytics/load-balance` to find the optimal hospital for admission.

---

## 🔐 Middleware & Security

- **CORS**: Enabled for frontend applications (configurable in .env)
- **Logging**: All requests logged to console and `app.log`
- **Error Handling**: Global exception handler with detailed logging
- **Session Management**: SQLAlchemy with connection pooling

---

## 🛠️ Configuration

### Environment Variables (.env)
```
# Database
DATABASE_URL=mysql+mysqlconnector://root:password@localhost:3306/carematrix

# Server
HOST=0.0.0.0
PORT=8000
DEBUG=True

# CORS
ALLOWED_ORIGINS=["http://localhost:3000", "http://localhost:5173"]
```

---

## 📝 Example API Calls

### 1. Create a Hospital
```bash
curl -X POST "http://localhost:8000/api/v1/hospitals/" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Central Hospital",
    "location": "Downtown",
    "total_beds": 100,
    "total_icu_beds": 20
  }'
```

### 2. Create a Patient
```bash
curl -X POST "http://localhost:8000/api/v1/patients/" \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "John Doe",
    "age": 45,
    "contact": "9876543210",
    "blood_group": "O+"
  }'
```

### 3. Admit Patient
```bash
curl -X POST "http://localhost:8000/api/v1/admissions/" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": 1,
    "hospital_id": 1,
    "priority": "high",
    "patient_condition": "Pneumonia",
    "department": "General Ward"
  }'
```

### 4. Get Hospital Load
```bash
curl "http://localhost:8000/api/v1/analytics/hospital-load"
```

### 5. Get Load Balancing Recommendation
```bash
curl "http://localhost:8000/api/v1/analytics/load-balance"
```

---

## 🔍 Logging

Logs are written to:
- **Console**: Real-time output
- **File**: `app.log` with timestamps

Log levels:
- INFO: General information
- WARNING: Warning messages
- ERROR: Error details
- DEBUG: Debug information

---

## 🚨 Error Handling

All endpoints return standardized error responses:

```json
{
  "detail": "Error message",
  "status_code": 400
}
```

Common status codes:
- `200`: Success
- `201`: Created
- `400`: Bad request
- `404`: Not found
- `500`: Server error

---

## 📈 Performance Considerations

- **Connection Pooling**: SQLAlchemy with QueuePool (10 connections, 20 overflow)
- **Connection Verification**: `pool_pre_ping=True` to verify connections
- **Pagination**: All list endpoints support `skip` and `limit` parameters
- **Indexing**: Primary keys and foreign keys indexed by default

---

## 🧪 Testing

### Using Swagger UI
1. Open http://localhost:8000/docs
2. Click on any endpoint
3. Click "Try it out"
4. Enter parameters
5. Click "Execute"

### Using curl
See "Example API Calls" section above

---

## 📦 Dependencies

- **FastAPI**: Modern web framework
- **Uvicorn**: ASGI server
- **SQLAlchemy**: ORM
- **MySQL Connector**: MySQL connector for Python
- **Pydantic**: Data validation
- **python-dotenv**: Environment management

---

## 🤝 Contributing

1. Follow the existing code structure
2. Add docstrings to functions
3. Use type hints
4. Add error handling
5. Update this README for new features

---

## 📄 License

Project for CareMatrix Hackathon

---

## 📞 Support

For issues or questions, check:
- API Documentation: http://localhost:8000/docs
- Application logs: `app.log`
- Console output during startup

---

## 🎯 Key Features Implemented

✅ Patient Management (Create, Read, List)
✅ Hospital Management (Create, Read, List, Resources)
✅ Admission/Discharge Tracking
✅ Active Patient Count per Hospital
✅ Load Balancing Algorithm (Find hospital with min load)
✅ Alert Generation (>85% occupancy)
✅ Resource Tracking (Beds, ICU, Ventilators, Oxygen)
✅ Analytics Dashboard
✅ CORS Middleware
✅ Comprehensive Logging
✅ Error Handling
✅ Swagger/OpenAPI Documentation

---

Generated: March 2026
Version: 1.0.0
