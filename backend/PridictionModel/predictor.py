"""
predictor.py  —  Patient Influx & Capacity Prediction SDK
══════════════════════════════════════════════════════════
Simple Python functions — no command line, no HTTP, no config files.
Import this file and call functions directly from your own code.

Quick start:
    from predictor import train, predict, forecast, capacity_report

    train("data/patients.csv")
    result = predict("2025-08-15")
    print(result.patients)          # 42
    print(result.bor_projected)     # 76.3  (% bed occupancy)
    print(result.wait_consultation) # 28    (minutes)
    print(result.alerts)            # ["counter_overload"]

Full example at the bottom of this file.
"""

import warnings
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional, Union

warnings.filterwarnings("ignore")

# ── Import the core engine ─────────────────────────────────────
import core


# ══════════════════════════════════════════════════════════════
# RESULT OBJECTS  — dot-access to every output value
# ══════════════════════════════════════════════════════════════

class PredictionResult:
    """
    Returned by predict() and each item in forecast().
    Access any field with dot notation.

    Prediction
    ──────────
    .date               str     "YYYY-MM-DD"
    .specialty          str     specialty / facility name
    .patients           int     predicted patient count
    .low                int     lower bound
    .high               int     upper bound
    .confidence         float   model confidence %
    .model_used         str     algorithm name (GBM / RF / DT / etc.)

    Bed Occupancy (IPD)
    ───────────────────
    .bor_current        float   current bed occupancy rate %
    .bor_projected      float   projected BOR % after today's admissions
    .beds_total         int     total sanctioned beds
    .beds_occupied_now  int     beds occupied right now
    .beds_new_admits    int     new admissions expected today
    .beds_free_after    int     beds available after admissions
    .bor_status         str     "target" / "low" / "critical" / "very_low"
    .bor_over_capacity  bool    True if projected occupancy exceeds total

    OPD Load
    ────────
    .opd_pts_per_hour       float   total patients per hour
    .opd_load_per_counter   float   patients per hour per counter
    .opd_load_per_doctor    float   patients per doctor today
    .opd_counters_needed    int     counters required
    .opd_counters_available int     counters you have
    .opd_doctors_needed     int     doctors required
    .opd_doctors_available  int     doctors you have
    .opd_counter_status     str     "ok" / "over" / "low"
    .opd_doctor_status      str     "ok" / "warn" / "over"

    Emergency Department
    ────────────────────
    .ed_util_pct            float   ED utilisation %
    .ed_occupied_now        int     ED beds occupied now
    .ed_new_patients        int     new ED arrivals expected
    .ed_opd_transfers       int     transfers from OPD
    .ed_direct_walkins      int     direct ED walk-ins
    .ed_triage_immediate    int     immediate priority patients
    .ed_triage_urgent       int     urgent priority patients
    .ed_triage_non_urgent   int     non-urgent patients
    .ed_status              str     "normal" / "moderate" / "high" / "critical"

    Waiting Times (minutes)
    ───────────────────────
    .wait_transport         int
    .wait_registration      int
    .wait_triage            int
    .wait_consultation      int     ← main bottleneck
    .wait_pharmacy          int
    .wait_billing           int
    .wait_total             int     total visit duration

    Alerts
    ──────
    .alerts         list[str]   list of alert codes  e.g. ["ed_critical"]
    .alert_messages list[str]   list of human-readable alert messages
    .has_danger     bool        True if any alert is danger level
    .has_warning    bool        True if any alert is warning level
    """

    def __init__(self, raw: dict):
        self._raw = raw
        p   = raw.get("prediction", {})
        b   = raw.get("bed_occupancy", {})
        o   = raw.get("opd_load", {})
        e   = raw.get("emergency_load", {})
        w   = raw.get("waiting_times", {})
        als = raw.get("alerts", [])

        # Prediction
        self.date               = p.get("date")
        self.specialty          = p.get("facility", "all")
        self.patients           = p.get("predicted")
        self.low                = p.get("low")
        self.high               = p.get("high")
        self.confidence         = p.get("confidence_pct")
        self.model_used         = p.get("model_used")

        # Bed occupancy
        self.bor_current        = b.get("current_bor_pct")
        self.bor_projected      = b.get("projected_bor_pct")
        self.beds_total         = b.get("total_beds")
        self.beds_occupied_now  = b.get("current_occupied")
        self.beds_new_admits    = b.get("new_admissions")
        self.beds_free_after    = b.get("beds_free_after")
        self.bor_status         = b.get("status")
        self.bor_over_capacity  = b.get("over_capacity", False)

        # OPD load
        self.opd_pts_per_hour       = o.get("patients_per_hour")
        self.opd_load_per_counter   = o.get("patients_per_hr_per_ctr")
        self.opd_load_per_doctor    = o.get("patients_per_doctor")
        self.opd_counters_needed    = o.get("counters_needed")
        self.opd_counters_available = o.get("counters_available")
        self.opd_doctors_needed     = o.get("doctors_needed")
        self.opd_doctors_available  = o.get("doctors_available")
        self.opd_counter_status     = o.get("counter_status")
        self.opd_doctor_status      = o.get("doctor_status")

        # Emergency
        self.ed_util_pct         = e.get("utilisation_pct")
        self.ed_occupied_now     = e.get("ed_occupied_now")
        self.ed_new_patients     = e.get("new_ed_patients")
        self.ed_opd_transfers    = e.get("opd_transfers")
        self.ed_direct_walkins   = e.get("direct_walkins")
        self.ed_triage_immediate = e.get("triage_immediate")
        self.ed_triage_urgent    = e.get("triage_urgent")
        self.ed_triage_non_urgent= e.get("triage_non_urgent")
        self.ed_status           = e.get("status")

        # Waiting times
        self.wait_transport     = w.get("transport")
        self.wait_registration  = w.get("registration")
        self.wait_triage        = w.get("triage")
        self.wait_consultation  = w.get("consultation")
        self.wait_pharmacy      = w.get("pharmacy")
        self.wait_billing       = w.get("billing")
        self.wait_total         = w.get("total")

        # Alerts
        self.alerts         = [a["code"] for a in als]
        self.alert_messages = [a["message"] for a in als]
        self.has_danger     = any(a["level"] == "danger"  for a in als)
        self.has_warning    = any(a["level"] == "warning" for a in als)

    def summary(self) -> str:
        """One-line text summary."""
        return (
            f"{self.date} | {self.specialty} | "
            f"Patients: {self.patients} ({self.low}–{self.high}) | "
            f"BOR: {self.bor_projected}% | "
            f"ED: {self.ed_util_pct}% | "
            f"Wait: {self.wait_total}min"
        )

    def to_dict(self) -> dict:
        """Return the raw underlying dict."""
        return self._raw

    def __repr__(self):
        return (
            f"PredictionResult("
            f"date={self.date!r}, "
            f"patients={self.patients}, "
            f"bor={self.bor_projected}%, "
            f"ed={self.ed_util_pct}%, "
            f"wait={self.wait_total}min)"
        )


