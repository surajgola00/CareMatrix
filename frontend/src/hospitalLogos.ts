// Place hospital-specific files in public/hospital-logos/.
// Keys are stable hospital IDs, not display names.
export const hospitalLogos: Record<string, string> = {
  hospital123: "/hospital-logos/hospital123.svg",
  hospital321: "/hospital-logos/hospital321.svg",
};

export const defaultHospitalLogo = "/favicon.svg";

export function hospitalLogo(hospitalId: string | null | undefined) {
  return (hospitalId && hospitalLogos[hospitalId]) || defaultHospitalLogo;
}
