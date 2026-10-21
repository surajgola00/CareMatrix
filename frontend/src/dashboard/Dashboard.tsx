import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import "./dashboard.css";
import {
  createPatientRequest,
  getOpenRequests,
  getPatientResponses,
  respondToPatient,
  selectHospital,
  denyResponse,
  getAcceptanceStatus,
  getHospitalInfo,
  getSurgeAlerts,
} from "../api";
import type { SurgeAlert } from "../api";
import { useHospital } from "../HospitalContext";

type TransferStatus =
  | "PENDING"
  | "ACCEPTED_PENDING"
  | "CONFIRMED"
  | "DENIED"
  | "DECLINED";

type Transfer = {
  id: string;
  department: string;
  priority: string;
  lat: number;
  lng: number;
  status: TransferStatus;
  receivedAt: string;
};

type AdmittedRecord = {
  id: string;
  department: string;
  priority: string;
  admittedAt: string;
};

type RegisteredPatient = {
  patientId: string;
  name: string;
  department: string;
  priority: string;
  matches: { hospital_id: string; name: string; decided: boolean }[];
  confirmed: string | null;
};

function nowTime() {
  return new Date().toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
  });
}

function Dashboard() {
  const [ribbonCycle, setRibbonCycle] = useState(0);
  const navigate = useNavigate();
  const { hospitalId } = useHospital();

  const [hospitalName, setHospitalName] = useState("CareMatrix Hospital");
  const [hospitalShort, setHospitalShort] = useState("CM");
  const [hospitalLocation, setHospitalLocation] = useState("");

  const [transfers, setTransfers] = useState<Transfer[]>([]);
  const [admitted, setAdmitted] = useState<AdmittedRecord[]>([]);
  const [registered, setRegistered] = useState<RegisteredPatient[]>([]);
  const [surgeAlerts, setSurgeAlerts] = useState<SurgeAlert[]>([]);
  const [deniedNotifs, setDeniedNotifs] = useState<string[]>([]);

  const seenIds = useRef<Set<string>>(new Set());
  const ownPatientIds = useRef<Set<string>>(new Set());

  const registeredRef = useRef<RegisteredPatient[]>([]);
  registeredRef.current = registered;

  // Ref keeps a live snapshot of ACCEPTED_PENDING transfers.
  // The acceptance-status polling effect reads from here so it never
  // needs `transfers` as a dependency — preventing the interval from
  // being torn down and restarted every 3 s (which caused the stuck state).
  const pendingTransfersRef = useRef<Transfer[]>([]);
  pendingTransfersRef.current = transfers.filter(
    (t) => t.status === "ACCEPTED_PENDING",
  );

  const [formData, setFormData] = useState({
    name: "",
    age: "",
    contact: "",
    bloodGroup: "O+",
    priority: "High",
    condition: "",
    department: "Emergency",
  });

  const triggerRibbon = () => setRibbonCycle((v) => v + 1);

  // ── Hospital identity ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!hospitalId) return;
    getHospitalInfo(hospitalId)
      .then((info) => {
        setHospitalName(info.name);
        setHospitalShort(info.short);
        setHospitalLocation(info.location);
      })
      .catch(() => {});
  }, [hospitalId]);

  // ── Surge alerts (refresh every 5 min) ────────────────────────────────────
  useEffect(() => {
    if (!hospitalId) return;
    const load = () =>
      getSurgeAlerts(hospitalId)
        .then(setSurgeAlerts)
        .catch(() => {});
    load();
    const iv = setInterval(load, 300_000);
    return () => clearInterval(iv);
  }, [hospitalId]);

  // ── Poll open transfer requests every 3 s (Hospital B view) ───────────────
  useEffect(() => {
    setRibbonCycle(1);

    const poll = async () => {
      const open = await getOpenRequests().catch(() => []);
      const openIds = new Set(open.map((r) => r.id));

      setTransfers((prev) =>
        prev.filter((t) => {
          if (t.status === "ACCEPTED_PENDING") return true;
          if (t.status === "CONFIRMED" || t.status === "DENIED") return true;
          if (t.status !== "PENDING") return false;
          return openIds.has(t.id);
        }),
      );

      const fresh = open.filter(
        (r) => !seenIds.current.has(r.id) && !ownPatientIds.current.has(r.id),
      );
      if (fresh.length === 0) return;

      fresh.forEach((r) => seenIds.current.add(r.id));
      setTransfers((prev) =>
        [
          ...fresh.map((r) => ({
            id: r.id,
            department: r.department,
            priority: r.priority,
            lat: r.lat,
            lng: r.lng,
            status: "PENDING" as const,
            receivedAt: nowTime(),
          })),
          ...prev,
        ].slice(0, 50),
      );
    };

    poll();
    const iv = setInterval(poll, 3000);
    return () => clearInterval(iv);
  }, []);

  // ── Poll acceptance-status for ACCEPTED_PENDING transfers (Hospital B) ────
  // Reads from pendingTransfersRef — NOT from transfers state — so this
  // interval mounts once and stays alive. `transfers` changing every 3 s
  // no longer tears it down before it can fire.
  useEffect(() => {
    if (!hospitalId) return;

    const poll = async () => {
      const pending = pendingTransfersRef.current;
      if (pending.length === 0) return;

      for (const t of pending) {
        const res = await getAcceptanceStatus(t.id, hospitalId).catch(
          () => null,
        );
        if (!res) continue;

        if (res.status === "confirmed") {
          setAdmitted((prev) => {
            if (prev.some((a) => a.id === t.id.slice(0, 8))) return prev;
            return [
              {
                id: t.id.slice(0, 8),
                department: t.department,
                priority: t.priority,
                admittedAt: nowTime(),
              },
              ...prev,
            ];
          });
          setTransfers((prev) =>
            prev.map((r) =>
              r.id === t.id ? { ...r, status: "CONFIRMED" as const } : r,
            ),
          );
          setTimeout(
            () => setTransfers((prev) => prev.filter((r) => r.id !== t.id)),
            3000,
          );
        } else if (res.status === "denied_by_source") {
          setDeniedNotifs((prev) => [
            `Transfer denied by source — ${t.department} (${t.priority})`,
            ...prev,
          ]);
          setTransfers((prev) =>
            prev.map((r) =>
              r.id === t.id ? { ...r, status: "DENIED" as const } : r,
            ),
          );
          setTimeout(
            () => setTransfers((prev) => prev.filter((r) => r.id !== t.id)),
            4000,
          );
        }
      }
    };

    const iv = setInterval(poll, 3000);
    return () => clearInterval(iv);
  }, [hospitalId]); // no `transfers` here — uses ref instead

  // ── Poll responses for outgoing patients every 4 s (Hospital A view) ──────
  useEffect(() => {
    const poll = async () => {
      for (const p of registeredRef.current) {
        if (p.confirmed) continue;
        const responses = await getPatientResponses(p.patientId).catch(
          () => [],
        );
        if (responses.length === 0) continue;
        setRegistered((prev) =>
          prev.map((x) => {
            if (x.patientId !== p.patientId) return x;
            const existingIds = new Set(x.matches.map((m) => m.hospital_id));
            const newMatches = responses
              .filter((r) => !existingIds.has(r.hospital_id))
              .map((r) => ({
                hospital_id: r.hospital_id,
                name: r.name,
                decided: false,
              }));
            return { ...x, matches: [...x.matches, ...newMatches] };
          }),
        );
      }
    };
    const iv = setInterval(poll, 4000);
    return () => clearInterval(iv);
  }, []);

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>,
  ) => setFormData({ ...formData, [e.target.name]: e.target.value });

  // ── Register new outgoing patient (Hospital A) ─────────────────────────────
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formData.name || !formData.age || !formData.contact) {
      alert("Please fill all required fields");
      return;
    }
    triggerRibbon();
    const res = await createPatientRequest(
      formData.department,
      formData.priority,
      28.6,
      77.1,
    ).catch(() => null);
    if (!res) {
      alert("Backend unreachable — patient not registered");
      return;
    }
    ownPatientIds.current.add(res.patient_id);
    seenIds.current.add(res.patient_id);

    setRegistered((prev) => [
      {
        patientId: res.patient_id,
        name: formData.name,
        department: formData.department,
        priority: formData.priority,
        matches: [],
        confirmed: null,
      },
      ...prev,
    ]);
    setFormData({
      name: "",
      age: "",
      contact: "",
      bloodGroup: "O+",
      priority: "High",
      condition: "",
      department: "Emergency",
    });
  };

  // ── Hospital B: Accept or Decline an incoming transfer ────────────────────
  const handleDecision = async (
    transfer: Transfer,
    decision: "ACCEPTED_PENDING" | "DECLINED",
  ) => {
    if (!hospitalId) return;

    if (decision === "ACCEPTED_PENDING") {
      await respondToPatient(transfer.id, hospitalId, "accepted").catch(
        () => {},
      );
      setTransfers((prev) =>
        prev.map((r) =>
          r.id === transfer.id
            ? { ...r, status: "ACCEPTED_PENDING" as const }
            : r,
        ),
      );
    } else {
      await respondToPatient(transfer.id, hospitalId, "rejected").catch(
        () => {},
      );
      setTransfers((prev) =>
        prev.map((r) =>
          r.id === transfer.id ? { ...r, status: "DECLINED" as const } : r,
        ),
      );
      setTimeout(
        () => setTransfers((prev) => prev.filter((r) => r.id !== transfer.id)),
        1500,
      );
    }
  };

  // ── Hospital A: Confirm a specific accepting hospital ──────────────────────
  const handleConfirm = async (
    patientId: string,
    hId: string,
    hName: string,
  ) => {
    const res = await selectHospital(patientId, hId).catch(() => null);
    if (res?.status === "assigned") {
      setRegistered((prev) =>
        prev.map((p) =>
          p.patientId === patientId
            ? {
                ...p,
                confirmed: hId,
                matches: p.matches.map((m) => ({ ...m, decided: true })),
              }
            : p,
        ),
      );
    } else if (res?.status === "no_capacity") {
      alert(`${hName} no longer has capacity. Choose another hospital.`);
      setRegistered((prev) =>
        prev.map((p) =>
          p.patientId === patientId
            ? {
                ...p,
                matches: p.matches.map((m) =>
                  m.hospital_id === hId ? { ...m, decided: true } : m,
                ),
              }
            : p,
        ),
      );
    } else if (res?.status === "already_assigned") {
      setRegistered((prev) =>
        prev.map((p) =>
          p.patientId === patientId ? { ...p, confirmed: hId } : p,
        ),
      );
    }
  };

  // ── Hospital A: Deny a specific accepting hospital ─────────────────────────
  const handleDeny = async (patientId: string, hId: string) => {
    await denyResponse(patientId, hId).catch(() => {});
    setRegistered((prev) =>
      prev.map((p) =>
        p.patientId === patientId
          ? {
              ...p,
              matches: p.matches.map((m) =>
                m.hospital_id === hId ? { ...m, decided: true } : m,
              ),
            }
          : p,
      ),
    );
  };

  const surgeColor = (level: string) => {
    if (level === "HIGH") return "#8f1d1d";
    if (level === "MODERATE") return "#c47a1d";
    return "#2e7d32";
  };

  return (
    <main
      className={`dashboard-shell ${ribbonCycle > 0 ? "animate-ribbon" : ""}`}
      data-ribbon-cycle={ribbonCycle % 2}
    >
      <header className="dashboard-topbar">
        <div className="brand-block">
          <div className="brand-logo" />
          <div className="brand-text-block">
            <p className="dashboard-label">Hospital Management System</p>
            <h1>{hospitalName}</h1>
            {hospitalLocation && (
              <p className="hospital-location-sub">{hospitalLocation}</p>
            )}
          </div>
        </div>
        <div className="account-menu">
          <div className="account-avatar">
            {hospitalShort.slice(0, 2).toUpperCase()}
          </div>
          <button
            className="signout-button"
            onClick={() => {
              localStorage.removeItem("cm_hospital_id");
              navigate("/login");
            }}
          >
            Sign Out
          </button>
        </div>
      </header>

      <section className="dashboard-grid">
        <section className="welcome-panel">
          <div className="hero-cross" />
          <div className="panel-logo" />
          <p className="dashboard-label">Emergency Access</p>
          <h2>Welcome</h2>
          <p className="welcome-copy">Rapid intake controls.</p>
          <div className="quick-links">
            <button className="mini-action">Register Patient</button>
            <button
              className="mini-action"
              onClick={() => navigate("/inventory")}
            >
              Inventory Management
            </button>
            <button className="mini-action">Emergency Alert</button>
            <button
              className="mini-action"
              onClick={() => navigate("/heatmap")}
            >
              Heat Map
            </button>
            <button
              className="mini-action"
              onClick={() => navigate("/prediction")}
            >
              Surge Prediction
            </button>
          </div>
        </section>

        <section className="workspace-panel split">
          {/* ── FORM ── */}
          <section className="form-panel">
            <div className="section-heading">
              <div className="panel-logo" />
              <div>
                <p className="dashboard-label">Quick Register</p>
                <h3>New Patient</h3>
              </div>
            </div>

            <form className="quick-form" onSubmit={handleSubmit}>
              <label>
                Patient Name
                <input
                  name="name"
                  value={formData.name}
                  onChange={handleChange}
                />
              </label>

              <div className="form-grid">
                <input
                  name="age"
                  value={formData.age}
                  onChange={handleChange}
                  placeholder="Age"
                />
                <input
                  name="contact"
                  value={formData.contact}
                  onChange={handleChange}
                  placeholder="Contact"
                />
              </div>

              <div className="form-grid">
                <select
                  name="bloodGroup"
                  value={formData.bloodGroup}
                  onChange={handleChange}
                >
                  <option>O+</option>
                  <option>O-</option>
                  <option>A+</option>
                  <option>B+</option>
                </select>
                <select
                  name="priority"
                  value={formData.priority}
                  onChange={handleChange}
                >
                  <option>Critical</option>
                  <option>High</option>
                  <option>Moderate</option>
                  <option>Low</option>
                </select>
              </div>

              <label>
                Condition
                <input
                  name="condition"
                  value={formData.condition}
                  onChange={handleChange}
                />
              </label>

              <select
                name="department"
                value={formData.department}
                onChange={handleChange}
              >
                <option>Emergency</option>
                <option>ICU</option>
                <option>Surgery</option>
                <option>Radiology</option>
              </select>

              <button className="action-card">Register Patient</button>
            </form>
          </section>

          {/* ── NOTIFICATIONS ── */}
          <section className="notification-panel">
            {/* Surge Intelligence */}
            {surgeAlerts.length > 0 && (
              <div className="notif-block surge-alert-block">
                <h3>⚠ Surge Intelligence</h3>
                <div className="notif-scroll">
                  {surgeAlerts.map((alert) => (
                    <div key={alert.id} className="surge-alert-item">
                      <div className="surge-alert-row">
                        <span
                          className="surge-level-badge"
                          style={{
                            background: surgeColor(alert.level),
                            color: "#f2f0ea",
                          }}
                        >
                          {alert.level}
                        </span>
                        <span className="surge-code">
                          {alert.code.replace(/_/g, " ")}
                        </span>
                      </div>
                      <p className="surge-message">{alert.message}</p>
                      <p className="surge-source">Source: {alert.source}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Denied notifications (Hospital B) */}
            {deniedNotifs.length > 0 && (
              <div className="notif-block denied-notif-block">
                <h3>✕ Transfer Denied by Source</h3>
                <div className="notif-scroll">
                  {deniedNotifs.map((msg, i) => (
                    <div key={i} className="denied-notif-item">
                      <p className="denied-notif-msg">{msg}</p>
                      <button
                        className="denied-dismiss"
                        onClick={() =>
                          setDeniedNotifs((prev) =>
                            prev.filter((_, j) => j !== i),
                          )
                        }
                      >
                        ✕
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Incoming Transfers (Hospital B view) */}
            <div className="notif-block">
              <h3>Incoming Transfers</h3>
              <div className="notif-scroll">
                {transfers.length === 0 && (
                  <p className="notif-empty">No open requests</p>
                )}
                {transfers.map((r) => (
                  <div
                    key={r.id}
                    className={`notif-item ${
                      r.status === "CONFIRMED" ||
                      r.status === "DECLINED" ||
                      r.status === "DENIED"
                        ? "notif-item-fading"
                        : ""
                    }`}
                  >
                    <div className="notif-details">
                      <div className="notif-row">
                        <strong>{r.department}</strong>
                        <span
                          className={`notif-badge notif-priority-${r.priority.toLowerCase()}`}
                        >
                          {r.priority}
                        </span>
                      </div>
                      <p className="notif-sub">
                        ID: {r.id.slice(0, 8)}… · {r.receivedAt}
                      </p>
                      <p className="notif-sub">
                        {r.lat.toFixed(3)}, {r.lng.toFixed(3)}
                      </p>
                      {r.status === "ACCEPTED_PENDING" && (
                        <p className="notif-status status-accepted-pending">
                          ⏳ Awaiting source confirmation…
                        </p>
                      )}
                      {r.status === "CONFIRMED" && (
                        <p className="notif-status status-admitted">
                          ✓ Confirmed — patient incoming
                        </p>
                      )}
                      {r.status === "DENIED" && (
                        <p className="notif-status status-declined">
                          ✕ Denied by source hospital
                        </p>
                      )}
                      {r.status === "DECLINED" && (
                        <p className="notif-status status-declined">
                          ✕ Declined
                        </p>
                      )}
                    </div>

                    {r.status === "PENDING" && (
                      <div className="notif-actions">
                        <button
                          className="notif-btn-admit"
                          onClick={() => handleDecision(r, "ACCEPTED_PENDING")}
                        >
                          ✓ Accept
                        </button>
                        <button
                          className="notif-btn-decline"
                          onClick={() => handleDecision(r, "DECLINED")}
                        >
                          ✕ Decline
                        </button>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Patient Status — outgoing (Hospital A) + locally admitted */}
            <div className="notif-block">
              <h3>Patient Status</h3>
              <div className="notif-scroll">
                {admitted.map((a) => (
                  <div key={a.id} className="notif-item notif-item-admitted">
                    <div className="notif-details">
                      <strong>{a.department}</strong>
                      <span className="notif-badge notif-badge-priority">
                        {a.priority}
                      </span>
                      <p className="notif-sub">
                        ID: {a.id}… · Admitted {a.admittedAt}
                      </p>
                    </div>
                    <span className="status-admitted">✓ ADMITTED</span>
                  </div>
                ))}

                {registered.map((p) => {
                  const undecided = p.matches.filter((m) => !m.decided);
                  return (
                    <div
                      key={p.patientId}
                      className="notif-item notif-item-outgoing"
                    >
                      <div className="notif-details">
                        <div className="notif-row">
                          <strong>{p.name}</strong>
                          <span
                            className={`notif-badge notif-priority-${p.priority.toLowerCase()}`}
                          >
                            {p.priority}
                          </span>
                        </div>
                        <p className="notif-sub">
                          {p.department} · {p.patientId.slice(0, 8)}…
                        </p>

                        {p.confirmed ? (
                          <p className="notif-confirm-done">
                            ✓ Transfer confirmed
                          </p>
                        ) : undecided.length === 0 ? (
                          <p className="notif-sub status-pending">
                            {p.matches.length === 0
                              ? "Broadcasting — awaiting responses…"
                              : "All responses decided — awaiting more…"}
                          </p>
                        ) : (
                          <>
                            <p className="notif-confirm-label">
                              Hospitals accepting — confirm or deny:
                            </p>
                            {undecided.map((m) => (
                              <div
                                key={m.hospital_id}
                                className="transfer-decision-row"
                              >
                                <span className="transfer-hosp-name">
                                  {m.name}
                                </span>
                                <div className="transfer-decision-btns">
                                  <button
                                    className="td-btn-confirm"
                                    onClick={() =>
                                      handleConfirm(
                                        p.patientId,
                                        m.hospital_id,
                                        m.name,
                                      )
                                    }
                                  >
                                    ✓ Confirm
                                  </button>
                                  <button
                                    className="td-btn-deny"
                                    onClick={() =>
                                      handleDeny(p.patientId, m.hospital_id)
                                    }
                                  >
                                    ✕ Deny
                                  </button>
                                </div>
                              </div>
                            ))}
                          </>
                        )}
                      </div>
                    </div>
                  );
                })}

                {admitted.length === 0 && registered.length === 0 && (
                  <p className="notif-empty">No activity yet</p>
                )}
              </div>
            </div>
          </section>
        </section>
      </section>
    </main>
  );
}

export default Dashboard;