class TrainingResult:
    """
    Returned by train().

    .session_id         int     which session number this was
    .best_model         str     algorithm that won (GBM / RF / DT / etc.)
    .accuracy           float   accuracy % (100 - MAPE)
    .mae                float   mean absolute error
    .rmse               float   root mean squared error
    .r2                 float   R² score
    .total_rows         int     rows used to train (after merge + date filter)
    .specialties        list    specialties found in the data
    .training_time_sec  float   seconds taken
    .gpu_used           str     GPU name or "none"
    .all_models         dict    {model_name: {mae, rmse, mape, r2, accuracy}}
    .routing            dict    per-specialty model selection info
    """
    def __init__(self, raw: dict):
        self._raw           = raw
        self.session_id     = raw.get("session_id")
        self.best_model     = raw.get("best_model")
        self.accuracy       = round(100 - raw.get("best_mape", 0), 1)
        self.mae            = raw.get("best_mae")
        self.rmse           = raw.get("best_rmse")
        self.r2             = raw.get("best_r2")
        self.total_rows     = raw.get("total_rows")
        self.specialties    = raw.get("facilities", [])
        self.training_time_sec = raw.get("training_time_sec")
        self.gpu_used       = raw.get("gpu_used", "none")
        self.all_models     = raw.get("all_results", {})
        self.routing        = raw.get("spec_info", {})

    def __repr__(self):
        return (
            f"TrainingResult("
            f"session={self.session_id}, "
            f"best={self.best_model}, "
            f"accuracy={self.accuracy}%, "
            f"mae={self.mae}, "
            f"rows={self.total_rows:,})"
        )


