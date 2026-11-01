import { Badge, PageHeader } from "../components/ui";

const TOKENS = [
  ["bg", "App background"],
  ["surface", "Cards and panels"],
  ["surface-2", "Inputs and hover"],
  ["border", "Dividers"],
  ["text", "Primary text"],
  ["muted", "Secondary text"],
  ["primary", "Primary action"],
  ["ok", "Approved / safe"],
  ["warn", "Pending / needs review"],
  ["danger", "Security / destructive"],
  ["info", "Information / AI draft"],
];

function ThemePreview({ theme }: { theme: "light" | "dark" }) {
  return (
    <section className="theme-preview" data-theme={theme} aria-label={`${theme} theme examples`}>
      <header className="preview-heading">
        <h2>{theme === "light" ? "Light theme" : "Dark theme"}</h2>
        <span className="muted small">Shared design tokens</span>
      </header>
      <div className="token-grid">
        {TOKENS.map(([token, label]) => (
          <div className="token-sample" key={token}>
            <span className="token-swatch" data-token={token} />
            <span><strong>{label}</strong><code>--{token}</code></span>
          </div>
        ))}
      </div>
      <div className="guide-section">
        <h3>Actions and statuses</h3>
        <div className="row">
          <button type="button" className="btn primary">Primary action</button>
          <button type="button" className="btn">Secondary</button>
          <button type="button" className="btn success">Approve</button>
          <button type="button" className="btn danger">Delete</button>
        </div>
        <div className="badges">
          <Badge tone="ok">Approved</Badge>
          <Badge tone="warn">Needs review</Badge>
          <Badge tone="danger">Security alert</Badge>
          <Badge tone="info">AI prepared</Badge>
          <Badge>Draft</Badge>
        </div>
        <div className="alert ok"><strong>✓ Approved.</strong> The requested change is ready.</div>
        <div className="alert warn"><strong>◷ Needs review.</strong> A person should check this item.</div>
        <div className="alert danger"><strong>! Security alert.</strong> An unsafe action was blocked.</div>
        <div className="alert info"><strong>✦ AI prepared.</strong> Review this draft before sending.</div>
      </div>
      <div className="guide-section">
        <h3>Data and score ramp</h3>
        <div className="tile guide-kpi">
          <span className="tile-label">Open candidates</span>
          <strong className="tile-value">24</strong>
          <Badge tone="info">+3 this week</Badge>
        </div>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th>Candidate</th><th>Status</th><th className="num">Score</th></tr></thead>
            <tbody>
              <tr><td>Sample candidate</td><td><Badge tone="ok">Verified</Badge></td><td className="num">86</td></tr>
              <tr className="selected"><td>Selected row</td><td><Badge tone="warn">Needs review</Badge></td><td className="num">72</td></tr>
            </tbody>
          </table>
        </div>
        <div className="score-ramp" aria-label="Candidate score scale, low to high">
          {[1, 2, 3, 4, 5].map((step) => <span className={`ramp-step ramp-${step}`} key={step}>{step}</span>)}
          <span className="muted small">Lower score <span aria-hidden="true">→</span> Higher score</span>
        </div>
      </div>
    </section>
  );
}

export default function StyleGuide() {
  return (
    <>
      <PageHeader
        title="Design system"
        subtitle="Neutral surfaces, clear status meanings, and consistent controls in both themes."
      />
      <div className="style-guide-grid">
        <ThemePreview theme="light" />
        <ThemePreview theme="dark" />
      </div>
    </>
  );
}
