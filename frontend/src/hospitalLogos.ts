// Place hospital-specific files in public/hospital-logos/.
// Keys are stable hospital IDs, not display names.
export const hospitalLogos: Record<string, string> = {
  hospital123: "/hospital-logos/hospital123.svg",
  hospital321: "/hospital-logos/hospital321.svg",
  fortis_memorial_gurugram: "/hospital-logos/fortis_memorial_gurugram.svg",
  max_gurugram: "/hospital-logos/max_gurugram.svg",
  paras_gurugram: "/hospital-logos/paras_gurugram.svg",
  medanta_medicity: "/hospital-logos/medanta_medicity.svg",
  artemis_gurugram: "/hospital-logos/artemis_gurugram.svg",
};

export const defaultHospitalLogo = "/favicon.svg";

export function hospitalLogo(hospitalId: string | null | undefined) {
  return (hospitalId && hospitalLogos[hospitalId]) || defaultHospitalLogo;
}
