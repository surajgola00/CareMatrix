import React, { useEffect, useRef, useState } from "react";
import { MapContainer, TileLayer, Circle, CircleMarker, Tooltip } from "react-leaflet";
import "./heatmap.css";
import { useNavigate } from "react-router-dom";
import { getHeatmap } from "../api";

type Hospital = {
  id: string;
  name: string;
  lat: number;
  lng: number;
  demand: number;
  total: number;
  available: number;
};

function zoneColor(demand: number): { fill: string; stroke: string; label: string } {
  if (demand >= 80) return { fill: "#c0392b", stroke: "#8f1d1d", label: "CRITICAL" };
  if (demand >= 65) return { fill: "#e67e22", stroke: "#c47a1d", label: "HIGH" };
  if (demand >= 45) return { fill: "#f1c40f", stroke: "#b7950b", label: "MODERATE" };
  return { fill: "#27ae60", stroke: "#1a7a3f", label: "NORMAL" };
}

function statusLabel(demand: number): string {
  if (demand >= 80) return "Critical Surge";
  if (demand >= 65) return "High Demand";
  if (demand >= 45) return "Moderate Load";
  return "Stable";
}

function circleRadius(total: number): number {
  // Radius in metres — scale by hospital size
  if (total >= 2000) return 2200;
  if (total >= 1000) return 1600;
  if (total >= 500)  return 1200;
  return 900;
}

