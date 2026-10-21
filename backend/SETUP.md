# CareMatrix Backend - Production Setup Guide

## Quick Overview

**CareMatrix** is a FastAPI-based backend for predictive hospital flow management. It helps hospitals optimize patient admissions, track resource availability, and predict bed occupancy using load-balancing algorithms.

**Key Features:**
- ✅ Patient Management System
- ✅ Hospital & Admission Tracking
- ✅ Real-time Resource Monitoring
- ✅ Hospital Load Analytics
- ✅ Smart Load Balancing (finds hospital with min occupancy)
- ✅ Automatic Alert System (>85% occupancy triggers critical alert)
- ✅ Comprehensive API Documentation

---

## 🚀 Installation & Setup (5 Minutes)

### Step 1: Prerequisites
```bash
# Ensure you have Python 3.8+ installed
python --version

# Ensure MySQL is running
mysql --version
```

### Step 2: Navigate to Server Directory
```bash
cd Server
```

### Step 3: Create Virtual Environment
```bash
# Windows
python -m venv venv
venv\Scripts\activate

# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### Step 4: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 5: Database Setup

**Option A: Automatic Setup (Recommended)**
```bash
# SQLAlchemy will automatically create all tables on first run
# Just configure your database credentials in .env
copy .env.example .env
# Edit .env with your MySQL credentials
```

**Option B: Manual Setup**
```bash
# Create database
mysql -u root -p
> CREATE DATABASE carematrix CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
> EXIT;

# Run SQL schema
mysql -u root -p carematrix < database_schema.sql
```

### Step 6: Configure Environment
Create `.env` file with your database:
```
DATABASE_URL=mysql+mysqlconnector://root:your_password@localhost:3306/carematrix
HOST=0.0.0.0
PORT=8000
DEBUG=True
ALLOWED_ORIGINS=["http://localhost:3000", "http://localhost:5173"]
```

### Step 7: Start Server

**Windows:**
```bash
run_server.bat
```

**Linux/Mac:**
```bash
bash run_server.sh
```

**Manual:**
```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

✅ Server running at: **http://localhost:8000**

---

## 📚 API Documentation

### Access Documentation
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI Schema**: http://localhost:8000/openapi.json

### Main Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |
| POST | `/api/v1/patients` | Create patient |
| GET | `/api/v1/patients` | List patients |
| POST | `/api/v1/hospitals` | Create hospital |
| GET | `/api/v1/hospitals` | List hospitals |
| POST | `/api/v1/admissions` | Admit patient |
| GET | `/api/v1/admissions/active` | Get active admissions |
| **GET** | **`/api/v1/analytics/load-balance`** | **Find best hospital (Load Balancing)** 🎯 |
| GET | `/api/v1/analytics/hospital-load` | Get hospital occupancy |
| GET | `/api/v1/analytics/summary` | Overall analytics |

---

## 🧪 Testing the API

### Option 1: Swagger UI (Easiest)
```
1. Open http://localhost:8000/docs
2. Click any endpoint
3. Click "Try it out"
4. Enter parameters
5. Click "Execute"
```

### Option 2: Test Script
```bash
python test_api.py
```

### Option 3: cURL Commands

**Create Hospital:**
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

**Create Patient:**
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

**Admit Patient:**
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

**Get Load Balancing Recommendation:**
```bash
curl "http://localhost:8000/api/v1/analytics/load-balance"
```

**Response:**
```json
{
  "recommended_hospital_id": 1,
  "recommended_hospital_name": "Central Hospital",
  "current_load": 5,
  "available_beds": 95,
  "bed_occupancy_percentage": 5.0,
  "reason": "Hospital with lowest occupancy (5.0%) and 95 available beds"
}
```

---

## 📊 Key Concepts

### Hospital Load Calculation
```
Occupancy% = (Active Patients / Total Beds) × 100
```

### Alert System
- **Normal**: 0-70% occupancy
- **Warning**: 70-85% occupancy
- **Critical**: ≥85% occupancy (Auto-generates alert)

### Load Balancing Algorithm
1. Query all hospitals
2. Count active patients in each
3. Calculate occupancy percentage
4. **Return hospital with MINIMUM occupancy**
5. Include available beds for decision making

**Use Case**: When new patient arrives, call `/analytics/load-balance` to find optimal hospital.

---

## 📁 Project Structure

```
Server/
├── main.py                 # FastAPI app entry point
├── database.py             # Database config & session
├── models.py               # SQLAlchemy models
├── schemas.py              # Pydantic request/response
├── crud.py                 # Database operations
├── requirements.txt        # Python dependencies
├── .env.example            # Environment template
├── .env                    # Your configuration (CREATE THIS)
├── README.md               # Full documentation
├── SETUP.md                # This file
├── database_schema.sql     # MySQL schema
├── test_api.py            # API testing script
├── run_server.bat         # Windows startup script
├── run_server.sh          # Linux/Mac startup script
├── app.log                # Application logs (auto-generated)
└── routers/
    ├── patients.py        # Patient endpoints
    ├── admissions.py      # Admission endpoints
    ├── hospitals.py       # Hospital endpoints
    └── analytics.py       # Analytics endpoints
```

