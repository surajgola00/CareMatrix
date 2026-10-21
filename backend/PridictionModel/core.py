"""
core.py  —  Patient Influx & Capacity Prediction Engine
────────────────────────────────────────────────────────
Pure ML engine. No CLI output. No printing.
Imported by both server.py (API) and train.py (CLI).

All public functions return plain Python dicts — safe for
JSON serialisation and direct use in Flask responses.
"""

import hashlib
import json
import logging
import multiprocessing
import subprocess
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.neighbors import KNeighborsRegressor
from sklearn.preprocessing import MinMaxScaler
from sklearn.tree import DecisionTreeRegressor

warnings.filterwarnings("ignore")
log = logging.getLogger("predictor.core")

# ── File paths ────────────────────────────────────────────────
BASE       = Path(__file__).parent
MODELS     = BASE / "models"
DATA       = BASE / "data"
LOGS       = BASE / "logs"
EXP        = BASE / "exports"
MEMORY     = MODELS / "memory.json"
MODEL_PKL  = MODELS / "ensemble.pkl"
STATS_JSON = MODELS / "stats.json"

for _p in [MODELS, DATA, LOGS, EXP]:
    _p.mkdir(parents=True, exist_ok=True)


# ══════════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════════

# Climate seasonal priors (index 0=Jan … 11=Dec)
CLIMATE_PRIORS: dict[str, list] = {
    "semi_arid":  [1.00,0.96,0.93,1.04,1.18,1.22,1.06,0.97,0.93,1.01,1.06,1.08],
    "tropical":   [1.00,0.97,0.95,1.04,1.14,1.08,0.96,0.93,0.92,0.98,1.06,1.08],
    "temperate":  [1.08,1.05,0.98,0.96,0.95,0.97,1.00,0.98,1.02,1.08,1.12,1.14],
    "cold":       [1.18,1.15,1.06,0.95,0.92,0.90,0.88,0.90,0.95,1.05,1.14,1.20],
    "equatorial": [1.00]*12,
}

# Paper-recommended model per specialty (Gupta & Sharma 2025, Table 1)
PAPER_BEST: dict[str, str] = {
    "dental": "RF",          "general medicine": "GBM",
    "ent": "GBM",            "orthopaedic": "RF",
    "emergency": "GBM",      "obstetrics": "RF",
    "paediatrics": "GBM",    "cardiology": "GBM",
    "surgery": "GBM",        "ophthalmology": "RF",
    "dermatology": "GBM",    "psychiatry": "GBM",
}

# NHM / IPHS norms
NHM = {
    "ctr_min": 12,   # patients/hr/counter minimum
    "ctr_max": 20,   # patients/hr/counter maximum
    "opd_hrs": 6,    # standard OPD hours/day
    "bor_target": 80,    # % bed occupancy target
    "doc_ok":   20,      # pts/doctor/day comfortable
    "doc_over": 30,      # pts/doctor/day overloaded
}

# Waiting-time study baselines — Vaishali & Rajan 2017 (minutes)
WAIT_BASE = {
    "transport":    22,
    "registration": 15,
    "triage":        8,
    "consultation": 60,
    "pharmacy":     20,
    "billing":      35,
}

# Season override multipliers
SEASON_MULT = {
    "peak": 1.18, "off": 0.88, "rain": 1.04, "cold": 1.10, "auto": 1.0,
}

# Event impact multipliers
EVENT_IMPACTS = {
    "holiday":    -0.18,
    "festival":   +0.13,
    "heatwave":   +0.25,
    "flu_peak":   +0.30,
    "rain_heavy": -0.14,
    "long_weekend":-0.20,
    "epidemic":   +0.35,
    "mass_event": +0.10,
}

FEAT_NAMES = [
    "day_of_week", "month", "day_of_month", "lagged_arrivals",
    "revisit_rate", "holiday", "hour_of_day", "morning_shift",
    "temperature", "air_quality", "rainfall", "seasonal_prior",
    "doctor_load", "weekend_flag", "peak_month_flag",
    "early_month_flag", "lagged_ratio",
]


# ══════════════════════════════════════════════════════════════
# DEVICE DETECTION
# ══════════════════════════════════════════════════════════════

class DeviceInfo:
    cpu_count: int = 1
    gpu_name:  str = "none"
    gpu_type:  str = "none"
    xgb_gpu:   bool = False
    lgbm_gpu:  bool = False

    def to_dict(self) -> dict:
        return {
            "cpu_count": self.cpu_count,
            "gpu_name":  self.gpu_name,
            "gpu_type":  self.gpu_type,
            "xgb_gpu":   self.xgb_gpu,
            "lgbm_gpu":  self.lgbm_gpu,
        }

