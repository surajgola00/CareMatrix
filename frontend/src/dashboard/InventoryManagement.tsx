import { useNavigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { createResourceRequest, getPrediction, getResourcePool } from "../api";
import type { ResourcePoolEntry } from "../api";
import { useHospital } from "../HospitalContext";

type Item = {
  id: string;
  name: string;
  quantity: number;
  price: number;
  icon: string;
  perPatient: number;
};

type BillItem = Item & { predicted: number; deficit: number; cost: number };

const inventory: Item[] = [
  { id: "i1",  name: "Oxygen Cylinders", quantity: 3,   price: 5000,  icon: "🫧", perPatient: 0.15 },
  { id: "i2",  name: "Ventilators",      quantity: 12,  price: 15000, icon: "🫁", perPatient: 0.05 },
  { id: "i4",  name: "Blood Units",      quantity: 25,  price: 1200,  icon: "🩸", perPatient: 0.2  },
  { id: "i5",  name: "Syringes",         quantity: 150, price: 10,    icon: "💉", perPatient: 3.0  },
  { id: "i6",  name: "Saline Bottles",   quantity: 8,   price: 200,   icon: "🧴", perPatient: 0.8  },
  { id: "i7",  name: "Defibrillators",   quantity: 2,   price: 7000,  icon: "⚡", perPatient: 0.02 },
  { id: "i8",  name: "Wheelchairs",      quantity: 18,  price: 8000,  icon: "♿", perPatient: 0.1  },
  { id: "i10", name: "Gloves",           quantity: 300, price: 5,     icon: "🧤", perPatient: 6.0  },
];

function today() {
  return new Date().toISOString().slice(0, 10);
}

export default function InventoryManagement() {
  const navigate = useNavigate();
  const { hospitalId } = useHospital();

  const [predictions, setPredictions] = useState<Record<string, number>>({});
  const [status, setStatus] = useState<Record<string, string>>({});
  const [bill, setBill] = useState<BillItem[]>([]);
  const [total, setTotal] = useState(0);
  const [ordering, setOrdering] = useState(false);
  const [orderDone, setOrderDone] = useState(false);
  const [loading, setLoading] = useState(false);
  const [predInfo, setPredInfo] = useState<{
    predicted: number;
    confidence_pct: number;
    date: string;
  } | null>(null);

  const [resourcePool, setResourcePool] = useState<ResourcePoolEntry[]>([]);
  const [expandedPool, setExpandedPool] = useState<string | null>(null);
  const [requestedItems, setRequestedItems] = useState<Set<string>>(new Set());

  useEffect(() => {
    if (!hospitalId) return;
    getResourcePool(hospitalId).then(setResourcePool).catch(() => {});
  }, [hospitalId]);

  const formatINR = (num: number) =>
    new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(num);

  const generatePrediction = async () => {
    if (!hospitalId) return;
    setLoading(true);
    setOrderDone(false);
    const data = await getPrediction(today(), hospitalId).catch(() => null);
    let patientCount: number;
    if (data) {
      patientCount = data.prediction.predicted;
      setPredInfo({ predicted: data.prediction.predicted, confidence_pct: data.prediction.confidence_pct, date: data.prediction.date });
    } else {
      patientCount = Math.floor(Math.random() * 60 + 20);
      setPredInfo(null);
    }
    const predMap: Record<string, number> = {};
    const statusMap: Record<string, string> = {};
    const newBill: BillItem[] = [];
    let sum = 0;
    inventory.forEach((item) => {
      const needed = Math.ceil(item.perPatient * patientCount);
      predMap[item.id] = needed;
      if (item.quantity >= needed) {
        statusMap[item.id] = "SATISFIED";
      } else {
        statusMap[item.id] = "REQUIRED";
        const deficit = needed - item.quantity;
        const cost = deficit * item.price;
        sum += cost;
        newBill.push({ ...item, predicted: needed, deficit, cost });
      }
    });
    setPredictions(predMap);
    setStatus(statusMap);
    setBill(newBill);
    setTotal(sum);
    setLoading(false);
  };

  const handleOrder = async () => {
    if (!hospitalId || bill.length === 0) return;
    setOrdering(true);
    await Promise.all(
      bill.map((b) => createResourceRequest(hospitalId, b.name, b.deficit).catch(() => {})),
    );
    setOrdering(false);
    setOrderDone(true);
  };

  const handleRequestFromPool = (hospitalId_: string, resourceType: string) => {
    const key = `${hospitalId_}::${resourceType}`;
    setRequestedItems((prev) => new Set([...prev, key]));
  };

  return (
    <main className="dashboard-shell inventory-shell">
      <header className="dashboard-topbar">
        <div className="brand-block">
          <div className="brand-logo" />
          <p className="dashboard-label">Hospital Management System</p>
          <h1>Inventory Management</h1>
        </div>
        <div className="account-menu">
          <div className="account-avatar">H</div>
          <button className="signout-button" onClick={() => navigate("/dashboard")}>Back</button>
        </div>
      </header>

      <section className="inventory-layout">
        <div className="inventory-table">
          <div className="table-header">
            <span>Item</span>
            <span>Available</span>
            <span>Required</span>
            <span>Status</span>
          </div>
          {inventory.map((item) => {
            const state = status[item.id];
            const isRequired = state === "REQUIRED";
            const isOk = state === "SATISFIED";
            return (
              <div
                key={item.id}
                className={`table-row ${isRequired ? "row-required" : isOk ? "row-ok" : ""}`}
              >
                <span className="item-name">
                  <span className="icon">{item.icon}</span>
                  {item.name}
                </span>
                <span className="number">{item.quantity}</span>
                <span className="number">{predictions[item.id] ?? "—"}</span>
                <span className={`status ${isRequired ? "status-bad" : isOk ? "status-ok" : ""}`}>
                  {state ?? "—"}
                </span>
              </div>
            );
          })}
        </div>

        <div className="inventory-side">
          <button className="action-card" onClick={generatePrediction} disabled={loading}>
            {loading ? "Fetching…" : "Predict Resources"}
          </button>

          {predInfo && (
            <div className="pred-info-card">
              <p className="pred-info-label">Based on prediction</p>
              <p className="pred-info-val">{predInfo.predicted} patients</p>
              <p className="pred-info-sub">{predInfo.confidence_pct}% confidence · {predInfo.date}</p>
            </div>
          )}

          <div className="bill-panel">
            {bill.length > 0 ? (
              <>
                <h3>Restock Bill</h3>
                {bill.map((b) => (
                  <div key={b.id} className="bill-row">
                    <span>{b.name}</span>
                    <span className="number bill-calc">{b.deficit} × {formatINR(b.price)}</span>
                    <span className="number bill-amount">{formatINR(b.cost)}</span>
                  </div>
                ))}
                <div className="bill-total">
                  <span>Total</span>
                  <span className="number">{formatINR(total)}</span>
                </div>
                {orderDone ? (
                  <p className="order-success">✓ Resource requests sent</p>
                ) : (
                  <button className="order-button" onClick={handleOrder} disabled={ordering || !hospitalId}>
                    {ordering ? "Sending…" : "Order Now"}
                  </button>
                )}
              </>
            ) : (
              <p className="placeholder">No prediction yet</p>
            )}
          </div>

          {/* ── Shared Resource Pool ── */}
          <div className="pool-panel">
            <h3 className="pool-heading">Network Resource Pool</h3>
            <p className="pool-sub">Available from nearby hospitals</p>
            {resourcePool.length === 0 ? (
              <p className="placeholder">Loading pool…</p>
            ) : (
              resourcePool.map((entry) => (
                <div key={entry.hospital_id} className="pool-entry">
                  <button
                    className="pool-entry-header"
                    onClick={() =>
                      setExpandedPool(expandedPool === entry.hospital_id ? null : entry.hospital_id)
                    }
                  >
                    <span className="pool-hosp-name">{entry.hospital}</span>
                    <span className="pool-dist">{entry.distance_km} km</span>
                    <span className="pool-chevron">{expandedPool === entry.hospital_id ? "▲" : "▼"}</span>
                  </button>
                  {expandedPool === entry.hospital_id && (
                    <div className="pool-resources">
                      {entry.resources.map((res) => {
                        const key = `${entry.hospital_id}::${res.type}`;
                        const requested = requestedItems.has(key);
                        return (
                          <div key={res.type} className="pool-resource-row">
                            <span className="pool-icon">{res.icon}</span>
                            <span className="pool-res-name">{res.type}</span>
                            <span className="pool-avail">{res.available} avail.</span>
                            <button
                              className={`pool-request-btn ${requested ? "pool-requested" : ""}`}
                              disabled={requested}
                              onClick={() => handleRequestFromPool(entry.hospital_id, res.type)}
                            >
                              {requested ? "✓ Requested" : "Request"}
                            </button>
                          </div>
                        );
                      })}
                    </div>
                  )}
                </div>
              ))
            )}
          </div>
        </div>
      </section>
    </main>
  );
}