class StorageInfo:
    """
    Returned by storage().

    .total_size_mb      float
    .file_count         int
    .session_count      int
    .total_rows         int
    .files              list[dict]   each file: path, size_kb, modified
    .database_used      bool         always False
    """
    def __init__(self, raw: dict):
        self._raw          = raw
        self.total_size_mb = raw.get("total_size_mb")
        self.file_count    = raw.get("file_count")
        self.session_count = raw.get("session_count")
        self.total_rows    = raw.get("total_data_rows")
        self.files         = raw.get("files", [])
        self.database_used = raw.get("database_used", False)

    def __repr__(self):
        return (
            f"StorageInfo("
            f"sessions={self.session_count}, "
            f"rows={self.total_rows:,}, "
            f"size={self.total_size_mb}MB, "
            f"files={self.file_count})"
        )


# ══════════════════════════════════════════════════════════════
# DATE HELPER
# ══════════════════════════════════════════════════════════════

def _date_str(d) -> str:
    """Accept date, datetime, or string and return 'YYYY-MM-DD'."""
    if isinstance(d, (date, datetime)):
        return d.strftime("%Y-%m-%d")
    if isinstance(d, str):
        # Validate and normalise
        import pandas as pd
        return pd.to_datetime(d).strftime("%Y-%m-%d")
    raise TypeError(f"date must be str, date, or datetime — got {type(d)}")


# ══════════════════════════════════════════════════════════════
# TRAINING
# ══════════════════════════════════════════════════════════════

def train(
    csv_file:    str,
    *,
    retrain:     bool = False,
    from_date:   Optional[Union[str, date]] = None,
    to_date:     Optional[Union[str, date]] = None,
    climate:     str  = "semi_arid",
    cpu_cores:   int  = -1,
    total_beds:  Optional[int]   = None,
    beds_occupied: Optional[int] = None,
    opd_hours:   Optional[float] = None,
    ed_beds:     Optional[int]   = None,
    ed_occupied: Optional[int]   = None,
    admit_rate:  Optional[float] = None,
    ed_rate:     Optional[float] = None,
    doctors:     Optional[int]   = None,
    counters:    Optional[int]   = None,
    walk_in_pct: Optional[float] = None,
) -> TrainingResult:
    """
    Train the prediction model on your CSV data.

    Parameters
    ──────────
    csv_file      Path to your CSV file.
                  Required columns: date, patients
                  Optional: specialty, temperature, aqi, rainfall,
                            holiday, revisit, doctors, counters, hour

    retrain       If True, merges new data with all previous training
                  sessions before fitting. Each session is remembered
                  permanently so accuracy improves over time.
                  Default: False (train only on this CSV)

    from_date     Only use rows on or after this date.
                  Accepts "2023-06-01", date(2023,6,1), or datetime.

    to_date       Only use rows on or before this date.

    climate       Seasonal prior profile for your region.
                  "semi_arid" (default) | "tropical" | "temperate"
                  | "cold" | "equatorial"
                  Your actual data overrides this once enough months
                  are covered.

    cpu_cores     Number of CPU cores to use. -1 means all.

    total_beds    Total sanctioned IPD beds at your facility.
    beds_occupied Beds occupied right now (snapshot).
    opd_hours     OPD operating hours per day (default 6).
    ed_beds       Emergency department bed capacity.
    ed_occupied   ED beds occupied right now.
    admit_rate    % of OPD patients admitted to IPD (default 8).
    ed_rate       % of OPD patients transferred to ED (default 3).
    doctors       Average doctors on duty.
    counters      Registration counters open.
    walk_in_pct   % of patients arriving as walk-ins (default 36).

    Returns
    ───────
    TrainingResult  with .best_model, .accuracy, .mae, .specialties, etc.

    Examples
    ────────
    # Minimal
    result = train("data/patients.csv")

    # With incremental memory and date filter
    result = train("data/june.csv", retrain=True,
                   from_date="2024-06-01", to_date="2024-06-30")

    # With your facility's bed setup
    result = train("data/patients.csv",
                   total_beds=150, beds_occupied=110,
                   ed_beds=30, doctors=8)
    """
    if not Path(csv_file).exists():
        raise FileNotFoundError(f"CSV file not found: {csv_file}")

    cap = {}
    if total_beds   is not None: cap["totalBeds"]    = total_beds
    if beds_occupied is not None: cap["bedsOccupied"] = beds_occupied
    if opd_hours    is not None: cap["opdHrs"]        = opd_hours
    if ed_beds      is not None: cap["edBeds"]        = ed_beds
    if ed_occupied  is not None: cap["edOccupied"]    = ed_occupied
    if admit_rate   is not None: cap["admitRate"]     = admit_rate
    if ed_rate      is not None: cap["edRate"]        = ed_rate
    if doctors      is not None: cap["doctors"]       = doctors
    if counters     is not None: cap["counters"]      = counters
    if walk_in_pct  is not None: cap["walkInPct"]     = walk_in_pct

    stats = core.run_training(
        csv_path  = csv_file,
        retrain   = retrain,
        climate   = climate,
        n_jobs    = cpu_cores,
        cap       = cap,
        from_date = _date_str(from_date) if from_date else None,
        to_date   = _date_str(to_date)   if to_date   else None,
    )
    return TrainingResult(stats)


