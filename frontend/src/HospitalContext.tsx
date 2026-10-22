import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { getCurrentUser, heartbeat, logout as apiLogout } from "./api";
import type { AuthHospital } from "./api";

type HospitalCtx = {
  hospitalId: string | null;
  hospital: AuthHospital | null;
  setHospital: (hospital: AuthHospital) => void;
  clearHospital: () => Promise<void>;
  authenticated: boolean;
  ready: boolean;
};

const Ctx = createContext<HospitalCtx>({
  hospitalId: null,
  hospital: null,
  setHospital: () => {},
  clearHospital: async () => {},
  authenticated: false,
  ready: false,
});

export function HospitalProvider({ children }: { children: ReactNode }) {
  const [hospital, setHospitalState] = useState<AuthHospital | null>(null);
  const [checked, setChecked] = useState(false);

  const setHospital = (value: AuthHospital) => setHospitalState(value);
  const clearHospital = async () => { await apiLogout(); setHospitalState(null); };

  useEffect(() => {
    getCurrentUser().then((user) => setHospitalState(user?.hospital ?? null)).finally(() => setChecked(true));
  }, []);

  useEffect(() => {
    if (!hospital) return;
    const id = window.setInterval(() => {
      heartbeat().catch((error: Error) => {
        // A temporary LAN/API failure must not log the presenter out.
        if (error.message === "AUTH_EXPIRED") setHospitalState(null);
      });
    }, 10000);
    return () => window.clearInterval(id);
  }, [hospital]);

  return (
    <Ctx.Provider value={{ hospitalId: hospital?.hospital_id ?? null, hospital, setHospital, clearHospital, authenticated: !!hospital, ready: checked }}>
      {children}
    </Ctx.Provider>
  );
}

export function useHospital() {
  return useContext(Ctx);
}
