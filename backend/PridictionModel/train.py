#!/usr/bin/env python3
"""
train.py  —  Patient Influx & Capacity Prediction  —  CLI
══════════════════════════════════════════════════════════
All ML logic lives in core.py.
This file is the command-line interface only.

Commands
────────
  python train.py --csv data/patients.csv
  python train.py --csv data/june.csv --retrain
  python train.py --predict --date 2025-08-15
  python train.py --predict --date 2025-08-15 --capacity
  python train.py --forecast --days 30 --capacity
  python train.py --capacity-report
  python train.py --export-dashboard
  python train.py --status
  python train.py --benchmark
  python train.py --clear-memory

API server (all features available over HTTP):
  python server.py
  python server.py --port 8080 --host 0.0.0.0
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import core

# ── Colours ────────────────────────────────────────────────────
try:
    from colorama import Fore, Style, init as _ci
    _ci(autoreset=True)
    G=Fore.GREEN; Y=Fore.YELLOW; R=Fore.RED; C=Fore.CYAN
    M=Fore.MAGENTA; DIM=Style.DIM; B=Style.BRIGHT; RST=Style.RESET_ALL
except ImportError:
    G=Y=R=C=M=DIM=B=RST=""

# ── Progress bar ───────────────────────────────────────────────
try:
    from tqdm import tqdm as _tq
    def pbar(it, desc="", total=None):
        return _tq(it, desc=f"{C}{desc}{RST}", total=total,
                   bar_format="{l_bar}{bar:30}{r_bar}", ncols=80)
except ImportError:
    def pbar(it, desc="", total=None):
        items = list(it)
        n = len(items)
        for i, item in enumerate(items):
            pct = int((i+1)/n*30)
            print(f"\r  {desc} [{'█'*pct}{'░'*(30-pct)}] {i+1}/{n}",
                  end="", flush=True)
            yield item
        print()


# ══════════════════════════════════════════════════════════════
# PRINT HELPERS
# ══════════════════════════════════════════════════════════════

def print_capacity(res: dict):
    """Print full BOR / OPD / ED / wait report to terminal."""
    bor = res["bed_occupancy"]
    opd = res["opd_load"]
    ed  = res["emergency_load"]
    wt  = res["waiting_times"]

    bc = (R if bor["status"]=="critical" else
          G if bor["status"]=="target"   else Y)
    ec = (R if ed["status"]=="critical"  else
          Y if ed["status"]=="high"      else G)

    print(f"\n  {B}── BED OCCUPANCY (IPD)  ─  IPHS target ≥80% ──{RST}")
    print(f"  Current BOR      : {bor['current_bor_pct']:>5.1f}%  "
          f"({bor['current_occupied']} / {bor['total_beds']} beds)")
    print(f"  New admissions   : {bor['new_admissions']:>5}")
    print(f"  Projected BOR    : {bc}{bor['projected_bor_pct']:>5.1f}%{RST}  "
          f"({bor['projected_occupied']} / {bor['total_beds']} beds)")
    print(f"  Free beds after  : {bor['beds_free_after']}")
    if bor["over_capacity"]:
        print(f"  {R}⚠ OVER CAPACITY — prepare overflow plan{RST}")
    elif bor["projected_bor_pct"] >= 90:
        print(f"  {Y}⚠ Approaching critical — review discharge schedule{RST}")

    print(f"\n  {B}── OPD LOAD  ─  NHM norm: 12–20 pts/hr/ctr ──{RST}")
    cc = G if opd["counter_status"]=="ok" else R
    dc = G if opd["doctor_status"]=="ok"  else (Y if opd["doctor_status"]=="warn" else R)
    print(f"  Patients/hour    : {opd['patients_per_hour']:>6.1f}")
    print(f"  Load per counter : {cc}{opd['patients_per_hr_per_ctr']:>6.1f}{RST}  "
          f"(NHM 12–20)  "
          f"{'✓ ok' if opd['counter_status']=='ok' else '⚠ over'}")
    print(f"  Load per doctor  : {dc}{opd['patients_per_doctor']:>6.1f}{RST}  "
          f"(comfortable <20)")
    print(f"  Counters needed  : {opd['counters_needed']}  "
          f"(available: {opd['counters_available']})")
    print(f"  Doctors needed   : {opd['doctors_needed']}  "
          f"(available: {opd['doctors_available']})")

    print(f"\n  {B}── EMERGENCY DEPARTMENT ──{RST}")
    now_pct = (round(ed["ed_occupied_now"] / ed["ed_beds"] * 100)
               if ed["ed_beds"] else 0)
    print(f"  Current util     : {now_pct:.0f}%  "
          f"({ed['ed_occupied_now']} / {ed['ed_beds']} beds)")
    print(f"  OPD transfers    : {ed['opd_transfers']}")
    print(f"  Direct walk-ins  : {ed['direct_walkins']}")
    print(f"  Projected util   : {ec}{ed['utilisation_pct']:.1f}%{RST}  "
          f"({ed['projected_occupied']} / {ed['ed_beds']} beds)")
    print(f"  Triage  Imm={ed['triage_immediate']}  "
          f"Urg={ed['triage_urgent']}  "
          f"Non-urg={ed['triage_non_urgent']}  "
          f"Obs={ed['triage_observation']}")
    if ed["status"] == "critical":
        print(f"  {R}⚠ ED CRITICAL — activate surge protocol{RST}")
    elif ed["status"] == "high":
        print(f"  {Y}⚠ ED high load — prepare overflow bays{RST}")

    print(f"\n  {B}── PATIENT WAITING TIMES ──{RST}")
    phases = [
        ("Transport",    wt["transport"],    40),
        ("Registration", wt["registration"], 30),
        ("Triage",       wt["triage"],       15),
        ("Consultation", wt["consultation"], 90),
        ("Pharmacy",     wt["pharmacy"],     30),
        ("Billing",      wt["billing"],      60),
    ]
    for nm, val, mx in phases:
        pct = min(1.0, val / mx)
        col = R if pct > 0.85 else Y if pct > 0.6 else G
        bar = "█" * int(pct*20) + "░" * (20 - int(pct*20))
        print(f"  {nm:<14} {col}{bar}{RST}  {col}{val:>3} min{RST}")
    tc = R if wt["total"]>180 else Y if wt["total"]>120 else G
    print(f"  {'─'*50}")
    print(f"  {'Total':<14}                       "
          f"{tc}{B}{wt['total']:>3} min{RST}")
    if wt.get("bed_delay_mult", 1) > 1:
        print(f"  {Y}  ⟳ High BOR adding "
              f"+{round((wt['bed_delay_mult']-1)*100)}% to consultation{RST}")

    # Alerts
    alerts = res.get("alerts", [])
    flagged = [a for a in alerts if a["level"] != "ok"]
    if flagged:
        print(f"\n  {B}── ALERTS ──{RST}")
        for a in flagged:
            col = R if a["level"]=="danger" else Y if a["level"]=="warning" else C
            print(f"  {col}{a['level'].upper():<8}{RST} {a['message']}")


def print_train_results(stats: dict):
    """Print training summary table."""
    dev_info = core.detect_devices()
    print(f"\n{B}{'═'*62}{RST}")
    print(f"{B}  TRAINING COMPLETE — Session {stats['session_id']}{RST}")
    print(f"{'─'*62}")
    print(f"  Records this session : {stats.get('total_rows',0):,}")
    mem = core.load_memory()
    print(f"  Total memory records : {mem['total_rows']:,}")
    print(f"  Date range           : "
          f"{mem['date_range'].get('first','—')} → "
          f"{mem['date_range'].get('last','—')}")
    print(f"\n  {'Model':<10} {'MAE':>7} {'RMSE':>7} "
          f"{'MAPE%':>7} {'R²':>7} {'Acc%':>7}")
    print(f"  {'─'*50}")
    for nm, ev in stats["all_results"].items():
        is_best = nm == stats["best_model"]
        ac = G if ev["accuracy"]>=90 else Y if ev["accuracy"]>=80 else R
        tag = f"  {G}← best{RST}" if is_best else ""
        print(f"  {nm:<10} {ev['mae']:>7.2f} {ev['rmse']:>7.2f} "
              f"{ev['mape']:>7.2f} {ev['r2']:>7.4f} "
              f"{ac}{ev['accuracy']:>6.1f}%{RST}{tag}")
    print(f"  {'─'*50}")
    print(f"\n  Best model : {G}{stats['best_model']}{RST}")
    print(f"  Accuracy   : {G}{round(100-stats['best_mape'],1)}%{RST}")
    print(f"  MAE        : {stats['best_mae']}")
    print(f"  GPU        : {stats.get('gpu_used','none')}")
    print(f"  Time       : {stats.get('training_time_sec','?')}s")

    print(f"\n  Per-specialty routing:")
    for fac, info in stats["spec_info"].items():
        tc = G if info["is_known_specialty"] else C
        print(f"  {tc}{fac:<25}{RST}  {G}{info['used_model']:<7}{RST}  "
              f"{DIM}{info['method']}{RST}")

    print(f"\n  Top features:")
    fi = stats["feature_importance"]
    for fn, fv in sorted(fi.items(), key=lambda x:-x[1])[:6]:
        print(f"  {fn:<25} {'█'*int(fv*200):<20} {fv*100:.1f}%")
    print(f"{B}{'═'*62}{RST}\n")


def show_status():
    s = core.get_status()
    print(f"\n{B}{'═'*62}{RST}")
    print(f"{B}  PATIENT PREDICTOR — MEMORY STATUS{RST}")
    print(f"{'═'*62}")
    print(f"  Sessions trained : {G}{s['sessions']}{RST}")
    print(f"  Total rows       : {G}{s['total_rows']:,}{RST}")
    if s["date_range"]["first"]:
        print(f"  Date range       : "
              f"{s['date_range']['first']} → {s['date_range']['last']}")
    print(f"  Specialties      : "
          f"{G}{', '.join(s['specialties']) or 'none'}{RST}")
    hist = s.get("training_history",[])
    if hist:
        print(f"\n  {'Sess':<5} {'Date':<17} {'Rows':>7} {'Total':>8} "
              f"{'Model':<7} {'MAE':>6} {'Acc%':>6} GPU")
        print(f"  {'─'*68}")
        for h in hist:
            ac = G if h["accuracy"]>=90 else Y
            print(f"  {h['session']:<5} {h['date'][:16]:<17} "
                  f"{h['rows_added']:>7,} {h['total_rows']:>8,} "
                  f"{h['best_model']:<7} {h['best_mae']:>6} "
                  f"{ac}{h['accuracy']:>5.1f}%{RST}  "
                  f"{DIM}{h.get('gpu','—')}{RST}")
    mi = s.get("model_info",{})
    if mi:
        kb = s.get("model_file_kb", 0)
        print(f"\n  Model    : {mi.get('best_model','—')}  "
              f"MAE={mi.get('best_mae','—')}  "
              f"Acc={mi.get('accuracy_pct','—')}%")
        print(f"  GPU      : {mi.get('gpu_used','—')}")
        print(f"  Size     : {kb} KB")
    dev = s.get("device",{})
    print(f"\n  CPU      : {G}{dev.get('cpu_count',1)} cores{RST}")
    print(f"  GPU      : {G if dev.get('gpu_type')!='none' else Y}"
          f"{dev.get('gpu_name','none')}{RST}")
    print(f"{'═'*62}\n")


def run_benchmark():
    print(f"\n{B}  CPU vs GPU BENCHMARK{RST}")
    dev = core.detect_devices()
    rng = np.random.default_rng(42)
    Xb  = rng.random((2000,17)).astype(np.float32)
    yb  = rng.random(2000) * 100
    print(f"\n  {'Model':<10} {'Time (s)':>10}  Backend")
    print(f"  {'─'*36}")
    for name, mdl in core.build_models(dev, n_jobs=-1).items():
        t0 = time.time()
        mdl.fit(Xb, yb)
        tag = (f"{G}GPU{RST}"
               if (name=="GBM" and dev.xgb_gpu)
               or (name=="RF"  and dev.lgbm_gpu)
               else f"{Y}CPU{RST}")
        print(f"  {name:<10} {time.time()-t0:>10.3f}s  {tag}")
    print()


def export_dashboard(stats: dict) -> str:
    """Export model to JSON for HTML dashboard."""
    import joblib, json

    bundle = joblib.load(core.MODEL_PKL)
    with open(core.STATS_JSON) as f:
        st = json.load(f)

    def _gbm_trees(mdl, n=40):
        out = []
        try:
            lr = mdl.learning_rate
            for arr in mdl.estimators_[:n]:
                t = arr[0].tree_
                f_ = int(t.feature[0])   if t.feature[0]>=0   else 0
                th = float(t.threshold[0]) if t.threshold[0]!=-2 else 0.5
                lv = float(t.value[1][0][0]) if t.node_count>1 else 0.0
                rv = float(t.value[2][0][0]) if t.node_count>1 else 0.0
                out.append({"s":{"feat":f_,"thresh":th,"lv":lv,"rv":rv},"lr":lr})
        except Exception:
            pass
        return out

    def _rf_trees(mdl, n=40):
        out = []
        try:
            mv = float(np.mean(
                [e.tree_.value[0][0][0] for e in mdl.estimators_[:n]]))
            for e in mdl.estimators_[:n]:
                t = e.tree_
                f_ = int(t.feature[0])   if t.feature[0]>=0   else 0
                th = float(t.threshold[0]) if t.threshold[0]!=-2 else 0.5
                lv = float(t.value[1][0][0]) if t.node_count>1 else mv
                rv = float(t.value[2][0][0]) if t.node_count>1 else mv
                out.append({"s":{"feat":f_,"thresh":th,"lv":lv,"rv":rv},"mean":mv})
        except Exception:
            pass
        return out

    def _dt(mdl):
        t = mdl.tree_
        return {"feat": int(t.feature[0]) if t.feature[0]>=0 else 0,
                "thresh":float(t.threshold[0]) if t.threshold[0]!=-2 else 0.5,
                "lv":float(t.value[1][0][0]) if t.node_count>1 else 0.0,
                "rv":float(t.value[2][0][0]) if t.node_count>1 else 0.0}

    js_models = {}
    for nm, mdl in bundle["trained_models"].items():
        ev = st["all_results"].get(nm,{})
        if nm=="GBM":
            js_models[nm]={"type":"GBM","baseMean":st["global_mean"],
                           "eval":ev,"trees":_gbm_trees(mdl)}
        elif nm=="RF":
            js_models[nm]={"type":"RF","baseMean":st["global_mean"],
                           "eval":ev,"trees":_rf_trees(mdl)}
        elif nm=="Ridge":
            js_models[nm]={"type":"LR","eval":ev,
                "w":[float(mdl.intercept_)]+[float(c) for c in mdl.coef_]}
        elif nm=="KNN":
            step=max(1,len(mdl._fit_X)//200)
            js_models[nm]={"type":"KNN","eval":ev,
                "X":mdl._fit_X[::step].tolist(),"y":mdl._y[::step].tolist()}
        elif nm=="DT":
            js_models[nm]={"type":"DT","eval":ev,
                "mean":st["global_mean"],"s":_dt(mdl)}

    export = {
        "version":"4.0","savedAt":st["trained_at"],
        "setting":"opd_multi","climate":st["climate"],
        "cap":st.get("cap_defaults",{}),
        "facilityList":st["facilities"],
        "specInfo":    st["spec_info"],
        "bestModel":   st["best_model"],
        "perSpecBest": {f"_b_{k}":v for k,v in st["spec_best"].items()},
        "modelStats":{
            "mean":st["global_mean"],"std":st["global_std"],
            "dowM":{int(k):v for k,v in st["dowM"].items()},
            "monM":{int(k):v for k,v in st["monM"].items()},
            "domM":{int(k):v for k,v in st["domM"].items()},
            "holMult":st["hol_mult"],"tSlope":st["t_slope"],
            "lastIdx":st["total_rows"],"avgDocs":st["cap_doctors"],
            "avgCtrs":st.get("cap_defaults",{}).get("counters",3),
            "bestModel":st["best_model"],"bestMAE":st["best_mae"],
            "bestRMSE":st["best_rmse"],"bestMAPE":st["best_mape"],
            "bestR2":st["best_r2"],"allResults":st["all_results"],
            "fi":list(st["feature_importance"].values()),
            "means":{"mean":st["global_mean"],"std":st["global_std"]},
        },
        "models":js_models,
    }

    out = (core.EXP /
           f"dashboard_model_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(out,"w") as f:
        json.dump(export, f, default=str)
    return str(out)


# ══════════════════════════════════════════════════════════════
# CLI ENTRY POINT
# ══════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(
        description="Patient Influx & Capacity Prediction — CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
━━━ TRAINING ━━━
  python train.py --csv data/patients.csv
  python train.py --csv data/june.csv --retrain
  python train.py --csv data.csv --retrain --jobs 8
  python train.py --csv data.csv --climate tropical
  python train.py --csv data.csv --from-date 2023-06-01 --to-date 2024-01-01
  python train.py --csv data.csv --retrain --from-date 2024-01-01

━━━ PREDICTION ━━━
  python train.py --predict --date 2025-08-15
  python train.py --predict --date 2025-08-15 --facility "General Medicine"
  python train.py --predict --date 2025-08-15 --capacity
  python train.py --predict --date 2025-08-15 --temp 38 --aqi 145
  python train.py --predict --date 2025-08-15 --events epidemic heatwave
  python train.py --predict --date 2025-08-15 --staffing 75 --lagged 65

━━━ FORECAST ━━━
  python train.py --forecast --days 30
  python train.py --forecast --days 14 --facility "Dental" --capacity
  python train.py --forecast --days 7 --start 2025-09-01
  python train.py --forecast --days 30 --temp 34 --aqi 120

━━━ CAPACITY ━━━
  python train.py --capacity-report
  python train.py --capacity-report --beds 150 --beds-occ 110 --ed-beds 30
  python train.py --capacity-report --staffing 80 --doctors 6

━━━ DATA INSPECT ━━━
  python train.py --data
  python train.py --data --from-date 2023-06-01 --to-date 2023-06-30
  python train.py --data --facility "General Medicine"
  python train.py --data-date 2023-07-15
  python train.py --data-date 2023-07-15 --facility "ENT"
  python train.py --export-data
  python train.py --export-data --from-date 2023-01-01

━━━ SYSTEM ━━━
  python train.py --status
  python train.py --storage
  python train.py --benchmark
  python train.py --export-dashboard
  python train.py --clear-memory

━━━ API SERVER ━━━
  python server.py
  python server.py --host 0.0.0.0 --port 8080
  python server.py --debug
        """
    )

    # Training
    ap.add_argument("--csv",      help="Training CSV path")
    ap.add_argument("--retrain",  action="store_true")
    ap.add_argument("--climate",  default="semi_arid",
                    choices=["semi_arid","tropical","temperate",
                             "cold","equatorial"])
    ap.add_argument("--jobs",     type=int, default=-1)
    ap.add_argument("--from-date", default=None, metavar="YYYY-MM-DD",
                    help="Only train on data on or after this date")
    ap.add_argument("--to-date",   default=None, metavar="YYYY-MM-DD",
                    help="Only train on data on or before this date")

    # Prediction
    ap.add_argument("--predict",  action="store_true")
    ap.add_argument("--date",
                    default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--facility", default="all")
    ap.add_argument("--season",   default="auto",
                    choices=["auto","peak","off","rain","cold"])
    ap.add_argument("--capacity", action="store_true")

    # Forecast
    ap.add_argument("--forecast", action="store_true")
    ap.add_argument("--days",     type=int, default=30)
    ap.add_argument("--start",    default=None)

    # Live environment flags (mirror of API env fields)
    ap.add_argument("--temp",        type=float, default=None,
                    help="Temperature °C")
    ap.add_argument("--aqi",         type=float, default=None,
                    help="Air Quality Index")
    ap.add_argument("--rain",        type=float, default=None,
                    help="Rainfall mm")
    ap.add_argument("--humidity",    type=float, default=None,
                    help="Humidity %%")
    ap.add_argument("--hour",        type=float, default=None,
                    help="Hour of day 0-23")
    ap.add_argument("--holiday",     type=int,   default=None,
                    help="Holiday flag: 1 or 0")
    ap.add_argument("--staffing",    type=float, default=None,
                    help="Staff availability %%")
    ap.add_argument("--lagged",      type=float, default=None,
                    help="Yesterday's patient count")
    ap.add_argument("--events",      nargs="*",  default=None,
                    help="Event flags: holiday festival heatwave flu_peak "
                         "rain_heavy long_weekend epidemic mass_event")

    # Capacity overrides
    ap.add_argument("--beds",        type=int,   default=None)
    ap.add_argument("--beds-occ",    type=int,   default=None)
    ap.add_argument("--ed-beds",     type=int,   default=None)
    ap.add_argument("--ed-occ",      type=int,   default=None)
    ap.add_argument("--admit-rate",  type=float, default=None)
    ap.add_argument("--ed-rate",     type=float, default=None)
    ap.add_argument("--doctors",     type=int,   default=None)
    ap.add_argument("--counters",    type=int,   default=None)
    ap.add_argument("--opd-hrs",     type=float, default=None)
    ap.add_argument("--walk-in",     type=float, default=None)

    # Utilities
    ap.add_argument("--capacity-report",  action="store_true")
    ap.add_argument("--export-dashboard", action="store_true")
    ap.add_argument("--status",           action="store_true")
    ap.add_argument("--benchmark",        action="store_true")
    ap.add_argument("--clear-memory",     action="store_true")

    # Data query / inspect
    ap.add_argument("--data",      action="store_true",
                    help="Show all stored data (with optional filters)")
    ap.add_argument("--data-date", default=None, metavar="YYYY-MM-DD",
                    help="Show stored data + prediction for one specific date")
    ap.add_argument("--export-data", action="store_true",
                    help="Export all stored data to a CSV file")
    ap.add_argument("--storage",   action="store_true",
                    help="Show local storage info (files, sizes, formats)")

    args = ap.parse_args()

    # Build env dict from CLI flags
    env = {}
    if args.temp      is not None: env["temperature"]  = args.temp
    if args.aqi       is not None: env["aqi"]           = args.aqi
    if args.rain      is not None: env["rainfall"]      = args.rain
    if args.humidity  is not None: env["humidity"]      = args.humidity
    if args.hour      is not None: env["hour"]          = args.hour
    if args.holiday   is not None: env["holiday"]       = args.holiday
    if args.staffing  is not None: env["staffing_pct"]  = args.staffing
    if args.lagged    is not None: env["lagged"]        = args.lagged

    # Build cap dict
    cap = {}
    if args.beds       is not None: cap["totalBeds"]    = args.beds
    if args.beds_occ   is not None: cap["bedsOccupied"] = args.beds_occ
    if args.ed_beds    is not None: cap["edBeds"]       = args.ed_beds
    if args.ed_occ     is not None: cap["edOccupied"]   = args.ed_occ
    if args.admit_rate is not None: cap["admitRate"]    = args.admit_rate
    if args.ed_rate    is not None: cap["edRate"]       = args.ed_rate
    if args.doctors    is not None: cap["doctors"]      = args.doctors
    if args.counters   is not None: cap["counters"]     = args.counters
    if args.opd_hrs    is not None: cap["opdHrs"]       = args.opd_hrs
    if args.walk_in    is not None: cap["walkInPct"]    = args.walk_in

    events = args.events or []

    # ── Status ─────────────────────────────────────────────────
    if args.status:
        show_status(); return

    # ── Storage info ───────────────────────────────────────────
    if args.storage:
        info = core.get_storage_info()
        print(f"\n{B}{'═'*62}{RST}")
        print(f"{B}  LOCAL STORAGE — no database required{RST}")
        print(f"{'═'*62}")
        print(f"  Base directory   : {info['base_directory']}")
        print(f"  Total size       : {info['total_size_mb']} MB  "
              f"({info['file_count']} files)")
        print(f"  Sessions stored  : {info['session_count']}")
        print(f"  Total data rows  : {info['total_data_rows']:,}")
        print(f"\n  Formats:")
        for k,v in info["formats_used"].items():
            print(f"    {k:<18} {DIM}{v}{RST}")
        print(f"\n  {'File':<40} {'Size':>8}  {'Modified':<17}")
        print(f"  {'─'*68}")
        for f in info["files"]:
            print(f"  {f['path']:<40} {f['size_kb']:>6.1f}KB  {f['modified']}")
        print(f"{'═'*62}\n")
        return

    # ── Data query — all stored data ───────────────────────────
    if args.data:
        result = core.get_data_range(
            from_date=args.from_date,
            to_date=args.to_date,
            facility=args.facility if args.facility!="all" else None,
        )
        s = result["summary"]
        print(f"\n{B}{'═'*62}{RST}")
        print(f"{B}  STORED DATA{RST}"
              f"{'  ('+args.facility+')' if args.facility!='all' else ''}")
        print(f"{'═'*62}")
        if not result["data"]:
            print(f"  {Y}No data found matching the filters.{RST}")
        else:
            fd = args.from_date or s["date_range"]["from"]
            td = args.to_date   or s["date_range"]["to"]
            print(f"  Range     : {fd} → {td}")
            print(f"  Days      : {s['days_with_data']}")
            print(f"  Rows      : {s['total_rows']:,}")
            print(f"  Specialties: {', '.join(s['specialties'])}")
            print(f"  Total pts : {s['total_patients']:,}")
            print(f"  Avg/day   : {s['avg_daily']}")
            print(f"  Max/day   : {s['max_daily']}")
            print(f"  Min/day   : {s['min_daily']}")
            print(f"\n  {'Date':<13} {'Patients':>9} {'Specialties'}")
            print(f"  {'─'*50}")
            for row in result["data"][:50]:
                specs = ', '.join(row['specialties']) if isinstance(row.get('specialties'), list) else ''
                print(f"  {row['date']:<13} "
                      f"{G}{row['total_patients']:>9,}{RST} "
                      f"{DIM}{specs}{RST}")
            if len(result["data"]) > 50:
                print(f"  {DIM}… {len(result['data'])-50} more rows "
                      f"(use --export-data to get all){RST}")
        print(f"{'═'*62}\n")
        return

    # ── Data query — specific date ─────────────────────────────
    if args.data_date:
        result = core.get_data_for_date(
            args.data_date,
            facility=args.facility if args.facility!="all" else None)
        print(f"\n{B}{'═'*62}{RST}")
        print(f"{B}  DATA + PREDICTION — {args.data_date}{RST}")
        print(f"{'═'*62}")
        if not result["actual_data"]:
            print(f"  {Y}No stored data for this date.{RST}")
        else:
            print(f"  Stored records: {result['stored_rows']}")
            for row in result["actual_data"]:
                print(f"\n  {G}{row.get('specialty','All')}{RST}")
                print(f"    Patients    : {row.get('patients','—')}")
                print(f"    Temperature : {row.get('temperature','—')}")
                print(f"    AQI         : {row.get('aqi','—')}")
                print(f"    Rainfall    : {row.get('rainfall','—')} mm")
                print(f"    Holiday     : {'Yes' if row.get('holiday') else 'No'}")
                print(f"    Doctors     : {row.get('doctors','—')}")
        if result["prediction"]:
            p = result["prediction"]
            if "error" in p:
                print(f"\n  {Y}Prediction unavailable: {p['error']}{RST}")
            else:
                pred = p["prediction"]
                print(f"\n  {B}Model prediction for this date:{RST}")
                print(f"    Predicted   : {G}{pred['predicted']}{RST} patients")
                print(f"    Range       : {pred['low']} – {pred['high']}")
                print(f"    Confidence  : {pred['confidence_pct']}%")
                print(f"    Model used  : {pred['model_used']}")
                if result["actual_data"]:
                    actual = result["actual_data"][0].get("patients")
                    if actual:
                        err = abs(pred["predicted"]-actual)/actual*100
                        col = G if err<10 else Y if err<20 else R
                        print(f"    Actual      : {actual}  "
                              f"Error: {col}{err:.1f}%{RST}")
        print(f"{'═'*62}\n")
        return

    # ── Export data ────────────────────────────────────────────
    if args.export_data:
        path = core.export_all_data(
            facility=args.facility if args.facility!="all" else None,
            from_date=args.from_date,
            to_date=args.to_date)
        print(f"\n{G}✓ Data exported → {path}{RST}\n")
        return

    # ── Benchmark ──────────────────────────────────────────────
    if args.benchmark:
        run_benchmark(); return

    # ── Clear memory ───────────────────────────────────────────
    if args.clear_memory:
        ans = input(f"{R}Clear ALL training memory? "
                    f"Type 'yes' to confirm: {RST}")
        if ans.strip().lower() == "yes":
            r = core.clear_memory()
            print(f"{G}Cleared {r['cleared_files']} files.{RST}")
        else:
            print("Cancelled.")
        return

    # ── Train ──────────────────────────────────────────────────
    if args.csv:
        if not Path(args.csv).exists():
            print(f"{R}CSV not found: {args.csv}{RST}"); sys.exit(1)

        dev = core.detect_devices()
        print(f"\n{B}{'═'*62}{RST}")
        print(f"{B}  PATIENT INFLUX PREDICTION — TRAINING{RST}")
        print(f"{B}{'═'*62}{RST}")
        print(f"  CPU : {G}{dev.cpu_count} cores{RST}")
        gpu_c = G if dev.gpu_type!="none" else Y
        print(f"  GPU : {gpu_c}{dev.gpu_name}{RST}")
        if dev.xgb_gpu:  print(f"  XGBoost GPU  : {G}✓{RST}")
        if dev.lgbm_gpu: print(f"  LightGBM GPU : {G}✓{RST}")
        print(f"  Mode: "
              f"{M}INCREMENTAL{RST}" if args.retrain else f"{C}FRESH{RST}")

        def _cb(step, total, msg):
            print(f"  {C}[{step}/{total}]{RST} {msg}")

        stats = core.run_training(
            csv_path=args.csv,
            retrain=args.retrain,
            climate=args.climate,
            n_jobs=args.jobs,
            cap=cap or {},
            progress_cb=_cb,
            from_date=args.from_date,
            to_date=args.to_date,
        )
        print_train_results(stats)
        return

    # ── Single prediction ──────────────────────────────────────
    if args.predict:
        res = core.predict_one(
            args.date, args.facility, args.season,
            env=env or None,
            cap_override=cap or None,
            events=events)
        p = res["prediction"]
        print(f"\n{B}{'═'*52}{RST}")
        print(f"{B}  PREDICTION — {p['date']}{RST}")
        print(f"{'═'*52}")
        print(f"  Facility   : {p['facility']}")
        print(f"  Predicted  : {G}{B}{p['predicted']}{RST} patients")
        print(f"  Range      : {p['low']} – {p['high']}")
        print(f"  Confidence : {p['confidence_pct']}%")
        print(f"  Model      : {p['model_used']}  "
              f"(blend {p['ml_blend_pct']}% ML)")
        if env:
            print(f"  Env used   : {env}")
        if args.capacity:
            print_capacity(res)
        print(f"{'═'*52}\n")
        return

    # ── Forecast ───────────────────────────────────────────────
    if args.forecast:
        results = []
        for i in pbar(range(args.days), desc="Forecasting"):
            from datetime import timedelta
            d = (pd.to_datetime(args.start) if args.start
                 else pd.Timestamp.now()) + timedelta(days=i)
            try:
                results.append(
                    core.predict_one(
                        d.strftime("%Y-%m-%d"), args.facility,
                        args.season,
                        env=env or None,
                        cap_override=cap or None,
                        events=events))
            except Exception as ex:
                print(f"\n  Day {i+1} failed: {ex}")

        hdr = (f"\n  {B}{'Date':<14} {'Day':<5} {'Pred':>6} "
               f"{'Low':>6} {'High':>6} {'Model':<7}")
        if args.capacity:
            hdr += f" {'BOR%':>6} {'ED%':>5} {'Wait':>6}"
        print(f"{hdr}{RST}")
        print(f"  {'─'*70}")

        rows = []
        for r in results:
            p   = r["prediction"]
            bor = r["bed_occupancy"]
            ed  = r["emergency_load"]
            wt  = r["waiting_times"]
            d   = pd.to_datetime(p["date"])
            line = (f"  {p['date']:<14} {d.strftime('%a'):<5} "
                    f"{G}{p['predicted']:>6}{RST} "
                    f"{p['low']:>6} {p['high']:>6} "
                    f"{p['model_used']:<7}")
            if args.capacity:
                bp = bor["projected_bor_pct"]
                ep = ed["utilisation_pct"]
                wp = wt["consultation"]
                bc = R if bp>=95 else Y if bp>=80 else G
                ec = R if ep>=95 else Y if ep>=80 else G
                wc = R if wp>=90 else Y if wp>=45 else G
                line += (f" {bc}{bp:>5.1f}%{RST}"
                         f" {ec}{ep:>4.1f}%{RST}"
                         f" {wc}{wp:>4}m{RST}")
            print(line)
            rows.append({
                "date":              p["date"],
                "day":               d.strftime("%a"),
                "facility":          p["facility"],
                "predicted":         p["predicted"],
                "low":               p["low"],
                "high":              p["high"],
                "confidence_pct":    p["confidence_pct"],
                "model":             p["model_used"],
                "bor_current_pct":   bor["current_bor_pct"],
                "bor_projected_pct": bor["projected_bor_pct"],
                "new_admissions":    bor["new_admissions"],
                "beds_free_after":   bor["beds_free_after"],
                "opd_pts_per_hr":    r["opd_load"]["patients_per_hour"],
                "opd_load_per_ctr":  r["opd_load"]["patients_per_hr_per_ctr"],
                "counters_needed":   r["opd_load"]["counters_needed"],
                "ed_util_pct":       ed["utilisation_pct"],
                "ed_new_patients":   ed["new_ed_patients"],
                "wait_reg_min":      wt["registration"],
                "wait_consult_min":  wt["consultation"],
                "wait_total_min":    wt["total"],
            })

        out = (core.EXP /
               f"forecast_{args.facility}_{datetime.now().strftime('%Y%m%d')}.csv")
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"\n  {G}Saved → {out}{RST}\n")
        return

    # ── Capacity report ────────────────────────────────────────
    if args.capacity_report:
        today = datetime.now().strftime("%Y-%m-%d")
        res   = core.predict_one(
            today, args.facility, args.season,
            env=env or None,
            cap_override=cap or None,
            events=events)
        p = res["prediction"]
        print(f"\n{B}{'═'*62}{RST}")
        print(f"{B}  CAPACITY REPORT — {today}  ({p['facility']}){RST}")
        print(f"{'═'*62}")
        print(f"  OPD predicted: {G}{B}{p['predicted']}{RST}  "
              f"({p['low']}–{p['high']})  conf={p['confidence_pct']}%")
        print_capacity(res)
        print(f"{'═'*62}\n")
        return

    # ── Export dashboard ───────────────────────────────────────
    if args.export_dashboard:
        _, st = core._load_bundle()
        path = export_dashboard(st)
        print(f"\n{G}✓ Dashboard JSON → {path}{RST}")
        print("  Open HTML dashboard → 'Load saved model' → select file\n")
        return

    ap.print_help()


if __name__ == "__main__":
    main()