# ══════════════════════════════════════════════════════════════
# PREDICTION
# ══════════════════════════════════════════════════════════════

def predict(
    date:           Union[str, "date", datetime] = None,
    *,
    specialty:      str   = "all",
    season:         str   = "auto",
    # Environmental conditions
    temperature:    Optional[float] = None,
    aqi:            Optional[float] = None,
    rainfall:       Optional[float] = None,
    humidity:       Optional[float] = None,
    hour:           Optional[float] = None,
    holiday:        Optional[int]   = None,
    staffing_pct:   Optional[float] = None,
    lagged:         Optional[float] = None,
    revisit_pct:    Optional[float] = None,
    # Events
    events:         Optional[List[str]] = None,
    # Capacity
    total_beds:     Optional[int]   = None,
    beds_occupied:  Optional[int]   = None,
    opd_hours:      Optional[float] = None,
    ed_beds:        Optional[int]   = None,
    ed_occupied:    Optional[int]   = None,
    admit_rate:     Optional[float] = None,
    ed_rate:        Optional[float] = None,
    doctors:        Optional[int]   = None,
    counters:       Optional[int]   = None,
    walk_in_pct:    Optional[float] = None,
) -> PredictionResult:
    """
    Predict patient count and capacity status for one date.

    Parameters
    ──────────
    date          Date to predict for.
                  Accepts "2025-08-15", date(2025,8,15), or datetime.
                  Default: today.

    specialty     Which specialty to predict for.
                  Use the exact name from your training data, or "all".
                  Default: "all"

    season        Override the seasonal multiplier.
                  "auto"  — uses learned month pattern (recommended)
                  "peak"  — × 1.18  (hot/busy season)
                  "off"   — × 0.88  (quiet season)
                  "rain"  — × 1.04  (monsoon/rainy)
                  "cold"  — × 1.10  (cold season)

    Environmental conditions (all optional):
      temperature   °C — affects predicted count
                    >39°C: +10% patients. <5°C: +8%
      aqi           Air Quality Index (0–500)
                    >100: +4%. >150: +9%. >200: +18%
      rainfall      mm per day
                    >20mm: −7% footfall. >50mm: −15%
      humidity      % — >85% adds ~5% respiratory load
      hour          0–23 — shifts intraday profile weighting
      holiday       1 = public holiday (applies −28% multiplier)
                    0 = normal day
      staffing_pct  0–100 — scales effective doctors on duty
                    80 means only 80% of normal staff present
      lagged        Yesterday's actual patient count (strong predictor)
      revisit_pct   Returning patients as % of average (default 30)

    events        List of event flags that adjust the prediction.
                  Each event applies a % multiplier:
                  "holiday"       −18%   public holiday
                  "festival"      +13%   festival / mela
                  "heatwave"      +25%   heat wave
                  "flu_peak"      +30%   influenza season peak
                  "rain_heavy"    −14%   heavy rain
                  "long_weekend"  −20%   long weekend
                  "epidemic"      +35%   outbreak / epidemic
                  "mass_event"    +10%   nearby large event
                  Multiple events stack: ["flu_peak","heatwave"]

    Capacity parameters (all optional — uses training defaults):
      total_beds      Total sanctioned IPD beds
      beds_occupied   Beds occupied RIGHT NOW (before predictions)
      opd_hours       OPD operating hours per day
      ed_beds         Emergency department bed capacity
      ed_occupied     ED beds occupied right now
      admit_rate      % of OPD patients admitted to IPD
      ed_rate         % of OPD patients transferred to ED
      doctors         Doctors on duty today
      counters        Registration counters open
      walk_in_pct     % of patients arriving as walk-ins

    Returns
    ───────
    PredictionResult  — dot-access to every field.

    Examples
    ────────
    # Minimal — predict today
    r = predict()
    print(r.patients, r.bor_projected, r.wait_total)

    # Specific date with conditions
    r = predict("2025-08-15",
                temperature=38, aqi=145, staffing_pct=85)

    # With events and bed snapshot
    r = predict("2025-12-25",
                holiday=1, events=["epidemic"],
                total_beds=150, beds_occupied=130)

    # Check alerts
    r = predict("2025-08-15")
    if r.has_danger:
        print("Danger:", r.alert_messages)
    """
    target = _date_str(date) if date else datetime.now().strftime("%Y-%m-%d")

    env = {}
    if temperature  is not None: env["temperature"]  = temperature
    if aqi          is not None: env["aqi"]           = aqi
    if rainfall     is not None: env["rainfall"]      = rainfall
    if humidity     is not None: env["humidity"]      = humidity
    if hour         is not None: env["hour"]          = hour
    if holiday      is not None: env["holiday"]       = holiday
    if staffing_pct is not None: env["staffing_pct"]  = staffing_pct
    if lagged       is not None: env["lagged"]        = lagged
    if revisit_pct  is not None: env["revisit_pct"]   = revisit_pct

    cap = {}
    if total_beds    is not None: cap["totalBeds"]    = total_beds
    if beds_occupied is not None: cap["bedsOccupied"] = beds_occupied
    if opd_hours     is not None: cap["opdHrs"]       = opd_hours
    if ed_beds       is not None: cap["edBeds"]       = ed_beds
    if ed_occupied   is not None: cap["edOccupied"]   = ed_occupied
    if admit_rate    is not None: cap["admitRate"]     = admit_rate
    if ed_rate       is not None: cap["edRate"]        = ed_rate
    if doctors       is not None: cap["doctors"]       = doctors
    if counters      is not None: cap["counters"]      = counters
    if walk_in_pct   is not None: cap["walkInPct"]    = walk_in_pct

    raw = core.predict_one(
        date_str     = target,
        facility     = specialty,
        season       = season,
        env          = env or None,
        cap_override = cap or None,
        events       = events or [],
    )
    return PredictionResult(raw)


