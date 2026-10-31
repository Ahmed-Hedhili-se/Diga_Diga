import { ReactElement } from "react";
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

interface NavEntry {
  path: string;
  label: string;
  roles: Role[];
  element: ReactElement;
}

const R: Role = "recruiter", M: Role = "hr_manager", E: Role = "employee", A: Role = "admin";

const NAV: NavEntry[] = [
  { path: "/candidates", label: "Candidates", roles: [R, M], element: <Candidates /> },
  { path: "/approvals", label: "Approvals", roles: [R, M], element: <Approvals /> },
  { path: "/inbox", label: "Inbox", roles: [R, M], element: <Inbox /> },
  { path: "/security", label: "Security Center", roles: [M, A], element: <SecurityCenter /> },
  { path: "/money", label: "Money", roles: [M, A], element: <Money /> },
  { path: "/answer-desk", label: "Answer Desk", roles: [E, M], element: <AnswerDesk /> },
  { path: "/documents", label: "My documents", roles: [E], element: <EmployeeDocs /> },
  { path: "/scorecard", label: "Interview scorecard", roles: [R, M], element: <Scorecard /> },
  { path: "/users", label: "Users", roles: [A], element: <Users /> },
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
          {mine.map((n) => (
            <NavLink key={n.path} to={n.path} className={({ isActive }) => (isActive ? "nav active" : "nav")}>
              {n.label}
            </NavLink>
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
