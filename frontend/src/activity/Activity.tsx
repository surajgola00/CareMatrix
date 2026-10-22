import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { hospitalLogo } from "../hospitalLogos";
import { useHospital } from "../HospitalContext";

type ActivityItem = { id: string; kind: "patient" | "resource"; stage: string | null; status: string; department: string; priority: string; created_at: number; origin_name: string; destination_name?: string };
type Detail = { details: Record<string, unknown>; events: { event_type: string; created_at: number; actor_hospital_id?: string }[] };

const transferStages = ["accepted", "ambulance_assigned", "ambulance_dispatched", "patient_picked_up", "in_transit", "arrived", "admitted"];
const resourceStages = ["accepted", "preparing", "dispatched", "in_transit", "delivered", "receipt_confirmed"];

export default function Activity() {
  const navigate = useNavigate();
  const { hospitalId, hospital } = useHospital();
  const [items, setItems] = useState<ActivityItem[]>([]);
  const [filter, setFilter] = useState("all");
  const [expanded, setExpanded] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, Detail>>({});
  const [error, setError] = useState("");
  const base = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

  const load = async () => {
    const r = await fetch(`${base}/api/activity`, { credentials: "include" });
    if (!r.ok) throw new Error("Could not load activity");
    setItems(await r.json());
  };
  useEffect(() => { if (!hospitalId) return; load().catch((e) => setError(e.message)); const timer = window.setInterval(() => load().catch(() => {}), 5000); return () => window.clearInterval(timer); }, [hospitalId]);

  const filtered = useMemo(() => items.filter((item) => {
    if (filter === "incoming") return item.destination_name === hospital?.name;
    if (filter === "outgoing") return item.origin_name === hospital?.name;
    if (filter === "patient") return item.kind === "patient";
    if (filter === "resource") return item.kind === "resource";
    if (filter === "active") return item.stage !== "admitted" && item.stage !== "receipt_confirmed";
    if (filter === "completed") return item.stage === "admitted" || item.stage === "receipt_confirmed";
    return true;
  }), [items, filter, hospital?.name]);
  const counts = { active: items.filter((i) => i.stage !== "admitted" && i.stage !== "receipt_confirmed").length, incoming: items.filter((i) => i.destination_name === hospital?.name).length, outgoing: items.filter((i) => i.origin_name === hospital?.name).length, resources: items.filter((i) => i.kind === "resource" && i.stage !== "receipt_confirmed").length };

  const toggle = async (item: ActivityItem) => {
    const key = `${item.kind}:${item.id}`;
    if (expanded === key) { setExpanded(null); return; }
    setExpanded(`${item.kind}:${item.id}`);
    if (!details[key]) { const r = await fetch(`${base}/api/activity/${item.kind}/${item.id}`, { credentials: "include" }); if (r.ok) { const data = await r.json(); setDetails((prev) => ({ ...prev, [key]: data })); } }
  };
  const updateStage = async (item: ActivityItem, stage: string) => { const r = await fetch(`${base}/api/activity/${item.kind}/${item.id}/stage?stage=${stage}`, { method: "POST", credentials: "include" }); if (r.ok) load(); };
  const stages = (item: ActivityItem) => item.kind === "patient" ? transferStages : resourceStages;

  return <main className="dashboard-shell"><header className="dashboard-topbar"><div className="brand-block"><img className="brand-logo" src={hospitalLogo(hospitalId)} alt="" /><div><p className="dashboard-label">Transfers & Activity</p><h1>{hospital?.name ?? "CareMatrix"}</h1></div></div><button className="signout-button" onClick={() => navigate("/dashboard")}>Back</button></header><section className="activity-page"><div className="activity-summary"><div><b>{counts.active}</b><span>Active activities</span></div><div><b>{counts.incoming}</b><span>Incoming patients</span></div><div><b>{counts.outgoing}</b><span>Outgoing patients</span></div><div><b>{counts.resources}</b><span>Resource sharing</span></div></div><div className="activity-filters">{[["all","All Activity"],["incoming","Incoming"],["outgoing","Outgoing"],["patient","Patient Transfers"],["resource","Resource Sharing"],["active","Active"],["completed","Completed"]].map(([key,label]) => <button className={filter === key ? "active" : ""} key={key} onClick={() => setFilter(key)}>{label}</button>)}</div>{error && <p className="login-error">{error}</p>}{filtered.length === 0 && !error && <p className="notif-empty">No matching activity.</p>}{filtered.map((item) => { const key = `${item.kind}:${item.id}`; const detail = details[key]; const current = stages(item).indexOf(item.stage ?? "accepted"); return <article className="activity-card" key={key}><div className="activity-card-head"><div><span className="activity-kind">{item.kind === "patient" ? "PATIENT TRANSFER" : "RESOURCE SHARING"}</span><h3>{item.department} · {item.id.slice(0, 8)}</h3><p>{item.origin_name} → {item.destination_name ?? "Awaiting provider"}</p></div><div><strong>{(item.stage ?? item.status).replaceAll("_", " ").toUpperCase()}</strong><small>{new Date(item.created_at * 1000).toLocaleString()}</small></div></div><button className="activity-details-button" onClick={() => toggle(item)}>{expanded === key ? "Hide Details" : "View Details"}</button>{expanded === key && <div className="activity-detail"><div className="activity-timeline">{stages(item).map((stage, index) => <div className={`timeline-step ${index <= current ? "complete" : "pending"}`} key={stage}><span>{index <= current ? "✓" : "○"}</span><b>{stage.replaceAll("_", " ")}</b>{index <= current && detail?.events?.find((event) => event.event_type === stage) && <small>{new Date((detail.events.find((event) => event.event_type === stage)?.created_at ?? 0) * 1000).toLocaleString()}</small>}</div>)}</div><div className="activity-actions">{stages(item).filter((_, index) => index === current + 1).map((next) => <button key={next} onClick={() => updateStage(item, next)}>Confirm {next.replaceAll("_", " ")}</button>)}</div></div>}</article>; })}</section></main>;
}