# ══════════════════════════════════════════════════════════════
# FORECAST
# ══════════════════════════════════════════════════════════════

def forecast(
    days:           int  = 30,
    *,
    start:          Union[str, "date", datetime] = None,
    specialty:      str   = "all",
    season:         str   = "auto",
    # Environmental conditions (applied to every day)
    temperature:    Optional[float] = None,
    aqi:            Optional[float] = None,
    rainfall:       Optional[float] = None,
    humidity:       Optional[float] = None,
    staffing_pct:   Optional[float] = None,
    events:         Optional[List[str]] = None,
    # Capacity
    total_beds:     Optional[int]   = None,
    beds_occupied:  Optional[int]   = None,
    opd_hours:      Optional[float] = None,
    ed_beds:        Optional[int]   = None,
    ed_occupied:    Optional[int]   = None,
    admit_rate:     Optional[float] = None,
    ed_rate:        Optional[float] = None,
    doctors:        Optional[int]   = None,
    counters:       Optional[int]   = None,
    walk_in_pct:    Optional[float] = None,
) -> List[PredictionResult]:
    """
    Generate a multi-day forecast.

    Parameters
    ──────────
    days          Number of days to forecast. Default: 30. Max: 365.

    start         First date of the forecast.
                  Default: today.

    specialty     Specialty to forecast for, or "all".

    season        "auto" | "peak" | "off" | "rain" | "cold"

    Environmental conditions applied uniformly to all forecast days:
      temperature, aqi, rainfall, humidity, staffing_pct

    events        Event flags applied to every day in the forecast.
                  (For day-specific events use predict() in a loop.)

    Capacity parameters: same as predict().

    Returns
    ───────
    list[PredictionResult]  — one entry per day, same dot-access fields.

    Examples
    ────────
    # 30-day forecast from today
    days = forecast(30)
    for d in days:
        print(d.date, d.patients, d.bor_projected)

    # Forecast during monsoon season
    days = forecast(14, temperature=29, rainfall=35, aqi=90)

    # Staff shortage scenario
    days = forecast(7, start="2025-09-01", staffing_pct=70)

    # Find days with danger alerts
    days = forecast(30)
    critical = [d for d in days if d.has_danger]
    """
    start_str = _date_str(start) if start else None

    env = {}
    if temperature  is not None: env["temperature"]  = temperature
    if aqi          is not None: env["aqi"]           = aqi
    if rainfall     is not None: env["rainfall"]      = rainfall
    if humidity     is not None: env["humidity"]      = humidity
    if staffing_pct is not None: env["staffing_pct"]  = staffing_pct

    cap = {}
    if total_beds    is not None: cap["totalBeds"]    = total_beds
    if beds_occupied is not None: cap["bedsOccupied"] = beds_occupied
    if opd_hours     is not None: cap["opdHrs"]       = opd_hours
    if ed_beds       is not None: cap["edBeds"]       = ed_beds
    if ed_occupied   is not None: cap["edOccupied"]   = ed_occupied
    if admit_rate    is not None: cap["admitRate"]     = admit_rate
    if ed_rate       is not None: cap["edRate"]        = ed_rate
    if doctors       is not None: cap["doctors"]       = doctors
    if counters      is not None: cap["counters"]      = counters
    if walk_in_pct   is not None: cap["walkInPct"]    = walk_in_pct

    raw_list = core.forecast_range(
        days         = days,
        facility     = specialty,
        start        = start_str,
        env          = env or None,
        cap_override = cap or None,
        events       = events or [],
    )
    return [PredictionResult(r) for r in raw_list]


