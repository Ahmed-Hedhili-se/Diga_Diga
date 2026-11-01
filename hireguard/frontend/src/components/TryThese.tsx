// "Examples to try": shown in the Overview's help popover, only for pages this account can open.
// Opening a page never approves, sends or releases anything.
import { useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

const EXAMPLES = [
  { path: "/candidates", permission: "candidates.read", title: "Inspect a candidate", detail: "Open a CV, review score evidence, then check its security findings." },
  { path: "/approvals", permission: "approvals.decide", title: "Review an approval", detail: "Compare the proposed change and its risk before deciding." },
  { path: "/security", permission: "security_center.read", title: "Explore a security finding", detail: "See what hidden text was detected and how it was handled." },
  { path: "/answer-desk", permission: "answer_desk.ask", title: "Try a handbook question", detail: "Start with a suggested question; answers include source citations." },
  { path: "/documents", permission: "documents.request", title: "Request a document", detail: "Choose a certificate type and follow its review status." },
] as const;

export default function TryThese({ onOpen }: { onOpen?: () => void }) {
  const { can } = useAuth();
  const navigate = useNavigate();
  const mine = EXAMPLES.filter((e) => can(e.permission));
  if (!mine.length) return null;
  return (
    <section className="try-these" aria-label="Examples to try">
      <h2>Examples to try</h2>
      <p className="muted small">Only pages your account can open are listed. Opening a page does not approve, send or release anything.</p>
      <ul>
        {mine.map((e) => (
          <li key={e.path}>
            <button type="button" className="link" onClick={() => { navigate(e.path); onOpen?.(); }}>
              {e.title}
            </button>
            <span className="muted small"> {e.detail}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