def detect_devices() -> DeviceInfo:
    d = DeviceInfo()
    d.cpu_count = multiprocessing.cpu_count()

    try:                                                    # NVIDIA
        r = subprocess.run(
            ["nvidia-smi","--query-gpu=name,memory.total",
             "--format=csv,noheader"],
            capture_output=True, text=True, timeout=5)
        if r.returncode == 0 and r.stdout.strip():
            d.gpu_name = r.stdout.strip().split("\n")[0]
            d.gpu_type = "nvidia"
    except Exception:
        pass

    if d.gpu_type == "none":
        try:                                                # AMD
            r = subprocess.run(["rocm-smi","--showproductname"],
                               capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                lines = [l for l in r.stdout.splitlines() if "GPU" in l]
                d.gpu_name = lines[0].strip() if lines else "AMD ROCm GPU"
                d.gpu_type = "amd"
        except Exception:
            pass

    if d.gpu_type == "none":
        try:                                                # Apple Metal
            import platform
            if platform.system() == "Darwin":
                r = subprocess.run(
                    ["system_profiler","SPDisplaysDataType"],
                    capture_output=True, text=True, timeout=5)
                if "Metal" in r.stdout or "Apple M" in r.stdout:
                    d.gpu_name = "Apple Metal (M-series)"
                    d.gpu_type = "apple"
        except Exception:
            pass

    try:
        import xgboost as _x                               # noqa
        if d.gpu_type in ("nvidia","amd"):
            d.xgb_gpu = True
    except ImportError:
        pass

    try:
        import lightgbm as _l                              # noqa
        if d.gpu_type in ("nvidia","amd"):
            d.lgbm_gpu = True
    except ImportError:
        pass

    return d


# ══════════════════════════════════════════════════════════════
# PERSISTENT MEMORY
# ══════════════════════════════════════════════════════════════

def load_memory() -> dict:
    if MEMORY.exists():
        with open(MEMORY) as f:
            return json.load(f)
    return {
        "sessions": 0, "total_rows": 0,
        "date_range": {"first": None, "last": None},
        "specialties": [], "csv_hashes": [],
        "cumulative_stats": {}, "training_history": [],
        "capacity_defaults": {},
    }

def save_memory(m: dict):
    with open(MEMORY, "w") as f:
        json.dump(m, f, indent=2, default=str)

def file_hash(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()[:12]

def bytes_hash(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()[:12]


# ══════════════════════════════════════════════════════════════
# DATA LOADING
# ══════════════════════════════════════════════════════════════

def _smart_dates(s: pd.Series) -> pd.Series:
    for fmt in ["%Y-%m-%d","%d/%m/%Y","%m/%d/%Y",
                "%d-%m-%Y","%Y/%m/%d","%d %b %Y"]:
        try:
            return pd.to_datetime(s, format=fmt)
        except Exception:
            pass
    return pd.to_datetime(s, infer_datetime_format=True, errors="coerce")

def _find_col(cols_lower: dict, *keys) -> Optional[str]:
    """Return first column whose lowercased name contains any key."""
    for k in keys:
        for cn in cols_lower:
            if k in cn:
                return cols_lower[cn]
    return None

def load_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    return _map_columns(df)

def load_csv_bytes(data: bytes) -> pd.DataFrame:
    import io
    df = pd.read_csv(io.BytesIO(data))
    return _map_columns(df)

def _map_columns(df: pd.DataFrame) -> pd.DataFrame:
    c = {col.lower().strip(): col for col in df.columns}

    dcol  = _find_col(c, "date","day","dt","timestamp","created","visit_date")
    pcol  = _find_col(c, "patient","count","visit","arriv","total",
                         "cases","attend","volume","opd","admission")
    fcol  = _find_col(c, "facilit","spec","dept","site","unit",
                         "depart","clinic","hosp","ward","service")
    hcol  = _find_col(c, "hour","hh","hr","time")
    tcol  = _find_col(c, "temp","celsius","fahrenheit","tmax","tmin")
    acol  = _find_col(c, "aqi","air","pm2","pm10","pollution")
    rcol  = _find_col(c, "rain","precip","mm","rainfall")
    holc  = _find_col(c, "holiday","hol","flag","closed","public")
    revc  = _find_col(c, "revisit","repeat","return","follow","reattend")
    lagc  = _find_col(c, "lag","yesterday","prev","prior","last_day")
    docc  = _find_col(c, "doctor","doc","physician","staff","clinician","md")
    ctrc  = _find_col(c, "counter","window","desk","registration_point")
    bedc  = _find_col(c, "bed_occ","beds_used","occupied_bed","ipd_occ","census")

    if not dcol:
        raise ValueError("No date column. Name it 'date', 'day', etc.")
    if not pcol:
        raise ValueError("No patient count column. Name it 'patients', "
                         "'count', 'visits', etc.")

    def to_num(col):
        return pd.to_numeric(df[col], errors="coerce") if col else np.nan

    df["_date"]     = _smart_dates(df[dcol])
    df["_patients"] = pd.to_numeric(df[pcol], errors="coerce")
    df["_facility"] = df[fcol].astype(str).str.strip() if fcol else "All"
    df["_hour"]     = to_num(hcol)
    df["_temp"]     = to_num(tcol)
    df["_aqi"]      = to_num(acol)
    df["_rain"]     = to_num(rcol)
    df["_holiday"]  = (pd.to_numeric(df[holc], errors="coerce").fillna(0)
                       if holc else 0)
    df["_revisit"]  = to_num(revc)
    df["_lagged"]   = to_num(lagc)
    df["_doctors"]  = to_num(docc)
    df["_counters"] = to_num(ctrc)
    df["_beds_occ"] = to_num(bedc)

    df = (df.dropna(subset=["_date","_patients"])
            .loc[df["_patients"] >= 0]
            .copy())
    df["_patients"] = df["_patients"].round().astype(int)
    df = df.sort_values("_date").reset_index(drop=True)
    df["_lagged"] = (df["_lagged"]
                     .fillna(df["_patients"].shift(1))
                     .fillna(df["_patients"]))

    log.info(f"Loaded {len(df):,} rows, "
             f"{df['_facility'].nunique()} specialties")
    return df


# ══════════════════════════════════════════════════════════════
# FEATURE ENGINEERING  (17 features, paper-backed)
# ══════════════════════════════════════════════════════════════

def engineer_features(df: pd.DataFrame,
                      global_mean: float,
                      climate: str = "semi_arid",
                      cap_doctors: float = 5.0,
                      env_override: Optional[dict] = None) -> np.ndarray:
    """
    Extract 17 features per row.

    env_override (dict) — live values injected by API, override per-row CSV values:
        temperature   float  °C
        aqi           float  Air Quality Index
        rainfall      float  mm
        humidity      float  % (informational, used as AQI modifier)
        hour          float  0-23
        holiday       int    0/1
        staffing_pct  float  0-100 (scales doctor load)
        revisit_pct   float  0-100 (revisit rate as % of mean)
        lagged        float  yesterday's patient count
    """
    env = env_override or {}
    prior = CLIMATE_PRIORS.get(climate, [1.0]*12)
    rows = []

    for _, r in df.iterrows():
        d   = r["_date"]
        dow = int(d.dayofweek)
        mon = int(d.month) - 1
        dom = int(d.day)

        # Apply env_override when provided (API live injection)
        lag  = float(env.get("lagged",
               r["_lagged"] if not pd.isna(r["_lagged"]) else global_mean))
        rev_raw = env.get("revisit_pct")
        rev  = (global_mean * rev_raw / 100 if rev_raw is not None else
                float(r["_revisit"]) if not pd.isna(r["_revisit"])
                else global_mean * 0.3)
        hol  = float(env.get("holiday",
               float(r["_holiday"])))
        hour = float(env.get("hour",
               float(r["_hour"]) if not pd.isna(r["_hour"]) else 12.0))
        morn = 1.0 if (6 <= hour <= 11) else 0.0
        temp = float(env.get("temperature",
               float(r["_temp"]) if not pd.isna(r["_temp"]) else 25.0))
        aqi  = float(env.get("aqi",
               float(r["_aqi"])  if not pd.isna(r["_aqi"])  else 80.0))
        # Humidity can push AQI up slightly (traps pollutants)
        hum  = float(env.get("humidity", 60.0))
        if hum > 85:
            aqi = min(aqi * 1.08, 500)
        rain = float(env.get("rainfall",
               float(r["_rain"]) if not pd.isna(r["_rain"]) else 0.0))
        staff_pct = float(env.get("staffing_pct", 100.0))
        effective_docs = (float(r["_doctors"])
                          if not pd.isna(r["_doctors"]) else cap_doctors)
        effective_docs *= (staff_pct / 100.0)
        pts  = float(r["_patients"])

        rows.append([
            dow / 6,                                           # F0  day-of-week
            mon / 11,                                          # F1  month
            (dom - 1) / 30,                                    # F2  day-of-month ★
            lag / (global_mean or 1),                          # F3  lagged       ★
            rev / (global_mean or 1),                          # F4  revisit      ★
            hol,                                               # F5  holiday
            hour / 23,                                         # F6  hour         ★
            morn,                                              # F7  morning      ★
            (min(max(temp, -20), 55) + 20) / 75,              # F8  temperature
            min(aqi, 500) / 500,                               # F9  AQI
            min(rain, 150) / 150,                              # F10 rainfall
            prior[mon],                                        # F11 seasonal prior
            min(pts / (effective_docs or 1) /
                (cap_doctors * 20), 1),                        # F12 doctor load
            float(dow in [5, 6]),                              # F13 weekend
            float(mon in [4, 5, 10, 11]),                      # F14 peak month
            float(dom <= 7),                                   # F15 early month
            min(lag / (global_mean or 1), 2.0),                # F16 lagged ratio
        ])

    return np.array(rows, dtype=np.float32)


# ══════════════════════════════════════════════════════════════
# MODEL FACTORY
# ══════════════════════════════════════════════════════════════

def build_models(dev: DeviceInfo, n_jobs: int = -1) -> dict:
    mdls = {}

    if dev.xgb_gpu:
        try:
            import xgboost as xgb
            device = "cuda" if dev.gpu_type == "nvidia" else "gpu"
            mdls["GBM"] = xgb.XGBRegressor(
                n_estimators=400, learning_rate=0.06, max_depth=5,
                subsample=0.8, colsample_bytree=0.8, min_child_weight=3,
                device=device, tree_method="hist",
                random_state=42, verbosity=0)
            log.info(f"GBM → XGBoost ({device.upper()})")
        except Exception as e:
            log.warning(f"XGBoost GPU failed: {e}")
            dev.xgb_gpu = False

    if "GBM" not in mdls:
        mdls["GBM"] = GradientBoostingRegressor(
            n_estimators=200, learning_rate=0.08, max_depth=4,
            subsample=0.8, min_samples_leaf=3, random_state=42)

    if dev.lgbm_gpu:
        try:
            import lightgbm as lgbm
            dt = "gpu" if dev.gpu_type in ("nvidia","amd") else "cpu"
            mdls["RF"] = lgbm.LGBMRegressor(
                n_estimators=400, num_leaves=63, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8, min_child_samples=5,
                device_type=dt, random_state=42, verbose=-1)
            log.info(f"RF → LightGBM ({dt.upper()})")
        except Exception as e:
            log.warning(f"LightGBM GPU failed: {e}")
            dev.lgbm_gpu = False

    if "RF" not in mdls:
        mdls["RF"] = RandomForestRegressor(
            n_estimators=300, max_features="sqrt",
            min_samples_leaf=2, n_jobs=n_jobs, random_state=42)

    mdls["KNN"]   = KNeighborsRegressor(n_neighbors=7, weights="distance",
                                        n_jobs=n_jobs)
    mdls["Ridge"] = Ridge(alpha=1.0)
    mdls["DT"]    = DecisionTreeRegressor(max_depth=8, min_samples_leaf=3,
                                          random_state=42)
    return mdls


# ══════════════════════════════════════════════════════════════
# EVALUATION
# ══════════════════════════════════════════════════════════════

def eval_model(mdl, Xte: np.ndarray, yte: np.ndarray,
               name: str) -> dict:
    preds = np.maximum(0, mdl.predict(Xte)).round()
    mae   = float(mean_absolute_error(yte, preds))
    rmse  = float(np.sqrt(mean_squared_error(yte, preds)))
    mape  = float(np.mean(np.abs((yte - preds) / (yte + 1e-6)))) * 100
    r2    = float(r2_score(yte, preds))
    return {
        "name": name, "mae": round(mae, 2), "rmse": round(rmse, 2),
        "mape": round(mape, 2), "r2": round(r2, 4),
        "accuracy": round(max(0.0, 100 - mape), 1),
    }


# ══════════════════════════════════════════════════════════════
# SESSION STORE
# ══════════════════════════════════════════════════════════════

def load_all_sessions() -> pd.DataFrame:
    frames = []
    for p in sorted(DATA.glob("session_*.csv")):
        try:
            frames.append(pd.read_csv(p, low_memory=False))
        except Exception as e:
            log.warning(f"Could not load {p.name}: {e}")
    if frames:
        df = pd.concat(frames, ignore_index=True)
        log.info(f"Loaded {len(df):,} rows from {len(frames)} sessions")
        return df
    return pd.DataFrame()

def save_session(df: pd.DataFrame, sid: int):
    cols = ["_date","_patients","_facility","_hour","_temp","_aqi",
            "_rain","_holiday","_revisit","_lagged","_doctors",
            "_counters","_beds_occ"]
    out = df[[c for c in cols if c in df.columns]].copy()
    out["_date"] = out["_date"].astype(str)
    out.to_csv(DATA / f"session_{sid:04d}.csv", index=False)


# ══════════════════════════════════════════════════════════════
# CAPACITY CALCULATIONS
# ══════════════════════════════════════════════════════════════

def calc_bor(predicted: int, cap: dict) -> dict:
    total   = int(cap.get("totalBeds", 100))
    cur     = int(cap.get("bedsOccupied", round(total * 0.72)))
    ar      = float(cap.get("admitRate", 8)) / 100
    new_adm = round(predicted * ar)
    proj    = min(cur + new_adm, total)
    cur_bor = round(cur / total * 100, 1) if total else 0
    prj_bor = round(proj / total * 100, 1) if total else 0
    status  = ("critical" if prj_bor >= 95 else
               "target"   if prj_bor >= 80 else
               "low"      if prj_bor >= 60 else "very_low")
    return {
        "total_beds":          total,
        "current_occupied":    cur,
        "new_admissions":      new_adm,
        "projected_occupied":  proj,
        "beds_free_now":       total - cur,
        "beds_free_after":     max(0, total - proj),
        "current_bor_pct":     cur_bor,
        "projected_bor_pct":   prj_bor,
        "over_capacity":       (cur + new_adm) > total,
        "status":              status,
        "nhm_target_pct":      NHM["bor_target"],
    }

def calc_opd_load(predicted: int, cap: dict) -> dict:
    hrs   = float(cap.get("opdHrs",    6))
    ctrs  = int(cap.get("counters",    3))
    docs  = int(cap.get("doctors",     5))
    pph   = predicted / hrs
    pphc  = pph / ctrs
    ppd   = predicted / docs
    cneed = int(np.ceil(predicted / (NHM["ctr_max"] * hrs)))
    dneed = int(np.ceil(ppd / NHM["doc_ok"]))
    cst   = ("over" if pphc > NHM["ctr_max"] else
             "ok"   if pphc >= NHM["ctr_min"] else "low")
    dst   = ("over" if ppd > NHM["doc_over"] else
             "warn" if ppd > NHM["doc_ok"]   else "ok")
    return {
        "patients_per_hour":         round(pph, 1),
        "patients_per_hr_per_ctr":   round(pphc, 1),
        "patients_per_doctor":       round(ppd, 1),
        "counters_available":        ctrs,
        "counters_needed":           cneed,
        "doctors_available":         docs,
        "doctors_needed":            dneed,
        "counter_status":            cst,
        "doctor_status":             dst,
        "counter_util_pct":          round(pphc / NHM["ctr_max"] * 100, 1),
        "nhm_ctr_norm_min":          NHM["ctr_min"],
        "nhm_ctr_norm_max":          NHM["ctr_max"],
    }

def calc_ed_load(predicted: int, cap: dict) -> dict:
    eb   = int(cap.get("edBeds",     20))
    eo   = int(cap.get("edOccupied", round(eb * 0.6)))
    er   = float(cap.get("edRate", 3)) / 100
    tr   = round(predicted * er)
    dw   = round(eb * 0.4)
    tot  = tr + dw
    proj = min(eo + tot, eb)
    util = round(proj / eb * 100, 1) if eb else 0
    st   = ("critical" if util >= 95 else
            "high"     if util >= 80 else
            "moderate" if util >= 60 else "normal")
    return {
        "ed_beds":              eb,
        "ed_occupied_now":      eo,
        "opd_transfers":        tr,
        "direct_walkins":       dw,
        "new_ed_patients":      tot,
        "projected_occupied":   proj,
        "utilisation_pct":      util,
        "triage_immediate":     round(tot * 0.05),
        "triage_urgent":        round(tot * 0.25),
        "triage_non_urgent":    round(tot * 0.65),
        "triage_observation":   tot - round(tot*0.05) - round(tot*0.25)
                                    - round(tot*0.65),
        "status":               st,
    }

def calc_wait_times(predicted: int, cap: dict,
                    env: Optional[dict] = None) -> dict:
    hrs   = float(cap.get("opdHrs",   6))
    ctrs  = int(cap.get("counters",   3))
    docs  = int(cap.get("doctors",    5))
    walk  = float(cap.get("walkInPct", 36))
    staff = float((env or {}).get("staffing_pct", 100.0))

    # Effective doctors after staff adjustment
    eff_docs = max(1, round(docs * staff / 100))

    arr  = predicted / hrs
    cl   = arr / ctrs
    dl   = arr / eff_docs

    wm   = (1.30 if walk > 60 else 1.22 if walk > 50 else 1.0)
    bor  = calc_bor(predicted, cap)
    bm   = (1.18 if bor["projected_bor_pct"] > 90 else
            1.08 if bor["projected_bor_pct"] > 80 else 1.0)

    phases = {
        "transport":    max(5,  round(WAIT_BASE["transport"]    * (cl/12) * wm)),
        "registration": max(5,  round(WAIT_BASE["registration"] * (cl/12) * wm)),
        "triage":       max(3,  round(WAIT_BASE["triage"]       * (dl/8))),
        "consultation": max(10, round(WAIT_BASE["consultation"] * (dl/8) * wm * bm)),
        "pharmacy":     max(5,  round(WAIT_BASE["pharmacy"]     * (cl/10))),
        "billing":      max(5,  round(WAIT_BASE["billing"]      * (cl/10))),
    }
    phases["total"]           = sum(phases.values())
    phases["bed_delay_mult"]  = round(bm, 2)
    phases["effective_doctors"] = eff_docs
    return phases


# ══════════════════════════════════════════════════════════════
# TRAINING PIPELINE
# ══════════════════════════════════════════════════════════════

def run_training(csv_path: Optional[str] = None,
                 csv_bytes: Optional[bytes] = None,
                 retrain:   bool = False,
                 climate:   str  = "semi_arid",
                 n_jobs:    int  = -1,
                 cap:       Optional[dict] = None,
                 progress_cb = None,
                 from_date: Optional[str] = None,
                 to_date:   Optional[str] = None) -> dict:
    """
    Train the model ensemble.

    csv_path   — path to CSV file (CLI usage)
    csv_bytes  — raw CSV bytes (API upload usage)
    retrain    — merge with all previous sessions first
    climate    — seasonal prior profile
    n_jobs     — CPU parallelism (-1 = all cores)
    cap        — capacity defaults dict
    progress_cb— optional callable(step, total, message)
    from_date  — only use rows on or after this date "YYYY-MM-DD"
    to_date    — only use rows on or before this date "YYYY-MM-DD"

    Returns stats dict (JSON-safe).
    """
    def _progress(step, total, msg):
        log.info(f"[{step}/{total}] {msg}")
        if progress_cb:
            progress_cb(step, total, msg)

    cap  = cap or {}
    dev  = detect_devices()

    # Load new data
    _progress(1, 6, "Loading CSV data")
    if csv_bytes is not None:
        new_df = load_csv_bytes(csv_bytes)
        chash  = bytes_hash(csv_bytes)
    elif csv_path is not None:
        new_df = load_csv(csv_path)
        chash  = file_hash(csv_path)
    else:
        raise ValueError("Provide csv_path or csv_bytes")

    # Apply date-range filter if requested
    if from_date:
        fd = pd.to_datetime(from_date)
        before = len(new_df)
        new_df = new_df[new_df["_date"] >= fd].copy()
        log.info(f"  Date filter from {from_date}: {before}→{len(new_df)} rows")
    if to_date:
        td = pd.to_datetime(to_date)
        before = len(new_df)
        new_df = new_df[new_df["_date"] <= td].copy()
        log.info(f"  Date filter to   {to_date}: {before}→{len(new_df)} rows")
    if len(new_df) < 10:
        raise ValueError(
            f"Only {len(new_df)} rows after date filter — need at least 10. "
            f"Check --from-date / --to-date.")

    mem = load_memory()

    # Merge with history
    _progress(2, 6, "Merging with training memory")
    if retrain and any(DATA.glob("session_*.csv")):
        hist = load_all_sessions()
        if not hist.empty:
            for col in set(new_df.columns) | set(hist.columns):
                if col not in new_df.columns: new_df[col] = np.nan
                if col not in hist.columns:   hist[col]   = np.nan
            train_df = (pd.concat([hist, new_df], ignore_index=True)
                        .drop_duplicates(subset=["_date","_facility","_patients"])
                        .sort_values("_date").reset_index(drop=True))
            train_df["_lagged"] = (train_df["_patients"].shift(1)
                                   .fillna(train_df["_patients"]))
        else:
            train_df = new_df
    else:
        train_df = new_df

    sid = mem["sessions"] + 1
    save_session(new_df, sid)

    # Compute statistics
    _progress(3, 6, "Computing learned patterns")
    gm  = float(train_df["_patients"].mean())
    gsd = float(train_df["_patients"].std())
    facs= sorted(train_df["_facility"].unique().tolist())

    dow_m = train_df.groupby(train_df["_date"].dt.dayofweek)["_patients"].mean()
    mon_m = train_df.groupby(train_df["_date"].dt.month - 1)["_patients"].mean()
    dom_m = train_df.groupby(train_df["_date"].dt.day - 1)["_patients"].mean()
    hol_s = train_df[train_df["_holiday"] == 1]["_patients"]
    hol_m = float(hol_s.mean()) if len(hol_s) else gm * 0.72
    hol_mult = hol_m / gm

    dowM = {i: float(dow_m.get(i, gm)) / gm for i in range(7)}
    monM = {i: float(mon_m.get(i, gm)) / gm for i in range(12)}
    domM = {i: float(dom_m.get(i, gm)) / gm for i in range(31)}

    n    = len(train_df)
    vals = train_df["_patients"].values.astype(float)
    xm   = (n - 1) / 2.0
    sxy  = np.sum((np.arange(n) - xm) * (vals - gm))
    sxx  = np.sum((np.arange(n) - xm) ** 2)
    slope= sxy / sxx if sxx > 0 else 0.0

    cap_doc = (float(train_df["_doctors"].mean())
               if train_df["_doctors"].notna().any() else 5.0)
    cap_ctr = (float(train_df["_counters"].mean())
               if train_df["_counters"].notna().any() else 3.0)
    avg_bed = (float(train_df["_beds_occ"].mean())
               if "_beds_occ" in train_df
               and train_df["_beds_occ"].notna().any() else None)

    # Feature engineering
    _progress(4, 6, "Engineering features")
    X  = engineer_features(train_df, gm, climate, cap_doc)
    y  = vals
    sc = MinMaxScaler()
    Xs = sc.fit_transform(X)
    cut = int(n * 0.8)
    Xtr, Xte = Xs[:cut], Xs[cut:]
    ytr, yte  = y[:cut],  y[cut:]

    # Train models
    _progress(5, 6, "Training all models")
    mdl_defs = build_models(dev, n_jobs)
    trained  = {}
    results  = []
    t0_all   = time.time()

    for name, mdl in mdl_defs.items():
        t0 = time.time()
        mdl.fit(Xtr, ytr)
        elapsed = time.time() - t0
        ev = eval_model(mdl, Xte, yte, name)
        trained[name] = mdl
        results.append(ev)
        log.info(f"  {name}: MAE={ev['mae']} Acc={ev['accuracy']}% ({elapsed:.1f}s)")

    best = sorted(results, key=lambda r: r["mae"])[0]

    # Per-specialty routing
    _progress(6, 6, "Per-specialty model selection")
    spec_info = {}
    spec_best = {}

    for fac in facs:
        fdf   = train_df[train_df["_facility"] == fac]
        paper = PAPER_BEST.get(fac.lower().strip())
        nf    = len(fdf)

        if nf >= 20:
            Xf = sc.transform(
                engineer_features(fdf, gm, climate, cap_doc))
            yf = fdf["_patients"].values.astype(float)
            cf = int(len(yf) * 0.8)
            if cf >= 5 and len(yf) - cf >= 3:
                fe = {nm: eval_model(trained[nm], Xf[cf:], yf[cf:], nm)
                      for nm in trained}
                winner  = sorted(fe.values(), key=lambda x: x["mae"])[0]["name"]
                method  = "data_verified" if paper else "data_selected"
                mae_all = {k: round(v["mae"], 2) for k, v in fe.items()}
            else:
                winner, method, mae_all = (
                    paper or best["name"], "paper_prior_small_cv", {})
        elif nf >= 5:
            winner, method, mae_all = (
                paper or best["name"], f"paper_prior_{nf}_rows", {})
        else:
            winner, method, mae_all = (
                best["name"], f"generalised_{nf}_rows", {})

        spec_best[fac] = winner
        spec_info[fac] = {
            "rows": nf, "used_model": winner,
            "is_known_specialty": bool(paper),
            "paper_prior": paper, "method": method,
            "all_mae": mae_all,
        }

    # Feature importance
    rf     = trained.get("RF")
    fi_raw = (rf.feature_importances_
              if hasattr(rf, "feature_importances_")
              else np.ones(len(FEAT_NAMES)) / len(FEAT_NAMES))
    fi     = (fi_raw / fi_raw.sum()).tolist()

    # Save
    bundle = {"trained_models": trained, "scaler": sc,
              "spec_best": spec_best}
    joblib.dump(bundle, MODEL_PKL, compress=3)

    cap_defaults = {
        "doctors":      round(cap_doc, 1),
        "counters":     round(cap_ctr, 1),
        "totalBeds":    int(cap.get("totalBeds", 100)),
        "bedsOccupied": int(avg_bed if avg_bed else
                            cap.get("bedsOccupied",
                                    round(cap.get("totalBeds", 100) * 0.72))),
        "opdHrs":       int(cap.get("opdHrs", 6)),
        "edBeds":       int(cap.get("edBeds", 20)),
        "edOccupied":   int(cap.get("edOccupied", 12)),
        "admitRate":    float(cap.get("admitRate", 8)),
        "edRate":       float(cap.get("edRate", 3)),
        "walkInPct":    float(cap.get("walkInPct", 36)),
        "phonePct":     float(cap.get("phonePct", 34)),
    }

    stats = {
        "version":      "4.0",
        "trained_at":   datetime.now().isoformat(),
        "total_rows":   int(n),
        "session_id":   sid,
        "global_mean":  gm,
        "global_std":   gsd,
        "t_slope":      slope,
        "hol_mult":     hol_mult,
        "dowM":         dowM,
        "monM":         monM,
        "domM":         domM,
        "facilities":   facs,
        "climate":      climate,
        "cap_doctors":  round(cap_doc, 1),
        "cap_defaults": cap_defaults,
        "best_model":   best["name"],
        "best_mae":     best["mae"],
        "best_rmse":    best["rmse"],
        "best_mape":    best["mape"],
        "best_r2":      best["r2"],
        "all_results":  {r["name"]: r for r in results},
        "spec_info":    spec_info,
        "spec_best":    spec_best,
        "feature_importance": dict(zip(FEAT_NAMES, fi)),
        "training_time_sec":  round(time.time() - t0_all, 2),
        "gpu_used":     dev.gpu_name,
        "cpu_cores":    dev.cpu_count,
    }

    with open(STATS_JSON, "w") as f:
        json.dump(stats, f, indent=2, default=str)

    # Update memory
    mem["sessions"]    = sid
    mem["total_rows"] += len(new_df)
    all_dt = pd.to_datetime(train_df["_date"])
    mem["date_range"]  = {"first": str(all_dt.min().date()),
                          "last":  str(all_dt.max().date())}
    mem["specialties"]        = facs
    mem["csv_hashes"].append(chash)
    mem["cumulative_stats"]   = {
        "global_mean": gm, "global_std": gsd,
        "best_model":  best["name"], "best_mae": best["mae"],
    }
    mem["capacity_defaults"]  = cap_defaults
    mem["training_history"].append({
        "session":    sid,
        "date":       datetime.now().isoformat(),
        "rows_added": len(new_df),
        "total_rows": mem["total_rows"],
        "best_model": best["name"],
        "best_mae":   best["mae"],
        "accuracy":   best["accuracy"],
        "csv":        csv_path or "api_upload",
        "gpu":        dev.gpu_name,
    })
    save_memory(mem)

    log.info(f"Training complete — session {sid}, "
             f"best={best['name']}, acc={best['accuracy']}%")
    return stats


# ══════════════════════════════════════════════════════════════
# PREDICTION ENGINE
# ══════════════════════════════════════════════════════════════

def _load_bundle():
    if not MODEL_PKL.exists() or not STATS_JSON.exists():
        raise RuntimeError(
            "No trained model. POST /train first or run: "
            "python train.py --csv data/your_data.csv")
    bundle = joblib.load(MODEL_PKL)
    with open(STATS_JSON) as f:
        stats = json.load(f)
    return bundle, stats

def predict_one(date_str:  str,
                facility:  str = "all",
                season:    str = "auto",
                env:       Optional[dict] = None,
                cap_override: Optional[dict] = None,
                events:    Optional[list]  = None) -> dict:
    """
    Predict OPD patient count for one date.

    Parameters
    ──────────
    date_str     : "YYYY-MM-DD"
    facility     : specialty name or "all"
    season       : "auto" | "peak" | "off" | "rain" | "cold"
    env          : live environment overrides (see engineer_features)
    cap_override : capacity parameter overrides (merged with stored defaults)
    events       : list of event flag strings  e.g. ["epidemic","heatwave"]

    Returns full prediction + BOR + OPD + ED + wait dict.
    """
    bundle, stats = _load_bundle()
    env    = env or {}
    events = events or []
    cap    = {**stats.get("cap_defaults", {}), **(cap_override or {})}

    tr  = bundle["trained_models"]
    sc  = bundle["scaler"]
    gm  = stats["global_mean"]

    d   = pd.to_datetime(date_str)
    dow = d.dayofweek
    mon = d.month - 1
    dom = d.day

    # Apply staffing effect on cap.doctors
    if "staffing_pct" in env:
        base_docs = cap.get("doctors", stats["cap_doctors"])
        cap["doctors"] = max(1, round(base_docs * env["staffing_pct"] / 100))

    bname = (bundle["spec_best"].get(facility, stats["best_model"])
             if facility != "all" else stats["best_model"])
    mdl   = tr[bname]

    # Build synthetic row with env overrides applied
    lag = float(env.get("lagged", gm))
    row_df = pd.DataFrame([{
        "_date":     d,
        "_patients": gm,
        "_facility": facility,
        "_hour":     float(env.get("hour", 10)),
        "_temp":     float(env.get("temperature", 25)),
        "_aqi":      float(env.get("aqi", 80)),
        "_rain":     float(env.get("rainfall", 0)),
        "_holiday":  int(env.get("holiday", 0)),
        "_revisit":  gm * float(env.get("revisit_pct", 30)) / 100,
        "_lagged":   lag,
        "_doctors":  cap.get("doctors", stats["cap_doctors"]),
    }])

    X  = engineer_features(row_df, gm, stats["climate"],
                           stats["cap_doctors"], env)
    Xs = sc.transform(X)
    ml = max(0.0, float(mdl.predict(Xs)[0]))

    # Season multiplier
    if season == "auto":
        sm = stats["monM"].get(str(mon), 1.0)
    else:
        sm = SEASON_MULT.get(season, 1.0)

    bw  = min(0.75, stats["total_rows"] / 500)
    pt  = (gm * stats["dowM"].get(str(dow), 1.0)
           * sm * stats["domM"].get(str(dom - 1), 1.0))
    predicted = max(1, round(ml * bw + pt * (1 - bw)))

    # Weather adjustments
    temp = float(env.get("temperature", 25))
    aqi  = float(env.get("aqi", 80))
    rain = float(env.get("rainfall", 0))
    hum  = float(env.get("humidity", 60))

    if temp > 39:
        predicted = round(predicted * (1.10 + (temp - 39) * 0.012))
    elif temp < 5:
        predicted = round(predicted * 1.08)

    if aqi > 200:
        predicted = round(predicted * 1.18)
    elif aqi > 150:
        predicted = round(predicted * 1.09)
    elif aqi > 100:
        predicted = round(predicted * 1.04)

    if rain > 50:
        predicted = round(predicted * 0.85)
    elif rain > 20:
        predicted = round(predicted * 0.93)

    if hum > 85:
        predicted = round(predicted * 1.05)  # high humidity → more respiratory

    # Event flag adjustments
    for ev_id in events:
        impact = EVENT_IMPACTS.get(ev_id, 0.0)
        predicted = round(predicted * (1 + impact))

    if env.get("holiday", 0):
        predicted = round(predicted * stats.get("hol_mult", 0.72))

    predicted = max(1, predicted)
    unc  = round(predicted * 0.09)
    conf = max(65, min(94, 88 - abs(predicted / gm - 1) * 22))

    # Capacity outputs
    bor  = calc_bor(predicted, cap)
    opd  = calc_opd_load(predicted, cap)
    ed   = calc_ed_load(predicted, cap)
    wait = calc_wait_times(predicted, cap, env)

    # Alerts
    alerts = _build_alerts(predicted, gm, bor, opd, ed, wait, env)

    return {
        "prediction": {
            "date":           date_str,
            "facility":       facility,
            "predicted":      predicted,
            "low":            max(0, predicted - unc),
            "high":           predicted + unc,
            "confidence_pct": round(conf, 1),
            "model_used":     bname,
            "ml_blend_pct":   round(bw * 100, 1),
            "season_used":    season,
        },
        "bed_occupancy":         bor,
        "opd_load":              opd,
        "emergency_load":        ed,
        "waiting_times":         wait,
        "alerts":                alerts,
        "inputs_used": {
            "env":    env,
            "cap":    cap,
            "events": events,
            "season": season,
        },
    }

def _build_alerts(predicted, gm, bor, opd, ed, wait, env) -> list:
    alerts = []
    if predicted > gm * 1.4:
        alerts.append({"level":"warning","code":"high_influx",
                        "message":f"OPD load {round(predicted/gm*100-100)}% above average — consider surge protocol"})
    if opd["counter_status"] == "over":
        alerts.append({"level":"warning","code":"counter_overload",
                        "message":f"{opd['counters_needed']} counters needed (NHM max: 20 pts/hr/counter)"})
    if opd["doctor_status"] == "over":
        alerts.append({"level":"danger","code":"doctor_overload",
                        "message":f"Doctor load {opd['patients_per_doctor']:.1f} pts/day exceeds safe limit of 30"})
    if bor["over_capacity"]:
        alerts.append({"level":"danger","code":"bed_over_capacity",
                        "message":f"IPD beds will exceed capacity — prepare overflow plan"})
    elif bor["projected_bor_pct"] >= 90:
        alerts.append({"level":"warning","code":"bed_near_critical",
                        "message":f"BOR {bor['projected_bor_pct']}% approaching critical — review discharge schedule"})
    if ed["status"] == "critical":
        alerts.append({"level":"danger","code":"ed_critical",
                        "message":"ED at critical capacity — activate surge/diversion protocol"})
    elif ed["status"] == "high":
        alerts.append({"level":"warning","code":"ed_high",
                        "message":"ED high load — prepare overflow bays"})
    if wait["consultation"] > 90:
        alerts.append({"level":"warning","code":"long_wait",
                        "message":f"Consultation wait {wait['consultation']} min — consider extra sessions"})
    aqi = float(env.get("aqi", 80))
    if aqi > 150:
        alerts.append({"level":"info","code":"high_aqi",
                        "message":f"AQI {aqi:.0f} — elevated respiratory presentations expected"})
    if not alerts:
        alerts.append({"level":"ok","code":"nominal",
                        "message":"All metrics within safe range"})
    return alerts


def forecast_range(days:     int = 30,
                   facility: str = "all",
                   start:    Optional[str] = None,
                   env:      Optional[dict] = None,
                   cap_override: Optional[dict] = None,
                   events:   Optional[list] = None) -> list:
    s = pd.to_datetime(start) if start else datetime.now()
    results = []
    for i in range(days):
        d = s + timedelta(days=i)
        try:
            results.append(
                predict_one(d.strftime("%Y-%m-%d"), facility,
                            env=env, cap_override=cap_override,
                            events=events))
        except Exception as e:
            log.warning(f"Forecast day {i+1}: {e}")
    return results


# ══════════════════════════════════════════════════════════════
# STATUS & MODEL INFO
# ══════════════════════════════════════════════════════════════

def get_status() -> dict:
    mem = load_memory()
    model_info = {}
    if STATS_JSON.exists():
        with open(STATS_JSON) as f:
            st = json.load(f)
        model_info = {
            "best_model":  st.get("best_model"),
            "best_mae":    st.get("best_mae"),
            "accuracy_pct": round(100 - st.get("best_mape", 0), 1),
            "trained_at":  st.get("trained_at"),
            "total_rows":  st.get("total_rows"),
            "facilities":  st.get("facilities", []),
            "gpu_used":    st.get("gpu_used"),
            "climate":     st.get("climate"),
            "cap_defaults":st.get("cap_defaults", {}),
        }
    return {
        "sessions":          mem["sessions"],
        "total_rows":        mem["total_rows"],
        "date_range":        mem["date_range"],
        "specialties":       mem.get("specialties", []),
        "model_ready":       MODEL_PKL.exists() and STATS_JSON.exists(),
        "model_file_kb":     (round(MODEL_PKL.stat().st_size/1024)
                              if MODEL_PKL.exists() else 0),
        "training_history":  mem.get("training_history", [])[-10:],
        "model_info":        model_info,
        "device":            detect_devices().to_dict(),
    }

def get_model_info() -> dict:
    _, stats = _load_bundle()
    return {
        "version":            stats["version"],
        "trained_at":         stats["trained_at"],
        "total_rows":         stats["total_rows"],
        "session_id":         stats["session_id"],
        "facilities":         stats["facilities"],
        "climate":            stats["climate"],
        "best_model":         stats["best_model"],
        "accuracy_pct":       round(100 - stats["best_mape"], 1),
        "mae":                stats["best_mae"],
        "rmse":               stats["best_rmse"],
        "r2":                 stats["best_r2"],
        "all_model_results":  stats["all_results"],
        "spec_routing":       stats["spec_info"],
        "feature_importance": stats["feature_importance"],
        "cap_defaults":       stats["cap_defaults"],
        "gpu_used":           stats.get("gpu_used"),
        "training_time_sec":  stats.get("training_time_sec"),
    }

def clear_memory() -> dict:
    count = 0
    for p in list(DATA.glob("session_*.csv")) + \
             [MEMORY, MODEL_PKL, STATS_JSON]:
        if Path(p).exists():
            Path(p).unlink()
            count += 1
    return {"cleared_files": count, "message": "Memory cleared successfully"}


# ══════════════════════════════════════════════════════════════
# LOCAL DATA STORAGE — query, inspect, export
# No database needed. All data lives in CSV files.
# ══════════════════════════════════════════════════════════════

def load_all_data(facility: Optional[str] = None,
                  from_date: Optional[str] = None,
                  to_date:   Optional[str] = None) -> pd.DataFrame:
    """
    Load all stored training data from session CSVs.
    Optionally filter by specialty, start date, end date.
    Returns a clean DataFrame with human-readable column names.
    """
    df = load_all_sessions()
    if df.empty:
        return pd.DataFrame()

    # Ensure date column is datetime
    df["_date"] = pd.to_datetime(df["_date"], errors="coerce")

    # Filters
    if facility and facility.lower() != "all":
        df = df[df["_facility"].str.lower() == facility.lower()]
    if from_date:
        df = df[df["_date"] >= pd.to_datetime(from_date)]
    if to_date:
        df = df[df["_date"] <= pd.to_datetime(to_date)]

    df = df.sort_values("_date").reset_index(drop=True)

    # Rename to readable columns for output
    rename = {
        "_date":     "date",
        "_patients": "patients",
        "_facility": "specialty",
        "_hour":     "hour",
        "_temp":     "temperature",
        "_aqi":      "aqi",
        "_rain":     "rainfall",
        "_holiday":  "holiday",
        "_revisit":  "revisit",
        "_lagged":   "lagged",
        "_doctors":  "doctors",
        "_counters": "counters",
        "_beds_occ": "beds_occupied",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")
    return df


def get_data_for_date(date_str: str,
                      facility: Optional[str] = None) -> dict:
    """
    Return all stored rows for a specific date.
    Shows actual recorded data plus the model's prediction for comparison.
    """
    df = load_all_data(facility=facility,
                       from_date=date_str, to_date=date_str)

    records = df.to_dict(orient="records") if not df.empty else []

    # Also predict for this date if model is ready
    prediction = None
    if MODEL_PKL.exists() and STATS_JSON.exists():
        try:
            fac = facility or "all"
            prediction = predict_one(date_str, fac)
        except Exception as e:
            prediction = {"error": str(e)}

    return {
        "date":       date_str,
        "facility":   facility or "all",
        "stored_rows": len(records),
        "actual_data": records,
        "prediction":  prediction,
    }


def get_data_range(from_date: Optional[str] = None,
                   to_date:   Optional[str] = None,
                   facility:  Optional[str] = None,
                   summary:   bool = True) -> dict:
    """
    Query all stored data within a date range.

    summary=True  → aggregated stats per date (fast)
    summary=False → every individual row
    """
    df = load_all_data(facility=facility,
                       from_date=from_date, to_date=to_date)
    if df.empty:
        return {"rows": 0, "data": [], "summary": {}}

    if summary:
        # Daily aggregate
        grp = (df.groupby("date")
                 .agg(
                     total_patients=("patients", "sum"),
                     specialties=("specialty", lambda x: list(x.unique())),
                     avg_patients=("patients", "mean"),
                     max_patients=("patients", "max"),
                     min_patients=("patients", "min"),
                 )
                 .reset_index())
        grp["avg_patients"] = grp["avg_patients"].round(1)
        data = grp.to_dict(orient="records")
    else:
        data = df.to_dict(orient="records")

    # Summary stats for the whole range
    stats_out = {
        "total_rows":        len(df),
        "date_range":        {
            "from": df["date"].min() if len(df) else None,
            "to":   df["date"].max() if len(df) else None,
        },
        "specialties":       sorted(df["specialty"].unique().tolist()),
        "total_patients":    int(df["patients"].sum()),
        "avg_daily":         round(df["patients"].mean(), 1),
        "max_daily":         int(df["patients"].max()),
        "min_daily":         int(df["patients"].min()),
        "days_with_data":    df["date"].nunique(),
    }

    return {
        "rows":    len(data),
        "data":    data,
        "summary": stats_out,
    }


def export_all_data(out_path: Optional[str] = None,
                    facility:  Optional[str] = None,
                    from_date: Optional[str] = None,
                    to_date:   Optional[str] = None) -> str:
    """
    Export all stored training data to a single CSV.
    Returns the path of the saved file.
    """
    df = load_all_data(facility=facility,
                       from_date=from_date, to_date=to_date)
    if df.empty:
        raise ValueError("No data found matching the given filters.")

    if out_path is None:
        ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
        tag = f"_{facility}" if facility else ""
        out_path = str(EXP / f"data_export{tag}_{ts}.csv")

    df.to_csv(out_path, index=False)
    log.info(f"Exported {len(df):,} rows → {out_path}")
    return out_path


def get_storage_info() -> dict:
    """
    Report on all local storage files — no database needed.
    """
    files = []
    total_bytes = 0

    for folder, label in [(DATA, "session_data"),
                          (MODELS, "model_files"),
                          (EXP,   "exports"),
                          (LOGS,  "logs")]:
        for p in sorted(folder.iterdir()):
            if p.is_file():
                sz = p.stat().st_size
                total_bytes += sz
                files.append({
                    "path":     str(p.relative_to(BASE)),
                    "category": label,
                    "size_kb":  round(sz / 1024, 1),
                    "modified": datetime.fromtimestamp(
                                    p.stat().st_mtime).strftime(
                                    "%Y-%m-%d %H:%M"),
                })

    mem = load_memory()
    return {
        "storage_type":   "local_files_only",
        "database_used":  False,
        "base_directory": str(BASE),
        "total_size_kb":  round(total_bytes / 1024, 1),
        "total_size_mb":  round(total_bytes / 1024 / 1024, 2),
        "file_count":     len(files),
        "files":          files,
        "session_count":  mem.get("sessions", 0),
        "total_data_rows":mem.get("total_rows", 0),
        "formats_used": {
            "training_data":  "CSV (.csv) — one file per training session",
            "model":          "Pickle (.pkl) — sklearn joblib format",
            "statistics":     "JSON (.json) — learned patterns + metadata",
            "memory":         "JSON (.json) — session index + history",
            "exports":        "CSV + JSON — forecasts + dashboard models",
            "logs":           "Plain text (.log)",
        },
    }