# ══════════════════════════════════════════════════════════════
# CAPACITY REPORT
# ══════════════════════════════════════════════════════════════

def capacity_report(
    date:           Union[str, "date", datetime] = None,
    *,
    specialty:      str   = "all",
    total_beds:     Optional[int]   = None,
    beds_occupied:  Optional[int]   = None,
    opd_hours:      Optional[float] = None,
    ed_beds:        Optional[int]   = None,
    ed_occupied:    Optional[int]   = None,
    admit_rate:     Optional[float] = None,
    ed_rate:        Optional[float] = None,
    doctors:        Optional[int]   = None,
    counters:       Optional[int]   = None,
    walk_in_pct:    Optional[float] = None,
    staffing_pct:   Optional[float] = None,
    temperature:    Optional[float] = None,
    aqi:            Optional[float] = None,
) -> PredictionResult:
    """
    Full capacity report for a date (shortcut for predict with capacity focus).

    Same as predict() but defaults to today and is named to make
    the intent obvious when you just want the capacity breakdown.

    Example
    ───────
    report = capacity_report(
        total_beds=150, beds_occupied=112,
        ed_beds=30, ed_occupied=22,
        doctors=7, counters=4
    )
    print(f"BOR: {report.bor_projected}%")
    print(f"ED: {report.ed_util_pct}%")
    print(f"Wait: {report.wait_total} min")
    """
    return predict(
        date,
        specialty     = specialty,
        total_beds    = total_beds,
        beds_occupied = beds_occupied,
        opd_hours     = opd_hours,
        ed_beds       = ed_beds,
        ed_occupied   = ed_occupied,
        admit_rate    = admit_rate,
        ed_rate       = ed_rate,
        doctors       = doctors,
        counters      = counters,
        walk_in_pct   = walk_in_pct,
        staffing_pct  = staffing_pct,
        temperature   = temperature,
        aqi           = aqi,
    )


# ══════════════════════════════════════════════════════════════
# DATA QUERIES
# ══════════════════════════════════════════════════════════════

def get_data(
    from_date:  Union[str, "date", datetime] = None,
    to_date:    Union[str, "date", datetime] = None,
    specialty:  Optional[str] = None,
    summary:    bool = True,
) -> dict:
    """
    Query stored training data.

    Parameters
    ──────────
    from_date   Start of date range (inclusive).
    to_date     End of date range (inclusive).
    specialty   Filter to one specialty. None = all.
    summary     True  = one row per day with totals (default)
                False = every individual stored row

    Returns
    ───────
    dict with keys:
      "rows"      int            number of records returned
      "summary"   dict           overall stats (mean, max, min, etc.)
      "data"      list[dict]     the records

    Example
    ───────
    d = get_data(from_date="2023-06-01", to_date="2023-06-30")
    print(d["summary"]["avg_daily"])
    for row in d["data"]:
        print(row["date"], row["total_patients"])
    """
    return core.get_data_range(
        from_date = _date_str(from_date) if from_date else None,
        to_date   = _date_str(to_date)   if to_date   else None,
        facility  = specialty,
        summary   = summary,
    )


