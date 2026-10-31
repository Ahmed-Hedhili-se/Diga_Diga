import { Fragment, ReactElement } from "react";
import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { IdleWatcher, ROLE_LABEL, useAuth } from "./auth";
import { Badge, ConfirmButton } from "./components/ui";
import Login from "./pages/Login";
import Candidates from "./pages/Candidates";
import Approvals from "./pages/Approvals";
import Inbox from "./pages/Inbox";
import EmployeeQuestions from "./pages/EmployeeQuestions";
import SecurityCenter from "./pages/SecurityCenter";
import AnswerDesk from "./pages/AnswerDesk";
import Money from "./pages/Money";
import Scorecard from "./pages/Scorecard";
import EmployeeDocs from "./pages/EmployeeDocs";
import Users from "./pages/Users";
import { Forbidden, NotFound } from "./pages/Errors";
import Team from "./pages/Team";

interface Page {
  path: string;
  label: string;
  permission: string;
  group: "Recruit" | "Team" | "Oversight" | "Admin";
  element: ReactElement;
}

// Two modules on one trust core: Recruit (HireGuard, HR <-> candidates) and Team (HR Nexus, HR <-> staff).
// Nav, routes and home all derive from permissions (GET /auth/me), never from hard-coded roles.
const PAGES: Page[] = [
  { path: "/candidates", label: "Candidates", group: "Recruit", permission: "candidates.read", element: <Candidates /> },
  { path: "/inbox", label: "Inbox", group: "Recruit", permission: "inbox.read", element: <Inbox /> },
  { path: "/approvals", label: "Approvals", group: "Recruit", permission: "approvals.decide", element: <Approvals /> },
  { path: "/interviews", label: "Interviews", group: "Recruit", permission: "interviews.scorecard", element: <Scorecard /> },
  { path: "/team", label: "Team insights", group: "Team", permission: "team.read", element: <Team /> },
  { path: "/questions", label: "Employee questions", group: "Team", permission: "questions.reply", element: <EmployeeQuestions /> },
  { path: "/answer-desk", label: "Answer Desk", group: "Team", permission: "answer_desk.ask", element: <AnswerDesk /> },
  { path: "/documents", label: "My documents", group: "Team", permission: "documents.request", element: <EmployeeDocs /> },
  { path: "/security", label: "Security Center", group: "Oversight", permission: "security_center.read", element: <SecurityCenter /> },
  { path: "/money", label: "Money", group: "Oversight", permission: "money.read", element: <Money /> },
  { path: "/users", label: "Users", group: "Admin", permission: "users.manage", element: <Users /> },
];

// Where each kind of user lands: HR manager -> approvals, recruiter -> candidates, employee -> documents,
// admin -> users. Expressed as "first permission held", so a new role lands somewhere sensible.
const HOME: [string, string][] = [
  ["approvals.decide_high_risk", "/approvals"],
  ["candidates.read", "/candidates"],
  ["documents.request", "/documents"],
  ["users.manage", "/users"],
];

export default function App() {
  const { user, loading, can, logout, logoutAll } = useAuth();

  if (loading) return <div className="center muted">Loading…</div>;
  if (!user) return <Login />;

  const mine = PAGES.filter((p) => can(p.permission));
  const home = HOME.find(([p]) => can(p))?.[1] ?? mine[0]?.path ?? "/403";

  return (
    <div className="shell">
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="sidebar">
        <div className="brand">
          <img src="/favicon.svg" alt="" width={26} height={26} />
          <span>HireGuard</span>
        </div>
        <nav aria-label="Main">
          {mine.map((p, i) => (
            <Fragment key={p.path}>
              {p.group !== mine[i - 1]?.group && <div className="nav-group">{p.group}</div>}
              <NavLink to={p.path} className={({ isActive }) => (isActive ? "nav active" : "nav")}>
                {p.label}
              </NavLink>
            </Fragment>
          ))}
        </nav>
      </aside>
      <div className="main-col">
        <header className="topbar">
          <div className="who">
            <span className="who-name">{user.display_name}</span>
            <Badge tone="info">{ROLE_LABEL[user.role]}</Badge>
          </div>
          <div className="row">
            <button className="btn ghost small" onClick={logout}>
              Log out
            </button>
            <ConfirmButton
              className="btn ghost small"
              label="Log out everywhere"
              title="Log out on every device?"
              message="This closes all your sessions, including on other computers and phones."
              confirmLabel="Log out everywhere"
              onConfirm={logoutAll}
            />
          </div>
        </header>
        <main className="content" id="main" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<Navigate to={home} replace />} />
            {PAGES.map((p) => (
              <Route key={p.path} path={p.path} element={can(p.permission) ? p.element : <Forbidden home={home} />} />
            ))}
            <Route path="/403" element={<Forbidden home={home} />} />
            <Route path="*" element={<NotFound home={home} />} />
          </Routes>
        </main>
      </div>
      <IdleWatcher />
    </div>
  );
}
