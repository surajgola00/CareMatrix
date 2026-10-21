import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import "./index.css";
import "leaflet/dist/leaflet.css";
import App from "./App.tsx";
import { HospitalProvider } from "./HospitalContext.tsx";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <HospitalProvider>
        <App />
      </HospitalProvider>
    </BrowserRouter>
  </StrictMode>,
);