def get_data_for_date(
    date:       Union[str, "date", datetime],
    specialty:  Optional[str] = None,
) -> dict:
    """
    Get all stored rows for one specific date, plus the model prediction.

    Useful for comparing actual vs predicted on historical dates.

    Returns
    ───────
    dict with keys:
      "date"         str
      "stored_rows"  int            how many rows exist for this date
      "actual_data"  list[dict]     what was actually recorded
      "prediction"   PredictionResult-compatible dict

    Example
    ───────
    d = get_data_for_date("2023-07-15")
    print("Stored rows:", d["stored_rows"])
    for row in d["actual_data"]:
        print(row["specialty"], row["patients"])
    print("Predicted:", d["prediction"]["prediction"]["predicted"])
    """
    return core.get_data_for_date(
        date_str = _date_str(date),
        facility = specialty,
    )


def export_data(
    output_file:  Optional[str] = None,
    from_date:    Union[str, "date", datetime] = None,
    to_date:      Union[str, "date", datetime] = None,
    specialty:    Optional[str] = None,
) -> str:
    """
    Export stored training data to a CSV file.

    Parameters
    ──────────
    output_file   Path to save to. Auto-generated in exports/ if None.
    from_date     Only export rows from this date onward.
    to_date       Only export rows up to this date.
    specialty     Only export rows for this specialty.

    Returns
    ───────
    str   Path of the saved CSV file.

    Example
    ───────
    path = export_data(from_date="2023-01-01", to_date="2023-06-30")
    print("Saved to:", path)
    """
    return core.export_all_data(
        out_path  = output_file,
        facility  = specialty,
        from_date = _date_str(from_date) if from_date else None,
        to_date   = _date_str(to_date)   if to_date   else None,
    )


# ══════════════════════════════════════════════════════════════
# SYSTEM INFO
# ══════════════════════════════════════════════════════════════

def status() -> dict:
    """
    Return training memory status.

    dict with:
      sessions          int    number of training sessions
      total_rows        int    total training rows in memory
      date_range        dict   {"first": "...", "last": "..."}
      specialties       list   specialties trained on
      model_ready       bool   whether a model is available to predict
      training_history  list   last 10 sessions with accuracy etc.
      model_info        dict   current model accuracy, best model, etc.
      device            dict   CPU cores, GPU name

    Example
    ───────
    s = status()
    print(f"Trained on {s['total_rows']:,} rows")
    print(f"Best model: {s['model_info']['best_model']}")
    print(f"Accuracy: {s['model_info']['accuracy_pct']}%")
    """
    return core.get_status()


def storage() -> StorageInfo:
    """
    Show all local storage files (no database used).

    Example
    ───────
    s = storage()
    print(f"Total size: {s.total_size_mb} MB")
    print(f"Database used: {s.database_used}")   # always False
    for f in s.files:
        print(f["path"], f["size_kb"], "KB")
    """
    return StorageInfo(core.get_storage_info())


def model_info() -> dict:
    """
    Return detailed model information.

    dict with:
      best_model            str
      accuracy_pct          float
      mae, rmse, r2         floats
      all_model_results     dict  per-algorithm scores
      spec_routing          dict  per-specialty model selection
      feature_importance    dict  which features matter most
      cap_defaults          dict  stored capacity defaults

    Example
    ───────
    info = model_info()
    print(info["best_model"], info["accuracy_pct"])
    for name, scores in info["all_model_results"].items():
        print(f"{name}: MAE={scores['mae']}")
    """
    return core.get_model_info()


def clear_all_data() -> dict:
    """
    Wipe all training memory, session CSV files, and model files.
    The model will need to be retrained after calling this.

    Returns dict with cleared_files count.

    Example
    ───────
    result = clear_all_data()
    print(f"Cleared {result['cleared_files']} files")
    """
    return core.clear_memory()


# ══════════════════════════════════════════════════════════════
# CONVENIENCE EXPORTS
# ══════════════════════════════════════════════════════════════

__all__ = [
    # Training
    "train",
    # Prediction
    "predict",
    "forecast",
    "capacity_report",
    # Data
    "get_data",
    "get_data_for_date",
    "export_data",
    # System
    "status",
    "storage",
    "model_info",
    "clear_all_data",
    # Result classes (for type hints)
    "PredictionResult",
    "TrainingResult",
    "StorageInfo",
]