---

## 🔧 Configuration Options

### Environment Variables (.env)

```
# Database Connection
DATABASE_URL=mysql+mysqlconnector://username:password@host:port/database

# Server Settings
HOST=0.0.0.0          # Listen on all interfaces
PORT=8000             # Server port
DEBUG=True            # Enable debug mode (reload on file change)

# CORS Settings (Frontend origins)
ALLOWED_ORIGINS=["http://localhost:3000", "http://localhost:5173"]
```

### MySQL Connection Examples

**Local Machine:**
```
DATABASE_URL=mysql+pymysql://root:password@localhost:3306/carematrix
```

**Remote Server:**
```
DATABASE_URL=mysql+mysqlconnector://user:pass@192.168.1.100:3306/carematrix
```

**With Special Characters in Password:**
```
DATABASE_URL=mysql+mysqlconnector://user:p%40ssw0rd@localhost:3306/carematrix
```

---

## 🚨 Troubleshooting

### Problem: "ModuleNotFoundError"
**Solution:**
```bash
# Ensure virtual environment is active
venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# Reinstall dependencies
pip install -r requirements.txt
```

### Problem: "MySQL Connection Error"
**Solution:**
```bash
# Verify MySQL is running
mysql -u root -p

# Check DATABASE_URL in .env
DATABASE_URL=mysql+pymysql://root:password@localhost:3306/carematrix

# Create database if it doesn't exist
mysql -u root -p -e "CREATE DATABASE carematrix;"
```

### Problem: "Port 8000 already in use"
**Solution:**
```bash
# Use different port
uvicorn main:app --port 8001

# Or kill process using port 8000
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# Linux/Mac
lsof -i :8000
kill -9 <PID>
```

### Problem: "CORS Error" in frontend
**Solution:**
Edit `.env`:
```
ALLOWED_ORIGINS=["http://localhost:3000", "http://localhost:5173", "http://your-frontend-url"]
```

---

## 📊 Database Tables

### Patients
```sql
SELECT * FROM patients;
-- patient_id, full_name, age, contact, blood_group, created_at
```

### Hospitals
```sql
SELECT * FROM hospitals;
-- hospital_id, name, location, total_beds, total_icu_beds, created_at
```

### Admissions
```sql
SELECT * FROM admissions
WHERE discharge_time IS NULL;  -- Active admissions only
-- admission_id, patient_id, hospital_id, admission_time, discharge_time, priority, patient_condition, department
```

### Resources
```sql
SELECT * FROM resources;
-- resource_id, hospital_id, available_beds, available_icu_beds, ventilators, oxygen_units, updated_at
```

### Alerts
```sql
SELECT * FROM alerts
WHERE is_resolved = 0;  -- Unresolved alerts
-- alert_id, hospital_id, alert_type, message, created_at, is_resolved
```

---

## 🧑‍💻 Development Tips

### Enable SQL Logging
Edit `database.py`:
```python
engine = create_engine(
    DATABASE_URL,
    echo=True  # Set to True to see all SQL queries
)
```

### Add Custom Endpoints
1. Create new function in `routers/your_router.py`
2. Add to `routers/__init__.py`
3. Include in `main.py`: `app.include_router(your_router, prefix="/api/v1")`

### Add Database Fields
1. Modify model in `models.py`
2. Create migration or let SQLAlchemy create table on restart
3. Add schema in `schemas.py`
4. Add CRUD operations in `crud.py`

---

## 📈 Load Testing

### Using simple HTTP requests:
```bash
# Linux/Mac
for i in {1..100}; do
  curl -s "http://localhost:8000/api/v1/analytics/load-balance" &
done

# Windows PowerShell
1..100 | % { curl "http://localhost:8000/api/v1/analytics/load-balance" -UseBasicParsing }
```

---

## 🎯 Next Steps

1. ✅ Install dependencies
2. ✅ Configure `.env` with database
3. ✅ Start server
4. ✅ Open http://localhost:8000/docs
5. ✅ Create test hospitals and patients
6. ✅ Test load balancing endpoint
7. ✅ Connect frontend to API

---

## 📞 Support

- **API Docs**: http://localhost:8000/docs
- **Logs**: Check `app.log` for errors
- **Console**: Watch server output during requests
- **GitHub Issues**: Report bugs or request features

---

## 🚀 Deployment

### Docker (Optional)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Production Settings
```
DEBUG=False
ALLOWED_ORIGINS=["https://yourdomain.com"]
DATABASE_URL=mysql+mysqlconnector://prod_user:secure_pass@prod_host/carematrix
```

---

## ✅ Documentation Checklist

- [x] Installation steps
- [x] API endpoints reference
- [x] Configuration guide
- [x] Troubleshooting
- [x] Project structure
- [x] Testing guide
- [x] Load balancing explanation
- [x] Alert system
- [x] Database schema
- [x] cURL examples

---

**Happy Coding! 🚀**

Generated: March 2026
Version: 1.0.0
