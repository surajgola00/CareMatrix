-- CareMatrix Database Schema
-- MySQL Database Setup Script
-- Run this script if you want to manually create tables instead of letting SQLAlchemy do it

CREATE DATABASE IF NOT EXISTS carematrix CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE carematrix;

-- ==================== PATIENTS TABLE ====================
CREATE TABLE IF NOT EXISTS patients (
    patient_id INT AUTO_INCREMENT PRIMARY KEY,
    full_name VARCHAR(255) NOT NULL,
    age INT NOT NULL,
    contact VARCHAR(20) NOT NULL,
    blood_group VARCHAR(10) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==================== HOSPITALS TABLE ====================
CREATE TABLE IF NOT EXISTS hospitals (
    hospital_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    location VARCHAR(255) NOT NULL,
    total_beds INT NOT NULL,
    total_icu_beds INT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_name (name),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==================== ADMISSIONS TABLE ====================
CREATE TABLE IF NOT EXISTS admissions (
    admission_id INT AUTO_INCREMENT PRIMARY KEY,
    patient_id INT NOT NULL,
    hospital_id INT NOT NULL,
    admission_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    discharge_time DATETIME NULL,
    priority ENUM('low', 'mid', 'high') DEFAULT 'mid',
    patient_condition VARCHAR(255) NOT NULL,
    department VARCHAR(100) NOT NULL,
    FOREIGN KEY (patient_id) REFERENCES patients(patient_id) ON DELETE CASCADE,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    INDEX idx_patient_id (patient_id),
    INDEX idx_hospital_id (hospital_id),
    INDEX idx_admission_time (admission_time),
    INDEX idx_discharge_time (discharge_time),
    INDEX idx_active_admissions (discharge_time, hospital_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==================== RESOURCES TABLE ====================
CREATE TABLE IF NOT EXISTS resources (
    resource_id INT AUTO_INCREMENT PRIMARY KEY,
    hospital_id INT NOT NULL UNIQUE,
    available_beds INT NOT NULL,
    available_icu_beds INT NOT NULL,
    ventilators INT NOT NULL,
    oxygen_units INT NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    INDEX idx_hospital_id (hospital_id),
    INDEX idx_updated_at (updated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==================== PREDICTIONS TABLE ====================
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id INT AUTO_INCREMENT PRIMARY KEY,
    hospital_id INT NOT NULL,
    prediction_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    predicted_patients FLOAT NOT NULL,
    predicted_bed_usage FLOAT NOT NULL,
    predicted_icu_usage FLOAT NOT NULL,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    INDEX idx_hospital_id (hospital_id),
    INDEX idx_prediction_time (prediction_time)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==================== ALERTS TABLE ====================
CREATE TABLE IF NOT EXISTS alerts (
    alert_id INT AUTO_INCREMENT PRIMARY KEY,
    hospital_id INT NOT NULL,
    alert_type ENUM('critical', 'warning', 'info') NOT NULL,
    message VARCHAR(500) NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_resolved INT DEFAULT 0,
    FOREIGN KEY (hospital_id) REFERENCES hospitals(hospital_id) ON DELETE CASCADE,
    INDEX idx_hospital_id (hospital_id),
    INDEX idx_alert_type (alert_type),
    INDEX idx_is_resolved (is_resolved),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==================== INSERT SAMPLE DATA ====================
-- Uncomment this section to add sample data

/*
-- Sample Hospitals
INSERT INTO hospitals (name, location, total_beds, total_icu_beds) VALUES
('Central Hospital', 'Downtown', 100, 20),
('Medical City', 'North District', 150, 30),
('Emergency Care Center', 'East Zone', 80, 15);

-- Sample Patients
INSERT INTO patients (full_name, age, contact, blood_group) VALUES
('John Doe', 45, '9876543210', 'O+'),
('Jane Smith', 38, '8765432109', 'A+'),
('Robert Johnson', 52, '7654321098', 'B-'),
('Emily Williams', 29, '6543210987', 'AB+');

-- Sample Resources
INSERT INTO resources (hospital_id, available_beds, available_icu_beds, ventilators, oxygen_units) VALUES
(1, 50, 15, 8, 50),
(2, 80, 20, 12, 75),
(3, 40, 10, 5, 30);

-- Sample Admissions
INSERT INTO admissions (patient_id, hospital_id, admission_time, priority, patient_condition, department) VALUES
(1, 1, NOW() - INTERVAL 2 DAY, 'high', 'Severe Pneumonia', 'General Ward'),
(2, 1, NOW() - INTERVAL 1 DAY, 'mid', 'Heart Issues', 'Cardiology'),
(3, 2, NOW(), 'high', 'Critical Care', 'ICU'),
(4, 2, NOW() - INTERVAL 3 DAY, 'low', 'Minor Surgery Recovery', 'General Ward');

*/

-- ==================== CREATE VIEWS ====================
-- Active Admissions View
CREATE OR REPLACE VIEW active_admissions AS
SELECT 
    a.admission_id,
    a.patient_id,
    p.full_name,
    a.hospital_id,
    h.name as hospital_name,
    a.admission_time,
    a.priority,
    a.patient_condition,
    a.department,
    DATEDIFF(CURDATE(), DATE(a.admission_time)) as days_admitted
FROM admissions a
JOIN patients p ON a.patient_id = p.patient_id
JOIN hospitals h ON a.hospital_id = h.hospital_id
WHERE a.discharge_time IS NULL;

-- Hospital Load View
CREATE OR REPLACE VIEW hospital_load AS
SELECT 
    h.hospital_id,
    h.name,
    h.total_beds,
    h.total_icu_beds,
    COUNT(DISTINCT CASE WHEN a.discharge_time IS NULL THEN a.admission_id END) as active_patients,
    ROUND(COUNT(DISTINCT CASE WHEN a.discharge_time IS NULL THEN a.admission_id END) * 100.0 / h.total_beds, 2) as bed_occupancy_percent,
    CASE 
        WHEN (COUNT(DISTINCT CASE WHEN a.discharge_time IS NULL THEN a.admission_id END) * 100.0 / h.total_beds) >= 85 THEN 'critical'
        WHEN (COUNT(DISTINCT CASE WHEN a.discharge_time IS NULL THEN a.admission_id END) * 100.0 / h.total_beds) >= 70 THEN 'warning'
        ELSE 'normal'
    END as alert_status
FROM hospitals h
LEFT JOIN admissions a ON h.hospital_id = a.hospital_id
GROUP BY h.hospital_id, h.name, h.total_beds, h.total_icu_beds;

-- Unresolved Alerts View
CREATE OR REPLACE VIEW unresolved_alerts AS
SELECT 
    al.alert_id,
    al.hospital_id,
    h.name as hospital_name,
    al.alert_type,
    al.message,
    al.created_at,
    TIMESTAMPDIFF(HOUR, al.created_at, NOW()) as hours_since_alert
FROM alerts al
JOIN hospitals h ON al.hospital_id = h.hospital_id
WHERE al.is_resolved = 0
ORDER BY al.created_at DESC;

-- ==================== QUERIES FOR TESTING ====================
-- View active admissions
-- SELECT * FROM active_admissions;

-- View hospital load
-- SELECT * FROM hospital_load;

-- View unresolved alerts
-- SELECT * FROM unresolved_alerts;

-- Get hospital with minimum load
-- SELECT * FROM hospital_load ORDER BY active_patients ASC LIMIT 1;

COMMIT;
