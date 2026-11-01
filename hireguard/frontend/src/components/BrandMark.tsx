// The Venidis mark as inline SVG so its badge can follow the theme (ink on light, paper on dark).
// Geometry matches brand/venidis-mark.svg, which brand/build_logo.py generates.
export default function BrandMark({ size = 30 }: { size?: number }) {
  return (
    <svg className="brand-mark" width={size} height={size} viewBox="0 0 64 64" role="img" aria-label="Venidis">
      <rect className="badge" width="64" height="64" rx="14" />
      <path className="stroke" d="M13 16 L32 47 L51 16" fill="none" strokeWidth="7" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="28" y="21.6" width="8" height="8" rx="1.4" fill="#F5C842" />
    </svg>
  );
}