export default function HeatMapPage() {
  const mapRef = useRef(null);
  const navigate = useNavigate();
  const [selected, setSelected] = useState<Hospital | null>(null);
  const [hospitals, setHospitals] = useState<Hospital[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"ALL" | "CRITICAL" | "HIGH" | "MODERATE" | "NORMAL">("ALL");

  useEffect(() => {
    const load = async () => {
      const data = await getHeatmap().catch(() => []);
      setHospitals(
        data.map((h) => ({
          id: h.id, name: h.name, lat: h.lat, lng: h.lng,
          demand: h.demand, total: h.total, available: h.available,
        })),
      );
      setLoading(false);
    };
    load();
    const iv = setInterval(load, 10000);
    return () => clearInterval(iv);
  }, []);

  const visible = hospitals.filter((h) => {
    if (filter === "ALL") return true;
    return zoneColor(h.demand).label === filter;
  });

  const criticalCount = hospitals.filter((h) => h.demand >= 80).length;
  const highCount = hospitals.filter((h) => h.demand >= 65 && h.demand < 80).length;
  const modCount = hospitals.filter((h) => h.demand >= 45 && h.demand < 65).length;
  const normCount = hospitals.filter((h) => h.demand < 45).length;

  return (
    <div className="heatmap-shell">
      <header className="heatmap-header">
        <div className="heatmap-header-left">
          <h2>Demand Intelligence — NCR Hospital Network</h2>
          <p className="heatmap-sub">Live resource utilisation · 10-second refresh</p>
        </div>
        <div className="heatmap-header-right">
          <div className="heatmap-stats">
            <button
              className={`stat-chip stat-critical ${filter === "CRITICAL" ? "active" : ""}`}
              onClick={() => setFilter(filter === "CRITICAL" ? "ALL" : "CRITICAL")}
            >
              <span className="chip-dot" style={{ background: "#c0392b" }} />
              {criticalCount} Critical
            </button>
            <button
              className={`stat-chip stat-high ${filter === "HIGH" ? "active" : ""}`}
              onClick={() => setFilter(filter === "HIGH" ? "ALL" : "HIGH")}
            >
              <span className="chip-dot" style={{ background: "#e67e22" }} />
              {highCount} High
            </button>
            <button
              className={`stat-chip stat-mod ${filter === "MODERATE" ? "active" : ""}`}
              onClick={() => setFilter(filter === "MODERATE" ? "ALL" : "MODERATE")}
            >
              <span className="chip-dot" style={{ background: "#f1c40f" }} />
              {modCount} Moderate
            </button>
            <button
              className={`stat-chip stat-norm ${filter === "NORMAL" ? "active" : ""}`}
              onClick={() => setFilter(filter === "NORMAL" ? "ALL" : "NORMAL")}
            >
              <span className="chip-dot" style={{ background: "#27ae60" }} />
              {normCount} Normal
            </button>
          </div>
          <button className="back-button" onClick={() => navigate("/dashboard")}>
            ← Back
          </button>
        </div>
      </header>

      <div className="heatmap-body">
        <div className="map-container">
          {loading ? (
            <div className="heatmap-loading">
              <span className="loading-spinner" />
              Loading hospital network…
            </div>
          ) : (
            <MapContainer
              ref={mapRef}
              center={[28.57, 77.18]}
              zoom={11}
              className="heatmap-map"
            >
              <TileLayer
                attribution="&copy; OpenStreetMap contributors"
                url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
              />
              {visible.map((h) => {
                const { fill, stroke } = zoneColor(h.demand);
                const isSelected = selected?.id === h.id;
                return (
                  <React.Fragment key={h.id}>
                    {/* Translucent zone circle */}
                    <Circle
                      center={[h.lat, h.lng]}
                      radius={circleRadius(h.total)}
                      pathOptions={{
                        color: stroke,
                        fillColor: fill,
                        fillOpacity: isSelected ? 0.38 : 0.22,
                        weight: isSelected ? 2.5 : 1.5,
                        dashArray: isSelected ? undefined : "6 4",
                      }}
                    />
                    {/* Solid pin marker */}
                    <CircleMarker
                      center={[h.lat, h.lng]}
                      radius={isSelected ? 11 : 8}
                      pathOptions={{
                        color: "#111",
                        fillColor: fill,
                        fillOpacity: 1,
                        weight: isSelected ? 3 : 2,
                      }}
                      eventHandlers={{ click: () => setSelected(h) }}
                    >
                      <Tooltip direction="top" offset={[0, -10]} opacity={0.95}>
                        <div className="map-tooltip">
                          <strong>{h.name}</strong>
                          <span>{h.demand}% utilised · {h.available} beds free</span>
                        </div>
                      </Tooltip>
                    </CircleMarker>
                  </React.Fragment>
                );
              })}
            </MapContainer>
          )}
        </div>

        <div className="info-panel">
          {/* Legend */}
          <div className="legend-block">
            <p className="legend-title">Zone Legend</p>
            <div className="legend-row"><span className="legend-swatch" style={{ background: "#c0392b" }} /><span>≥80% — Critical Surge</span></div>
            <div className="legend-row"><span className="legend-swatch" style={{ background: "#e67e22" }} /><span>65–79% — High Demand</span></div>
            <div className="legend-row"><span className="legend-swatch" style={{ background: "#f1c40f" }} /><span>45–64% — Moderate Load</span></div>
            <div className="legend-row"><span className="legend-swatch" style={{ background: "#27ae60" }} /><span>&lt;45% — Stable / Normal</span></div>
          </div>

          {/* Hospital list */}
          <div className="hospital-list">
            {hospitals
              .filter((h) => filter === "ALL" || zoneColor(h.demand).label === filter)
              .sort((a, b) => b.demand - a.demand)
              .map((h) => {
                const { fill, label } = zoneColor(h.demand);
                return (
                  <div
                    key={h.id}
                    className={`hospital-row ${selected?.id === h.id ? "hospital-row-selected" : ""}`}
                    onClick={() => setSelected(selected?.id === h.id ? null : h)}
                  >
                    <div className="hosp-row-left">
                      <span className="hosp-demand-dot" style={{ background: fill }} />
                      <span className="hosp-name">{h.name}</span>
                    </div>
                    <span className="hosp-demand-val" style={{ color: fill }}>{h.demand}%</span>
                  </div>
                );
              })}
          </div>

          {/* Detail card */}
          {selected && (() => {
            const { fill, stroke, label } = zoneColor(selected.demand);
            const occupied = selected.total - selected.available;
            return (
              <div className="info-card" style={{ borderColor: stroke, boxShadow: `6px 6px 0 ${stroke}` }}>
                <div className="info-card-header" style={{ borderBottomColor: stroke }}>
                  <h3>{selected.name}</h3>
                  <span className="info-status-badge" style={{ background: fill }}>{label}</span>
                </div>

                <div className="info-metric">
                  <span className="metric-label">Utilisation</span>
                  <span className="metric-val" style={{ color: fill }}>{selected.demand}%</span>
                </div>
                <div className="demand-bar-wrap">
                  <div
                    className="demand-bar-fill"
                    style={{ width: `${selected.demand}%`, background: fill }}
                  />
                </div>

                <div className="info-grid">
                  <div className="info-metric-sm">
                    <span className="metric-label">Total Beds</span>
                    <span className="metric-val-sm">{selected.total.toLocaleString()}</span>
                  </div>
                  <div className="info-metric-sm">
                    <span className="metric-label">Available</span>
                    <span className="metric-val-sm" style={{ color: "#27ae60" }}>{selected.available.toLocaleString()}</span>
                  </div>
                  <div className="info-metric-sm">
                    <span className="metric-label">Occupied</span>
                    <span className="metric-val-sm" style={{ color: fill }}>{occupied.toLocaleString()}</span>
                  </div>
                  <div className="info-metric-sm">
                    <span className="metric-label">Status</span>
                    <span className="metric-val-sm">{statusLabel(selected.demand)}</span>
                  </div>
                </div>

                <button className="info-close-btn" onClick={() => setSelected(null)}>✕ Close</button>
              </div>
            );
          })()}

          {!selected && (
            <p className="info-hint">Click a hospital marker to view details</p>
          )}
        </div>
      </div>
    </div>
  );
}


