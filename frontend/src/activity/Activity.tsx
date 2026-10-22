import { useEffect, useState } from "react";
import { useHospital } from "../HospitalContext";
import { hospitalLogo } from "../hospitalLogos";

type Transfer = { id: string; department: string; priority: string; status: string; notified: number; responded: number; accepted: number; rejected: number };
type Event = { event_type: string; created_at: number; actor_hospital_id?: string };

export default function Activity() {
  const { hospitalId, hospital } = useHospital();
  const [items, setItems] = useState<Transfer[]>([]);
  const [error, setError] = useState("");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [timelines, setTimelines] = useState<Record<string, Event[]>>({});
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
  const toggle = async (id: string) => {
    if (expanded === id) { setExpanded(null); return; }
    setExpanded(id);
    if (!timelines[id]) {
      const r = await fetch(`${import.meta.env.VITE_API_BASE ?? "http://localhost:8000"}/api/transfer/${id}/timeline`, { credentials: "include" });
      if (r.ok) { const events = await r.json(); setTimelines((prev) => ({ ...prev, [id]: events })); }
    }
  };
  return <main className="dashboard-shell"><header className="dashboard-topbar"><div className="brand-block"><img className="brand-logo" src={hospitalLogo(hospitalId)} alt="" /><div><p className="dashboard-label">Transfers & Activity</p><h1>{hospital?.name ?? "CareMatrix"}</h1></div></div></header><section className="dashboard-grid"><section className="workspace-panel"><section className="form-panel"><h3>Transfers & Activity</h3>{error && <p className="login-error">{error}</p>}{!error && items.length === 0 && <p className="notif-empty">No transfer activity.</p>}{items.map((item) => <article className="activity-row" key={item.id} onClick={() => toggle(item.id)}><div><strong>{item.department} · {item.priority}</strong><span>{item.status}</span><small>Notified {item.notified ?? 0} · Responses {item.responded ?? 0} · Accepted {item.accepted ?? 0} · Rejected {item.rejected ?? 0}</small></div>{expanded === item.id && <div className="activity-timeline">{(timelines[item.id] ?? []).map((event) => <div className="timeline-step" key={`${event.event_type}-${event.created_at}`}><b>{event.event_type.replaceAll("_", " ")}</b><small>{new Date(event.created_at * 1000).toLocaleString()}</small></div>)}</div>}</article>)}</section></section></section></main>;
}
