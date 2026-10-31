import { Fragment, ReactElement } from "react";
import { Navigate, NavLink, Route, Routes } from "react-router-dom";
import { hasRole, ROLE_LABEL, useAuth } from "./auth";
import type { Role } from "./types";
import Login from "./pages/Login";
import Candidates from "./pages/Candidates";
import Approvals from "./pages/Approvals";
import Inbox from "./pages/Inbox";
import SecurityCenter from "./pages/SecurityCenter";
import AnswerDesk from "./pages/AnswerDesk";
import Money from "./pages/Money";
import Scorecard from "./pages/Scorecard";
import EmployeeDocs from "./pages/EmployeeDocs";
import Users from "./pages/Users";
import Team from "./pages/Team";

interface NavEntry {
  path: string;
  label: string;
  group: "Recruit" | "Team" | "Oversight" | "Admin";
  roles: Role[];
  element: ReactElement;
}

const R: Role = "recruiter", M: Role = "hr_manager", E: Role = "employee", A: Role = "admin";

// Two modules on one trust core: Recruit (HireGuard, HR <-> candidates) and Team (HR Nexus, HR <-> staff)
const NAV: NavEntry[] = [
  { path: "/candidates", label: "Candidates", group: "Recruit", roles: [R, M], element: <Candidates /> },
  { path: "/inbox", label: "Inbox", group: "Recruit", roles: [R, M], element: <Inbox /> },
  { path: "/approvals", label: "Approvals", group: "Recruit", roles: [R, M], element: <Approvals /> },
  { path: "/scorecard", label: "Interview scorecard", group: "Recruit", roles: [R, M], element: <Scorecard /> },
  { path: "/team", label: "Team insights", group: "Team", roles: [M, A], element: <Team /> },
  { path: "/answer-desk", label: "Answer Desk", group: "Team", roles: [E, M], element: <AnswerDesk /> },
  { path: "/documents", label: "My documents", group: "Team", roles: [E], element: <EmployeeDocs /> },
  { path: "/security", label: "Security Center", group: "Oversight", roles: [M, A], element: <SecurityCenter /> },
  { path: "/money", label: "Money", group: "Oversight", roles: [M, A], element: <Money /> },
  { path: "/users", label: "Users", group: "Admin", roles: [A], element: <Users /> },
];

export default function App() {
  const { user, loading, logout } = useAuth();

  if (loading) return <div className="center muted">Loading…</div>;
  if (!user) return <Login />;

  const mine = NAV.filter((n) => hasRole(user, ...n.roles));

  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <img src="/favicon.svg" alt="" width={26} height={26} />
          <span>HireGuard</span>
        </div>
        <nav>
          {mine.map((n, i) => (
            <Fragment key={n.path}>
              {n.group !== mine[i - 1]?.group && <div className="nav-group">{n.group}</div>}
              <NavLink to={n.path} className={({ isActive }) => (isActive ? "nav active" : "nav")}>
                {n.label}
              </NavLink>
            </Fragment>
          ))}
        </nav>
        <div className="who">
          <div className="who-name">{user.display_name}</div>
          <div className="muted small">{ROLE_LABEL[user.role]}</div>
          <button className="btn ghost small" onClick={logout}>
            Sign out
          </button>
        </div>
      </aside>
      <main className="content">
        <Routes>
          {mine.map((n) => (
            <Route key={n.path} path={n.path} element={n.element} />
          ))}
          <Route path="*" element={<Navigate to={mine[0]?.path ?? "/"} replace />} />
        </Routes>
      </main>
    </div>
  );
}
