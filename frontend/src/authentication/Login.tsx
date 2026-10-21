import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useHospital } from "../HospitalContext";
import { updateCapacity } from "../api";

const BASE = "http://localhost:8000";

const KNOWN_IDS: Record<string, { name: string; lat: number; lng: number }> = {
  hospital123: { name: "Sarvodya General Hospital", lat: 28.4450, lng: 76.9970 },
  hospital321: { name: "Global Care Medical Centre", lat: 28.6329, lng: 77.2195 },
};

const DEPARTMENTS = ["Emergency", "ICU", "Surgery", "Radiology"];

function Login() {
  const [ribbonCycle, setRibbonCycle] = useState(0);
  const [hospitalId, setHospitalIdInput] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const { setHospitalId } = useHospital();

  useEffect(() => {
    setRibbonCycle(1);
  }, []);

  const triggerRibbon = () => setRibbonCycle((v) => v + 1);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (!hospitalId.trim()) {
      setError("Hospital ID is required");
      return;
    }
    if (!password.trim()) {
      setError("Password is required");
      return;
    }

    triggerRibbon();

    const id = hospitalId.trim();
    setHospitalId(id);

    // Register hospital identity (upsert — safe to call repeatedly)
    const known = KNOWN_IDS[id];
    if (known) {
      await fetch(`${BASE}/api/hospital/register-with-id`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ hospital_id: id, name: known.name, lat: known.lat, lng: known.lng }),
      }).catch(() => {});
    }

    // Seed capacity for all departments so selectHospital never returns no_capacity
    await Promise.all(
      DEPARTMENTS.map((dept) => updateCapacity(id, dept, 20, 20)),
    ).catch(() => {});

    setTimeout(() => navigate("/dashboard"), 200);
  };

  return (
    <main
      className={`dashboard-shell ${ribbonCycle > 0 ? "animate-ribbon" : ""}`}
      data-ribbon-cycle={ribbonCycle % 2}
    >
      <header className="dashboard-topbar">
        <div className="brand-block">
          <div className="brand-logo" />
          <p className="dashboard-label">Hospital Management System</p>
          <h1>CareMatrix</h1>
        </div>
      </header>

      <section className="dashboard-grid">
        <section className="welcome-panel">
          <div className="hero-cross" />
          <div className="panel-logo" />

          <p className="dashboard-label">Secure Access</p>
          <h2>Clinical Control Interface</h2>

          <p className="welcome-copy">
            Authorized personnel only. Monitor patient flow, manage admissions,
            and respond to critical demand in real-time.
          </p>

          <div className="quick-links">
            <div className="mini-action">24/7 Monitoring</div>
            <div className="mini-action">Emergency Ready</div>
            <div className="mini-action">Live Demand Map</div>
          </div>
        </section>

        <section className="workspace-panel">
          <section className="form-panel">
            <div className="section-heading">
              <div className="panel-logo" />
              <div>
                <p className="dashboard-label">Authentication</p>
                <h3>Sign In</h3>
              </div>
            </div>

            <form className="quick-form" onSubmit={handleLogin}>
              <label>
                Hospital ID
                <input
                  type="text"
                  placeholder="e.g. hospital123"
                  value={hospitalId}
                  onChange={(e) => setHospitalIdInput(e.target.value)}
                  required
                />
              </label>

              <label>
                Password
                <input
                  type="password"
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                />
              </label>

              {error && <p className="login-error">{error}</p>}

              <button type="submit" className="action-card">
                Enter System
              </button>
            </form>
          </section>
        </section>
      </section>
    </main>
  );
}

export default Login;
