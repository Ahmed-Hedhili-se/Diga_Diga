import { ReactElement, useEffect, useState } from "react";
import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { IdleWatcher, ROLE_LABEL, useAuth } from "./auth";
import { Badge, ConfirmButton, Modal } from "./components/ui";
import { Icon, type IconName } from "./components/icons";
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
import UploadCv from "./pages/UploadCv";
import Rubric from "./pages/Rubric";
import { Forbidden, NotFound } from "./pages/Errors";
import StyleGuide from "./pages/StyleGuide";
import Team from "./pages/Team";

interface Page {
  path: string;
  label: string;
  permission: string;
  group: Group;
  module: string;
  icon: IconName;
  element: ReactElement;
}

// Two modules on one trust core: Recruit (HireGuard, HR <-> candidates) and Team (HR Nexus, HR <-> staff).
// Nav, routes and home all derive from permissions (GET /auth/me), never from hard-coded roles.
const PAGES: Page[] = [
  { path: "/candidates", label: "Candidates", permission: "candidates.read", group: "Recruit", module: "candidates", icon: "candidates", element: <Candidates /> },
  { path: "/inbox", label: "Inbox", permission: "inbox.read", group: "Recruit", module: "inbox", icon: "inbox", element: <Inbox /> },
  { path: "/approvals", label: "Approvals", permission: "approvals.decide", group: "Recruit", module: "approvals", icon: "approvals", element: <Approvals /> },
  { path: "/interviews", label: "Interviews", permission: "interviews.scorecard", group: "Recruit", module: "scorecard", icon: "interviews", element: <Scorecard /> },
  { path: "/team", label: "Team insights", permission: "team.read", group: "Team", module: "team", icon: "team", element: <Team /> },
  { path: "/questions", label: "Employee questions", permission: "questions.reply", group: "Team", module: "answer-desk", icon: "questions", element: <EmployeeQuestions /> },
  { path: "/answer-desk", label: "Answer Desk", permission: "answer_desk.ask", group: "Team", module: "answer-desk", icon: "answers", element: <AnswerDesk /> },
  { path: "/documents", label: "My documents", permission: "documents.request", group: "Team", module: "documents", icon: "documents", element: <EmployeeDocs /> },
  { path: "/security", label: "Security Center", permission: "security_center.read", group: "Oversight", module: "security", icon: "attacks", element: <SecurityCenter /> },
  { path: "/money", label: "Money", permission: "money.read", group: "Oversight", module: "money", icon: "vacancy", element: <Money /> },
  { path: "/users", label: "Users", permission: "users.manage", group: "Admin", module: "users", icon: "users", element: <Users /> },
];
// Recruit = HireGuard (HR <-> candidates); Team = HR Nexus (HR <-> staff); Oversight spans both on the trust core.
const GROUPS = ["Recruit", "Team", "Oversight", "Admin"] as const;
type Group = (typeof GROUPS)[number];
type Theme = "system" | "light" | "dark";

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
  const location = useLocation();
  const navigate = useNavigate();
  const [theme, setTheme] = useState<Theme>(() => {
    try {
      const saved = window.localStorage.getItem("hireguard-theme");
      return saved === "light" || saved === "dark" ? saved : "system";
    } catch {
      return "system";
    }
  });
  const [collapsed, setCollapsed] = useState(false);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [query, setQuery] = useState("");

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      window.localStorage.setItem("hireguard-theme", theme);
    } catch {
      // The selected theme remains active for this session if storage is unavailable.
    }
  }, [theme]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && paletteOpen) setPaletteOpen(false);
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen(true);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [paletteOpen]);

  if (loading) return <div className="center muted">Loading…</div>;
  if (!user) return <Login />;

  const mine = PAGES.filter((p) => can(p.permission));
  const home = HOME.find(([p]) => can(p))?.[1] ?? mine[0]?.path ?? "/403";
  const currentPage = PAGES.find((p) => location.pathname.startsWith(p.path));
  const isStyleGuide = location.pathname === "/style-guide";
  const visiblePages = mine.filter((p) => p.label.toLowerCase().includes(query.trim().toLowerCase()));
  const themeLabel = theme === "system" ? "System" : theme === "light" ? "Light" : "Dark";
  const examples = [
    { path: "/candidates", title: "Inspect a candidate", detail: "Open a CV, review score evidence, then check its security findings." },
    { path: "/approvals", title: "Review an approval", detail: "Compare the proposed change and its risk before deciding." },
    { path: "/security", title: "Explore a security finding", detail: "See what hidden text was detected and how it was handled." },
    { path: "/answer-desk", title: "Try a handbook question", detail: "Start with a suggested question; answers include source citations." },
    { path: "/documents", title: "Request a document", detail: "Choose a certificate type and follow its review status." },
  ].filter((example) => mine.some((page) => page.path === example.path));

  function openPage(path: string) {
    navigate(path);
    setPaletteOpen(false);
    setQuery("");
    setMobileNavOpen(false);
  }

  return (
    <div className={`shell${collapsed ? " sidebar-collapsed" : ""}${mobileNavOpen ? " mobile-nav-open" : ""}`}>
      <a className="skip-link" href="#main">
        Skip to content
      </a>
      <aside className="sidebar">
        <div className="brand">
          <img src="/favicon.svg" alt="" width={28} height={28} />
          <span>HireGuard</span>
          <button
            type="button"
            className="sidebar-toggle"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
            onClick={() => setCollapsed((value) => !value)}
          >
            <span aria-hidden="true">{collapsed ? "»" : "«"}</span>
          </button>
        </div>
        <nav aria-label="Main">
          {GROUPS.map((group) => {
            const pages = mine.filter((page) => page.group === group);
            if (!pages.length && !(group === "Admin" && import.meta.env.DEV && can("users.manage"))) return null;
            return (
              <section className="nav-group" key={group} aria-label={group}>
                <h2 className="nav-heading">{group}</h2>
                {pages.map((page) => (
                  <NavLink
                    key={page.path}
                    to={page.path}
                    title={page.label}
                    className={({ isActive }) => `nav module-${page.module}${isActive ? " active" : ""}`}
                    onClick={() => setMobileNavOpen(false)}
                  >
                    <Icon name={page.icon} size={18} />
                    <span className="nav-label">{page.label}</span>
                  </NavLink>
                ))}
                {group === "Admin" && import.meta.env.DEV && can("users.manage") && (
                  <NavLink to="/style-guide" className={`nav module-users${isStyleGuide ? " active" : ""}`} onClick={() => setMobileNavOpen(false)}>
                    <span className="nav-guide-icon" aria-hidden="true">Aa</span>
                    <span className="nav-label">Style guide</span>
                  </NavLink>
                )}
              </section>
            );
          })}
        </nav>
      </aside>
      <div className="main-col">
        <header className="topbar">
          <div className="topbar-leading">
            <button
              type="button"
              className="mobile-menu btn ghost"
              aria-label={mobileNavOpen ? "Close navigation" : "Open navigation"}
              aria-expanded={mobileNavOpen}
              onClick={() => setMobileNavOpen((value) => !value)}
            >
              <span aria-hidden="true">☰</span>
            </button>
            <div className="topbar-title">
              <span className={`module-chip module-${currentPage?.module ?? "users"}`} aria-hidden="true">
                <Icon name={currentPage?.icon ?? "overview"} size={16} />
              </span>
              <div>
                <span className="topbar-eyebrow">{currentPage?.group ?? (isStyleGuide ? "Admin" : "Workspace")}</span>
                <h1>{isStyleGuide ? "Style guide" : currentPage?.label ?? "HireGuard"}</h1>
              </div>
            </div>
          </div>
          <div className="topbar-actions">
            <button type="button" className="global-search" onClick={() => setPaletteOpen(true)} aria-keyshortcuts="Control+K Meta+K">
              <span className="search-glyph" aria-hidden="true">⌕</span>
              <span>Search pages</span>
              <kbd>Ctrl / ⌘ K</kbd>
            </button>
            <button
              type="button"
              className="theme-toggle"
              title={`Theme: ${themeLabel}. Click to change.`}
              aria-label={`Theme: ${themeLabel}. Click to change.`}
              onClick={() => setTheme((value) => value === "system" ? "light" : value === "light" ? "dark" : "system")}
            >
              <span aria-hidden="true">{theme === "light" ? "☼" : theme === "dark" ? "☾" : "◐"}</span>
              <span className="theme-label">{themeLabel}</span>
            </button>
            <div className="user-menu">
              <details>
                <summary className="user-trigger">
                  <span className="avatar" aria-hidden="true">{user.display_name.trim().charAt(0).toUpperCase() || "?"}</span>
                  <span className="user-copy">
                    <span className="who-name">{user.display_name}</span>
                    <Badge tone="neutral">{ROLE_LABEL[user.role]}</Badge>
                  </span>
                  <span className="user-chevron" aria-hidden="true">⌄</span>
                </summary>
                <div className="user-menu-panel">
                  <div className="user-menu-identity">
                    <strong>{user.display_name}</strong>
                    <Badge tone="neutral">{ROLE_LABEL[user.role]}</Badge>
                  </div>
                  <button className="btn ghost small" onClick={logout}>Log out</button>
                  <ConfirmButton
                    className="btn ghost small"
                    label="Log out everywhere"
                    title="Log out on every device?"
                    message="This closes all your sessions, including on other computers and phones."
                    confirmLabel="Log out everywhere"
                    onConfirm={logoutAll}
                  />
                </div>
              </details>
            </div>
          </div>
        </header>
        <main className="content" id="main" tabIndex={-1}>
          <Routes>
            <Route path="/" element={<Navigate to={home} replace />} />
            {PAGES.map((p) => (
              <Route key={p.path} path={p.path} element={can(p.permission) ? p.element : <Forbidden home={home} />} />
            ))}
            <Route
              path="/candidates/upload"
              element={can("candidates.upload") ? <UploadCv /> : <Forbidden home={home} />}
            />
            <Route
              path="/rubrics"
              element={can("candidates.read") ? <Rubric /> : <Forbidden home={home} />}
            />
            {import.meta.env.DEV && can("users.manage") && <Route path="/style-guide" element={<StyleGuide />} />}
            <Route path="/403" element={<Forbidden home={home} />} />
            <Route path="*" element={<NotFound home={home} />} />
          </Routes>
          {examples.length > 0 && (
            <details className="quick-start">
              <summary>
                <span>Examples to try</span>
                <span className="muted small">Quick tour · only pages available to your account</span>
              </summary>
              <div className="quick-start-grid">
                {examples.map((example) => (
                  <button
                    type="button"
                    className="quick-start-item"
                    key={example.path}
                    onClick={() => openPage(example.path)}
                  >
                    <strong>{example.title}</strong>
                    <span>{example.detail}</span>
                    <span className="quick-start-link">Open example →</span>
                  </button>
                ))}
              </div>
              <p className="quick-start-note">
                Demo examples appear when the local demo data has been seeded. Opening a page does not approve,
                send, or release anything.
              </p>
            </details>
          )}
        </main>
      </div>
      {mobileNavOpen && <button className="nav-scrim" aria-label="Close navigation" onClick={() => setMobileNavOpen(false)} />}
      <Modal
        open={paletteOpen}
        title="Navigate to a page"
        titleClassName="visually-hidden"
        className="palette-modal"
        onClose={() => setPaletteOpen(false)}
      >
        <label className="palette-input">
            <span aria-hidden="true">⌕</span>
            <input
              autoFocus
              aria-label="Search accessible pages"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search pages you can access…"
              onKeyDown={(event) => {
                if (event.key === "Enter" && visiblePages[0]) openPage(visiblePages[0].path);
              }}
            />
            <kbd>ESC</kbd>
        </label>
        <div className="palette-results">
            {visiblePages.map((page) => (
              <button type="button" className={`palette-result module-${page.module}`} key={page.path} onClick={() => openPage(page.path)}>
                <Icon name={page.icon} size={18} />
                <span>{page.label}</span>
                <span className="muted">{page.group}</span>
              </button>
            ))}
            {visiblePages.length === 0 && <p className="empty muted">No accessible pages match your search.</p>}
        </div>
      </Modal>
      <IdleWatcher />
    </div>
  );
}
