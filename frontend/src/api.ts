const BASE = "http://10.97.203.81:8000";

export async function registerHospital(name: string, lat: number, lng: number) {
  const r = await fetch(`${BASE}/api/hospital/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name, lat, lng }),
  });
  return r.json() as Promise<{ id: string }>;
}

export async function updateCapacity(
  hospital_id: string,
  department: string,
  total: number,
  available: number,
) {
  await fetch(`${BASE}/api/hospital/capacity`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hospital_id, department, total, available }),
  });
}

export async function getOpenRequests(department?: string) {
  const url = department
    ? `${BASE}/api/hospital/open-requests?department=${encodeURIComponent(department)}`
    : `${BASE}/api/hospital/open-requests`;
  const r = await fetch(url);
  const rows: any[] = await r.json();
  return rows.map((row) => ({
    id: row[0] as string,
    department: row[1] as string,
    priority: row[2] as string,
    lat: row[3] as number,
    lng: row[4] as number,
    assigned: row[5] as number,
    status: row[6] as string,
  }));
}

export async function respondToPatient(
  patient_id: string,
  hospital_id: string,
  status: "accepted" | "rejected",
) {
  await fetch(`${BASE}/api/hospital/respond`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ patient_id, hospital_id, status }),
  });
}

export async function createPatientRequest(
  department: string,
  priority: string,
  lat: number,
  lng: number,
) {
  const r = await fetch(`${BASE}/api/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ department, priority, lat, lng }),
  });
  return r.json() as Promise<{ patient_id: string }>;
}

export async function getPatientResponses(patient_id: string) {
  const r = await fetch(
    `${BASE}/api/patient/responses?patient_id=${patient_id}`,
  );
  const rows: any[] = await r.json();
  return rows.map((row) => ({
    hospital_id: row[0] as string,
    name: row[1] as string,
    lat: row[2] as number,
    lng: row[3] as number,
  }));
}

export async function selectHospital(patient_id: string, hospital_id: string) {
  const r = await fetch(`${BASE}/api/patient/select`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ patient_id, hospital_id }),
  });
  return r.json() as Promise<{ status: string }>;
}

export async function getHeatmap() {
  const r = await fetch(`${BASE}/api/heatmap`);
  return r.json() as Promise<
    {
      id: string;
      name: string;
      lat: number;
      lng: number;
      total: number;
      available: number;
      demand: number;
    }[]
  >;
}

export async function createResourceRequest(
  hospital_id: string,
  resource_type: string,
  quantity: number,
) {
  const r = await fetch(`${BASE}/api/resource/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hospital_id, resource_type, quantity }),
  });
  return r.json() as Promise<{ request_id: string }>;
}

export async function getOpenResourceRequests() {
  const r = await fetch(`${BASE}/api/resource/open`);
  const rows: any[] = await r.json();
  return rows.map((row) => ({
    id: row[0] as string,
    requester_hospital_id: row[1] as string,
    resource_type: row[2] as string,
    quantity: row[3] as number,
    status: row[4] as string,
    timestamp: row[5] as number,
  }));
}

export async function respondToResource(
  request_id: string,
  hospital_id: string,
  status: "accepted" | "rejected",
) {
  await fetch(`${BASE}/api/resource/respond`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ request_id, hospital_id, status }),
  });
}

export async function getHospitalInfo(hospital_id: string): Promise<{
  id: string;
  name: string;
  location: string;
  short: string;
}> {
  const r = await fetch(`${BASE}/api/hospital/info/${hospital_id}`);
  return r.json();
}

export type SurgeAlert = {
  id: string;
  level: "HIGH" | "MODERATE" | "LOW";
  code: string;
  message: string;
  source: string;
};

export async function getSurgeAlerts(
  hospital_id: string,
): Promise<SurgeAlert[]> {
  const r = await fetch(
    `${BASE}/api/surge-alerts?hospital_id=${encodeURIComponent(hospital_id)}`,
  );
  return r.json();
}

export type ResourcePoolEntry = {
  hospital: string;
  hospital_id: string;
  distance_km: number;
  resources: { type: string; available: number; icon: string }[];
};

export async function getResourcePool(
  hospital_id: string,
): Promise<ResourcePoolEntry[]> {
  const r = await fetch(
    `${BASE}/api/resource/pool?hospital_id=${encodeURIComponent(hospital_id)}`,
  );
  return r.json();
}

export type PredictionResponse = {
  prediction: {
    date: string;
    facility: string;
    predicted: number;
    low: number;
    high: number;
    confidence_pct: number;
    model_used: string;
    ml_blend_pct: number;
    season_used: string;
  };
  bed_occupancy: {
    total_beds: number;
    current_occupied: number;
    new_admissions: number;
    projected_occupied: number;
    beds_free_now: number;
    beds_free_after: number;
    current_bor_pct: number;
    projected_bor_pct: number;
    over_capacity: boolean;
    status: string;
    nhm_target_pct: number;
  };
  opd_load: {
    patients_per_hour: number;
    patients_per_hr_per_ctr: number;
    patients_per_doctor: number;
    counters_available: number;
    counters_needed: number;
    doctors_available: number;
    doctors_needed: number;
    counter_status: string;
    doctor_status: string;
    counter_util_pct: number;
    nhm_ctr_norm_min: number;
    nhm_ctr_norm_max: number;
  };
  emergency_load: {
    ed_beds: number;
    ed_occupied_now: number;
    opd_transfers: number;
    direct_walkins: number;
    new_ed_patients: number;
    projected_occupied: number;
    utilisation_pct: number;
    triage_immediate: number;
    triage_urgent: number;
    triage_non_urgent: number;
    triage_observation: number;
    status: string;
  };
  waiting_times: {
    transport: number;
    registration: number;
    triage: number;
    consultation: number;
    pharmacy: number;
    billing: number;
    total: number;
    bed_delay_mult: number;
    effective_doctors: number;
  };
  alerts: { level: string; code: string; message: string }[];
  inputs_used: {
    cap: {
      doctors: number;
      counters: number;
      totalBeds: number;
      bedsOccupied: number;
      opdHrs: number;
      edBeds: number;
      edOccupied: number;
      admitRate: number;
      edRate: number;
      walkInPct: number;
      phonePct: number;
    };
  };
};

export async function getPrediction(
  date: string,
  hospital_id: string,
): Promise<PredictionResponse> {
  const r = await fetch(`${BASE}/api/hospital/predict`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ hospital_id, date }),
  });
  return r.json();
}

export async function denyResponse(patient_id: string, hospital_id: string) {
  await fetch(`${BASE}/api/patient/deny-response`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ patient_id, hospital_id }),
  });
}

export async function getAcceptanceStatus(
  patient_id: string,
  hospital_id: string,
): Promise<{ status: "pending" | "confirmed" | "denied_by_source" }> {
  const r = await fetch(
    `${BASE}/api/patient/acceptance-status?patient_id=${patient_id}&hospital_id=${hospital_id}`,
  );
  return r.json();
}