# ══════════════════════════════════════════════════════════════
# EXAMPLE  — run this file directly to see a full demo
# ══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    from datetime import date

    print("=" * 60)
    print("  Patient Influx Prediction SDK — Demo")
    print("=" * 60)

    # ── 1. Train ───────────────────────────────────────────────
    print("\n1. Training on demo dataset...")
    result = train(
        "data/demo.csv",
        total_beds=150,
        beds_occupied=108,
        ed_beds=25,
        doctors=5,
        counters=3,
    )
    print(f"   Best model : {result.best_model}")
    print(f"   Accuracy   : {result.accuracy}%")
    print(f"   MAE        : {result.mae}")
    print(f"   Specialties: {result.specialties}")

    # ── 2. Predict today ───────────────────────────────────────
    print("\n2. Predicting today...")
    r = predict()
    print(f"   {r.summary()}")

    # ── 3. Predict with conditions ─────────────────────────────
    print("\n3. Predicting 2025-08-15 with hot/high-AQI day...")
    r = predict(
        "2025-08-15",
        specialty    = "General Medicine",
        temperature  = 38,
        aqi          = 155,
        staffing_pct = 85,
        lagged       = 52,
        events       = ["flu_peak"],
        total_beds   = 150,
        beds_occupied= 110,
    )
    print(f"   Patients        : {r.patients} ({r.low}–{r.high})")
    print(f"   Confidence      : {r.confidence}%")
    print(f"   Model           : {r.model_used}")
    print(f"   BOR now→after   : {r.bor_current}% → {r.bor_projected}%")
    print(f"   New admissions  : {r.beds_new_admits}")
    print(f"   Free beds after : {r.beds_free_after}")
    print(f"   ED utilisation  : {r.ed_util_pct}%")
    print(f"   ED status       : {r.ed_status}")
    print(f"   Wait total      : {r.wait_total} min")
    print(f"   Wait consult    : {r.wait_consultation} min")
    if r.alerts:
        print(f"   Alerts          : {r.alerts}")

    # ── 4. Forecast ────────────────────────────────────────────
    print("\n4. 7-day forecast...")
    days = forecast(7, start="2025-08-15", temperature=36, aqi=110)
    print(f"   {'Date':<13} {'Patients':>8} {'BOR%':>7} {'ED%':>6} {'Wait':>6}")
    print(f"   {'-'*44}")
    for d in days:
        print(f"   {d.date:<13} {d.patients:>8} "
              f"{d.bor_projected:>6.1f}% "
              f"{d.ed_util_pct:>5.1f}% "
              f"{d.wait_total:>5}min")

    # ── 5. Capacity report ─────────────────────────────────────
    print("\n5. Capacity report for today...")
    cr = capacity_report(
        total_beds    = 200,
        beds_occupied = 158,
        ed_beds       = 30,
        ed_occupied   = 22,
        doctors       = 8,
        counters      = 5,
    )
    print(f"   BOR projected  : {cr.bor_projected}%  ({cr.bor_status})")
    print(f"   Counters needed: {cr.opd_counters_needed}")
    print(f"   ED status      : {cr.ed_status}")
    print(f"   Total wait     : {cr.wait_total} min")

    # ── 6. Find critical days ──────────────────────────────────
    print("\n6. Finding high-risk days in 30-day forecast...")
    all_days = forecast(30)
    danger  = [d for d in all_days if d.has_danger]
    warning = [d for d in all_days if d.has_warning and not d.has_danger]
    print(f"   Danger  days : {len(danger)}")
    print(f"   Warning days : {len(warning)}")
    if danger:
        print(f"   First danger : {danger[0].date} — {danger[0].alert_messages[0]}")

    # ── 7. Data query ──────────────────────────────────────────
    print("\n7. Querying stored data...")
    d = get_data(from_date="2023-01-01", to_date="2023-01-07")
    print(f"   First week Jan 2023:")
    print(f"   Days: {d['summary']['days_with_data']}  "
          f"Total patients: {d['summary']['total_patients']:,}  "
          f"Daily avg: {d['summary']['avg_daily']}")

    # ── 8. System status ───────────────────────────────────────
    print("\n8. System status...")
    s = status()
    print(f"   Sessions : {s['sessions']}")
    print(f"   Rows     : {s['total_rows']:,}")
    print(f"   Model    : {s['model_info'].get('best_model')}  "
          f"acc={s['model_info'].get('accuracy_pct')}%")
    store = storage()
    print(f"   Storage  : {store.total_size_mb}MB  "
          f"{store.file_count} files  "
          f"database={store.database_used}")

    print("\n" + "=" * 60)
    print("  Done. Import predictor.py in your own code:")
    print("  from predictor import train, predict, forecast")
    print("=" * 60)
