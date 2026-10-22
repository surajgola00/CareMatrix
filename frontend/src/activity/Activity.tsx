import { useEffect, useState } from "react";
import { useHospital } from "../HospitalContext";
import { hospitalLogo } from "../hospitalLogos";

type Transfer = { id: string; department: string; priority: string; status: string; notified: number; responded: number; accepted: number; rejected: number };

export default function Activity() {
  const { hospitalId, hospital } = useHospital();
  const [items, setItems] = useState<Transfer[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!hospitalId) return;
    let active = true;
    const load = async () => {
      const r = await fetch(`${import.meta.env.VITE_API_BASE ?? "http://localhost:8000"}/api/transfer/outgoing`, { credentials: "include" });
      if (!r.ok) throw new Error("Could not load activity");
      if (active) setItems(await r.json());
    };
    load().catch((e) => active && setError(e.message));
    const id = window.setInterval(() => load().catch(() => {}), 5000);
    return () => { active = false; window.clearInterval(id); };
  }, [hospitalId]);
  return <main className="dashboard-shell"><header className="dashboard-topbar"><div className="brand-block"><img className="brand-logo" src={hospitalLogo(hospitalId)} alt="" /><div><p className="dashboard-label">Transfers & Activity</p><h1>{hospital?.name ?? "CareMatrix"}</h1></div></div></header><section className="dashboard-grid"><section className="workspace-panel"><section className="form-panel"><h3>My Requests & Transfers</h3>{error && <p className="login-error">{error}</p>}{!error && items.length === 0 && <p className="notif-empty">No outgoing transfer activity.</p>}{items.map((item) => <article className="activity-row" key={item.id}><strong>{item.department} · {item.priority}</strong><span>{item.status}</span><small>Notified {item.notified ?? 0} · Responses {item.responded ?? 0} · Accepted {item.accepted ?? 0} · Rejected {item.rejected ?? 0}</small></article>)}</section></section></section></main>;
}
