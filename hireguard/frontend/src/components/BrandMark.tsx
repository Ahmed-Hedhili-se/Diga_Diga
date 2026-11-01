// The Venidis mark as inline SVG so its badge can follow the theme (navy on light, brighter blue on dark).
// Geometry matches brand/venidis-mark.svg, which brand/build_logo.py generates.
export default function BrandMark({ size = 30 }: { size?: number }) {
  return (
    <svg className="brand-mark" width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="Venidis">
      <rect className="badge" width="64" height="64" rx="15" />
      <path d="M16 26 L32 50 L48 26" fill="none" stroke="#fff" strokeWidth="6.6" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="32" cy="15" r="5.6" fill="#FBBF24" />
    </svg>
  );
}
