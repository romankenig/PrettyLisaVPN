import flags from "../assets/country-flags.svg";

export function CountryIcon({ code }: { readonly code?: string | null }) {
  if (code && /^[A-Z]{2}$/.test(code)) {
    return (
      <svg className="country-icon" viewBox="0 0 512 512" aria-hidden="true">
        <use href={`${flags}#${code.toLowerCase()}`} />
      </svg>
    );
  }
  return (
    <svg className="country-icon country-icon--globe" viewBox="0 0 24 24" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <ellipse cx="12" cy="12" rx="4" ry="10" />
      <path d="M2 12h20M4 6h16M4 18h16" />
    </svg>
  );
}
