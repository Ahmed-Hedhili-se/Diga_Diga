// Line icons drawn on a 24px grid (1.75 stroke). Inline SVG: no icon font, no extra request, CSP-safe.

const PATHS = {
  overview: "M4 13h6V4H4zM14 20h6v-9h-6zM14 4h6v4h-6zM4 20h6v-3H4z",
  candidates: "M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM2 21v-1a7 7 0 0 1 14 0v1M17 3.5a4 4 0 0 1 0 7.5M22 21v-1a6 6 0 0 0-3.5-5.5",
  upload: "M12 16V4M7 9l5-5 5 5M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3",
  jobs: "M4 8h16v12H4zM9 8V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v3M4 13h16",
  interviews: "M4 6h16v14H4zM4 10h16M9 3v4M15 3v4M8 14h3",
  approvals: "M9 12l2 2 4-4M12 3l7 3v5c0 5-3.5 8.5-7 10-3.5-1.5-7-5-7-10V6z",
  inbox: "M3 13l3-8h12l3 8M3 13v6h18v-6M3 13h5l1 3h6l1-3h5",
  followups: "M12 7v5l3 2M21 12a9 9 0 1 1-3-6.7M21 4v5h-5",
  questions: "M4 5h16v11H9l-5 4zM9.5 9a2.5 2.5 0 1 1 3 2.4V12M12 14.5v.01",
  documents: "M7 3h7l5 5v13H7zM14 3v5h5M10 13h6M10 17h6",
  answers: "M11 4a7 7 0 1 0 4.9 12L20 20M8 11h6M11 8v6",
  attacks: "M12 3l8 4v5c0 4.5-3.4 8-8 9-4.6-1-8-4.5-8-9V7zM9 9l6 6M15 9l-6 6",
  evaluation: "M4 20V10M10 20V4M16 20v-7M22 20H2",
  reviewers: "M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12zM12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  audit: "M9 6l-5 5 5 5M15 6l5 5-5 5M13 4l-2 16",
  vacancy: "M12 3v18M17 7.5c0-2-2.2-3-5-3s-5 1.2-5 3.3c0 4.7 10 2.4 10 7.4 0 2-2.3 3.3-5 3.3s-5-1-5-3",
  savings: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM12 7v5l3 3",
  users: "M16 21v-1a5 5 0 0 0-5-5H7a5 5 0 0 0-5 5v1M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8zM19 8v6M22 11h-6",
  permissions: "M7 11V7a5 5 0 0 1 10 0v4M5 11h14v10H5zM12 15v2",
  integrations: "M9 2v6M15 2v6M6 8h12v4a6 6 0 0 1-12 0zM12 18v4",
  data: "M4 6c0-1.7 3.6-3 8-3s8 1.3 8 3-3.6 3-8 3-8-1.3-8-3zM4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3",
  check: "M5 12l5 5 9-10",
  alert: "M12 3l10 18H2zM12 10v4M12 17.5v.01",
  blocked: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18zM5.6 5.6l12.8 12.8",
  arrow: "M5 12h14M13 6l6 6-6 6",
  team: "M12 12a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM5 10a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM19 10a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5zM7 20v-1a5 5 0 0 1 10 0v1M1.5 18v-.5A3.5 3.5 0 0 1 5 14h1M22.5 18v-.5A3.5 3.5 0 0 0 19 14h-1",
  logout: "M15 4h4a1 1 0 0 1 1 1v14a1 1 0 0 1-1 1h-4M10 16l-4-4 4-4M6 12h10",
} as const;

export type IconName = keyof typeof PATHS;

export function Icon({ name, size = 18, className }: { name: IconName; size?: number; className?: string }) {
  return (
    <svg
      className={`icon ${className ?? ""}`}
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
