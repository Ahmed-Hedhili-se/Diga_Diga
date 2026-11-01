import { ReactElement, useEffect, useState } from "react";
import { BRAND } from "./brand";
import BrandMark from "./components/BrandMark";
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
import Overview from "./pages/Overview";
import PageHints from "./components/PageHints";

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
  { path: "/overview", label: "Overview", permission: "", group: "Workspace", module: "overview", icon: "overview", element: <Overview /> },
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
const GROUPS = ["Workspace", "Recruit", "Team", "Oversight", "Admin"] as const;
type Group = (typeof GROUPS)[number];
type Theme = "system" | "light" | "dark";

// Where each kind of user lands: staff (recruiter, HR manager, admin) -> overview, employee -> documents.
// Expressed as "first permission held", so a new role lands somewhere sensible.
const HOME: [string, string][] = [
  ["model.status", "/overview"],
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

  const allowed = (p: Page) => !p.permission || can(p.permission); // "" = any signed-in user
  const mine = PAGES.filter(allowed);
  const home = HOME.find(([p]) => can(p))?.[1] ?? mine[0]?.path ?? "/403";
  const isStyleGuide = location.pathname === "/style-guide";
  const visiblePages = mine.filter((p) => p.label.toLowerCase().includes(query.trim().toLowerCase()));
  const themeLabel = theme === "system" ? "System" : theme === "light" ? "Light" : "Dark";
  // Demo names carry a role suffix, e.g. "Karim Trabelsi (HR Manager)": greet by first name only.
  const firstName = user.display_name.replace(/\(.*\)/, "").trim().split(/\s+/)[0] || user.display_name;
  const hour = new Date().getHours();
  const greeting = hour < 5 ? "Working late" : hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
  const today = new Date().toLocaleDateString(undefined, { weekday: "long", day: "numeric", month: "long" });
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
          <BrandMark size={30} />
          <span>{BRAND.name}</span>
          <button
            type="button"
            className="sidebar-toggle"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-expanded={!collapsed}
            onClick={() => setCollapsed((value) => !value)}
          >
            <Icon name={collapsed ? "panelRight" : "panelLeft"} size={18} />
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
        <p className="sidebar-note">
          <strong><span className="status-dot" aria-hidden="true" />Nothing leaves without a person</strong>
          Emails, offers and Odoo updates wait in Approvals until someone signs off.
        </p>
      </aside>
      <div className="main-col">
        <header className="topbar">
          <div className="topbar-leading">
            <button
              type="button"
              className="mobile-menu icon-btn"
              aria-label={mobileNavOpen ? "Close navigation" : "Open navigation"}
              aria-expanded={mobileNavOpen}
              onClick={() => setMobileNavOpen((value) => !value)}
            >
              <Icon name="menu" size={20} />
            </button>
            <div className="greeting">
              <p className="greeting-line">{greeting}, {firstName}</p>
              <p className="greeting-date">{today}</p>
            </div>
          </div>
          <div className="topbar-actions">
            <button type="button" className="global-search" onClick={() => setPaletteOpen(true)} aria-keyshortcuts="Control+K Meta+K" aria-label="Search pages">
              <Icon name="search" size={17} />
              <span>Search pages</span>
              <kbd>Ctrl K</kbd>
            </button>
            <button
              type="button"
              className="theme-toggle"
              title={`Theme: ${themeLabel}. Click to change.`}
              aria-label={`Theme: ${themeLabel}. Click to change.`}
              onClick={() => setTheme((value) => value === "system" ? "light" : value === "light" ? "dark" : "system")}
            >
              <Icon name={theme === "light" ? "sun" : theme === "dark" ? "moon" : "system"} size={17} />
              <span className="theme-label">{themeLabel}</span>
            </button>
            <div className="user-menu">
              <details>
                <summary className="user-trigger">
                  <span className="avatar" aria-hidden="true">{user.display_name.trim().charAt(0).toUpperCase() || "?"}</span>
                  <span className="user-copy">
                    <span className="who-name">{user.display_name.replace(/\s*\(.*\)\s*$/, "") || user.display_name}</span>
                    <Badge tone="neutral">{ROLE_LABEL[user.role]}</Badge>
                  </span>
                  <span className="user-chevron"><Icon name="chevronDown" size={16} /></span>
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
              <Route key={p.path} path={p.path} element={allowed(p) ? p.element : <Forbidden home={home} />} />
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
          <PageHints path={location.pathname} />
          {examples.length > 0 && (
            <details className="quick-start">
              <summary>
                <span>New here? Try one of these</span>
                <span className="muted small">Only pages your account can open are listed.</span>
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
                    <span className="quick-start-link">Open this page</span>
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
            <Icon name="search" size={18} />
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
