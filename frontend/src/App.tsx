import "./App.css";
import type { ReactNode } from "react";
import { Routes, Route, Navigate } from "react-router-dom";
import Login from "./authentication/Login";
import HeatMapPage from "./heatmap/HeatMapPage";
import Dashboard from "./dashboard/Dashboard";
import InventoryManagement from "./dashboard/InventoryManagement";
import PredictionPage from "./dashboard/Predictionpage";
import Activity from "./activity/Activity";
import { useHospital } from "./HospitalContext";

function Protected({ children }: { children: ReactNode }) {
  const { authenticated, ready } = useHospital();
  if (!ready) return <main className="dashboard-shell"><p className="notif-empty">Checking session…</p></main>;
  return authenticated ? <>{children}</> : <Navigate to="/login" replace />;
}

function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/login" replace />} />
      <Route path="/login" element={<Login />} />
      <Route path="/heatmap" element={<Protected><HeatMapPage /></Protected>} />
      <Route path="/dashboard" element={<Protected><Dashboard /></Protected>} />
      <Route path="/inventory" element={<Protected><InventoryManagement /></Protected>} />
      <Route path="/prediction" element={<Protected><PredictionPage /></Protected>} />
      <Route path="/activity" element={<Protected><Activity /></Protected>} />
    </Routes>
  );
}

export default App;
