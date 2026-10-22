import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useHospital } from "../HospitalContext";
import { login } from "../api";

export default function Login() {
  const navigate = useNavigate();
  const { setHospital } = useHospital();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  async function submit(event: React.FormEvent) {
    event.preventDefault(); setError("");
    try { const result = await login(username.trim(), password); setHospital(result.hospital); navigate("/dashboard"); }
    catch (err) { setError(err instanceof Error ? err.message : "Login failed"); }
  }
  return <main className="dashboard-shell"><header className="dashboard-topbar"><div className="brand-block"><div className="brand-logo" /><p className="dashboard-label">Hospital Management System</p><h1>CareMatrix</h1></div></header><section className="dashboard-grid"><section className="welcome-panel"><div className="hero-cross" /><div className="panel-logo" /><p className="dashboard-label">Secure Access</p><h2>Clinical Control Interface</h2><p className="welcome-copy">Authorized personnel only. Monitor patient flow, manage admissions, and respond to critical demand.</p><div className="quick-links"><div className="mini-action">24/7 Monitoring</div><div className="mini-action">Emergency Ready</div><div className="mini-action">Live Demand Map</div></div></section><section className="workspace-panel"><section className="form-panel"><div className="section-heading"><div className="panel-logo" /><div><p className="dashboard-label">Authentication</p><h3>Sign In</h3></div></div><form className="quick-form" onSubmit={submit}><label>Username<input type="text" placeholder="Hospital administrator username" value={username} onChange={(e) => setUsername(e.target.value)} required /></label><label>Password<input type="password" placeholder="••••••••" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>{error && <p className="login-error">{error}</p>}<button type="submit" className="action-card">Enter System</button></form></section></section></section></main>;
}
