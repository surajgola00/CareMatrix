import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

type HospitalCtx = {
  hospitalId: string | null;
  setHospitalId: (id: string) => void;
};

const Ctx = createContext<HospitalCtx>({
  hospitalId: null,
  setHospitalId: () => {},
});

export function HospitalProvider({ children }: { children: ReactNode }) {
  const [hospitalId, setHospitalIdState] = useState<string | null>(() =>
    localStorage.getItem("cm_hospital_id"),
  );

  const setHospitalId = (id: string) => {
    localStorage.setItem("cm_hospital_id", id);
    setHospitalIdState(id);
  };

  useEffect(() => {
    const stored = localStorage.getItem("cm_hospital_id");
    if (stored) setHospitalIdState(stored);
  }, []);

  return (
    <Ctx.Provider value={{ hospitalId, setHospitalId }}>
      {children}
    </Ctx.Provider>
  );
}

export function useHospital() {
  return useContext(Ctx);
}
