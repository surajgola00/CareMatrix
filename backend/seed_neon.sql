-- CareMatrix Neon MVP seed. Safe to rerun.
CREATE TABLE IF NOT EXISTS hospitals (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  location TEXT NOT NULL,
  lat DOUBLE PRECISION NOT NULL,
  lng DOUBLE PRECISION NOT NULL,
  status TEXT NOT NULL DEFAULT 'offline',
  logo_url TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS capacity (
  hospital_id TEXT NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
  department TEXT NOT NULL,
  total INTEGER NOT NULL CHECK (total >= 0),
  available INTEGER NOT NULL CHECK (available >= 0 AND available <= total),
  PRIMARY KEY (hospital_id, department)
);

CREATE TABLE IF NOT EXISTS resources (
  hospital_id TEXT NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
  resource_type TEXT NOT NULL,
  available INTEGER NOT NULL CHECK (available >= 0),
  PRIMARY KEY (hospital_id, resource_type)
);

INSERT INTO hospitals (id, name, location, lat, lng, status, logo_url)
VALUES
  ('fortis_memorial_gurugram', 'Fortis Memorial Research Institute', 'Sector 44, Gurugram', 28.4595, 77.0726, 'active', '/hospital-logos/fortis_memorial_gurugram.svg'),
  ('max_gurugram', 'Max Hospital Gurugram', 'Sushant Lok I, Gurugram', 28.4597, 77.0835, 'active', '/hospital-logos/max_gurugram.svg'),
  ('paras_gurugram', 'Paras Hospital', 'Sector 43, Gurugram', 28.4494, 77.0847, 'active', '/hospital-logos/paras_gurugram.svg'),
  ('medanta_medicity', 'Medanta - The Medicity', 'Sector 38, Gurugram', 28.4395, 77.0405, 'offline', '/hospital-logos/medanta_medicity.svg'),
  ('artemis_gurugram', 'Artemis Hospital', 'Sector 51, Gurugram', 28.4239, 77.0663, 'active', '/hospital-logos/artemis_gurugram.svg')
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name, location = EXCLUDED.location, lat = EXCLUDED.lat,
  lng = EXCLUDED.lng, status = EXCLUDED.status, logo_url = EXCLUDED.logo_url;

INSERT INTO capacity (hospital_id, department, total, available)
VALUES
  ('fortis_memorial_gurugram', 'Emergency', 20, 6), ('fortis_memorial_gurugram', 'ICU', 30, 4), ('fortis_memorial_gurugram', 'General Medicine', 40, 12),
  ('max_gurugram', 'Emergency', 15, 5), ('max_gurugram', 'ICU', 20, 7), ('max_gurugram', 'General Medicine', 30, 10),
  ('paras_gurugram', 'Emergency', 18, 2), ('paras_gurugram', 'ICU', 24, 3), ('paras_gurugram', 'General Medicine', 35, 8),
  ('medanta_medicity', 'Emergency', 25, 8), ('medanta_medicity', 'ICU', 40, 10), ('medanta_medicity', 'General Medicine', 50, 15),
  ('artemis_gurugram', 'Emergency', 16, 4), ('artemis_gurugram', 'ICU', 28, 6), ('artemis_gurugram', 'General Medicine', 32, 11)
ON CONFLICT (hospital_id, department) DO UPDATE SET total = EXCLUDED.total, available = EXCLUDED.available;

INSERT INTO resources (hospital_id, resource_type, available)
VALUES
  ('fortis_memorial_gurugram', 'Oxygen Cylinders', 24), ('fortis_memorial_gurugram', 'Ventilators', 6), ('fortis_memorial_gurugram', 'Blood Units O+', 18),
  ('max_gurugram', 'Oxygen Cylinders', 18), ('max_gurugram', 'Ventilators', 4), ('max_gurugram', 'Blood Units A+', 14),
  ('paras_gurugram', 'Oxygen Cylinders', 12), ('paras_gurugram', 'Ventilators', 3), ('paras_gurugram', 'Saline Bottles', 80),
  ('medanta_medicity', 'Oxygen Cylinders', 30), ('medanta_medicity', 'Ventilators', 8), ('medanta_medicity', 'Blood Units B+', 20),
  ('artemis_gurugram', 'Oxygen Cylinders', 16), ('artemis_gurugram', 'Ventilators', 5), ('artemis_gurugram', 'Blood Units O-', 10)
ON CONFLICT (hospital_id, resource_type) DO UPDATE SET available = EXCLUDED.available;
