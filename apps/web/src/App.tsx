import { createContext, useContext, useState, useEffect, useRef } from "react";
import {
  Routes,
  Route,
  NavLink,
  Navigate,
  useNavigate,
  Link,
} from "react-router-dom";
import {
  LayoutDashboard,
  Users,
  Upload,
  Copy,
  Send,
  Inbox,
  LifeBuoy,
  History,
  Search,
  LogOut,
  ShieldCheck,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Moon,
  Sun,
  FolderKanban,
} from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useData, useAction, User, Page, can, label } from "./api";
import { Field, ErrorBox, Loading, HistoryBack } from "./ui";
import { Dashboard, AuditPage } from "./Overview";
import { JudgeConversation, Notifications } from "./Inbox";
import { JudgeDirectory } from "./JudgeDirectory";
import { Imports, ImportWizard, Duplicates, DuplicateDetail } from "./Imports";
import { Campaigns, CampaignNew, CampaignDetail, Outbox } from "./Campaigns";
import { Tickets, TicketNew, TicketDetail } from "./Tickets";
import { Competitions, CompetitionCategory, PilotDetail, DeletedCompetitions } from "./Pilots";
const Auth = createContext<User | undefined>(undefined);
export const useUser = () => useContext(Auth);
const loginSchema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});
type Theme = "light" | "dark";
function ThemeToggle({ theme, onToggle }: { theme: Theme; onToggle: () => void }) {
  return (
    <button
      type="button"
      className="theme-toggle"
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      aria-pressed={theme === "dark"}
      title={theme === "dark" ? "Light mode" : "Dark mode"}
      onClick={onToggle}
    >
      {theme === "dark" ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}
function Login({ theme, onToggleTheme }: { theme: Theme; onToggleTheme: () => void }) {
  const action = useAction();
  const navigate = useNavigate();
  const form = useForm<z.infer<typeof loginSchema>>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  });
  return (
    <div className="login-page">
      <div className="login-theme-toggle">
        <ThemeToggle theme={theme} onToggle={onToggleTheme} />
      </div>
      <main className="login-card">
        <div className="login-identity">
          <div className="brand-symbol">M</div>
          <h1>MIST Deck</h1>
        </div>
        <h2>Sign in</h2>
        <form
          onSubmit={form.handleSubmit(async (values) => {
            try {
              await action.mutateAsync({ path: "/auth/login", body: values });
              navigate("/dashboard");
            } catch {}
          })}
        >
          <Field label="Email">
            <input
              type="email"
              autoComplete="username"
              {...form.register("email")}
            />
          </Field>
          <Field label="Password">
            <input
              type="password"
              autoComplete="current-password"
              {...form.register("password")}
            />
          </Field>
          <ErrorBox
            error={
              Object.values(form.formState.errors)[0]?.message || action.error
            }
          />
          <button className="primary" disabled={action.isPending}>
            Sign in
          </button>
        </form>
      </main>
    </div>
  );
}
const navGroups = [
  { label: "Workspace", items: [["/dashboard", "Overview", LayoutDashboard, ""]] },
  {
    label: "Judge handling",
    items: [
      ["/judges", "Judge directory", Users, "judges"],
      ["/imports", "Imports", Upload, "imports"],
      ["/duplicates", "Duplicate review", Copy, "imports"],
      ["/competitions", "Competitions", FolderKanban, "judges"],
      ["/campaigns", "Campaigns", Send, "campaigns"],
      ["/outbox", "Sandbox outbox", Inbox, "outbox"],
    ],
  },
  { label: "Competitions tickets", items: [["/tickets", "Tickets", LifeBuoy, "tickets"]] },
  {
    label: "Administration",
    items: [
      ["/audit", "Audit trail", History, "audit"],
    ],
  },
] as const;
function Guard({
  permission,
  children,
}: {
  permission: string;
  children: React.ReactNode;
}) {
  const user = useUser();
  return can(user, permission) ? (
    children
  ) : (
    <div className="empty">
      <h1>Access restricted</h1>
      <p>Your role does not have permission to open this module.</p>
      <Link to="/dashboard">Return to overview</Link>
    </div>
  );
}
function BackgroundNotice() {
  const user = useUser();
  const messages = useData<Page>("/outbox?page_size=100", can(user, "outbox"));
  const previous = useRef<Record<string, string>>({});
  const [notice, setNotice] = useState("");
  useEffect(() => {
    if (!messages.data) return;
    const changed = messages.data.items.filter(
      (m) =>
        ["queued", "sending"].includes(previous.current[m.id]) &&
        ["sent", "failed"].includes(m.status),
    );
    if (changed.length)
      setNotice(
        `${changed.length} sandbox message${changed.length === 1 ? "" : "s"} finished processing. Check the outbox for delivery results.`,
      );
    previous.current = Object.fromEntries(
      messages.data.items.map((m) => [m.id, m.status]),
    );
  }, [messages.data]);
  return notice ? (
    <div className="toast" role="status">
      <span>{notice}</span>
      <button aria-label="Dismiss notification" onClick={() => setNotice("")}>
        ×
      </button>
    </div>
  ) : null;
}
export default function App() {
  const auth = useData<User>("/auth/me");
  const action = useAction();
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [menu, setMenu] = useState(false);
  const [collapsed, setCollapsed] = useState(
    () => window.localStorage.getItem("mist-sidebar-collapsed") === "true",
  );
  const [theme, setTheme] = useState<Theme>(() =>
    window.localStorage.getItem("mist-theme") === "dark" ? "dark" : "light",
  );
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("mist-theme", theme);
  }, [theme]);
  useEffect(() => {
    window.localStorage.setItem("mist-sidebar-collapsed", String(collapsed));
  }, [collapsed]);
  const toggleTheme = () => setTheme((current) => current === "dark" ? "light" : "dark");
  if (auth.isPending) return <Loading />;
  if (!auth.data || auth.error)
    return (
      <Routes>
        <Route path="/login" element={<Login theme={theme} onToggleTheme={toggleTheme} />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  const user = auth.data;
  return (
    <Auth.Provider value={user}>
      <BackgroundNotice />
      <div className={collapsed ? "app sidebar-collapsed" : "app"}>
        <aside className={`${menu ? "sidebar open" : "sidebar"}${collapsed ? " collapsed" : ""}`}>
          <div className="sidebar-header">
            <Link to="/dashboard" className="brand" title="MIST Deck">
              <span className="brand-symbol">M</span>
              <span className="brand-copy">MIST Deck</span>
            </Link>
            <button
              type="button"
              className="collapse-button"
              aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              aria-expanded={!collapsed}
              title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              onClick={() => setCollapsed((value) => !value)}
            >
              {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
            </button>
          </div>
          <button className="mobile-close" onClick={() => setMenu(false)}>
            Close navigation
          </button>
          <div className="sidebar-navigation">
            {navGroups.map((group) => {
              const items = group.items.filter(
                ([, name, , permission]) =>
                  !permission ||
                  can(user, permission) ||
                  (name === "Judge directory" && can(user, "imports")),
              );
              if (!items.length) return null;
              return (
                <nav className="nav-group" aria-label={group.label} key={group.label}>
                  <div className="nav-label">{group.label}</div>
                  {items.map(([path, name, Icon]) => (
                    <NavLink
                      onClick={() => setMenu(false)}
                      key={path}
                      to={path}
                      title={name}
                      aria-label={name}
                    >
                      <Icon size={18} />
                      <span className="nav-text">{name}</span>
                    </NavLink>
                  ))}
                </nav>
              );
            })}
          </div>
          <div className="sidebar-bottom">
            <div className="workspace-tag">
              <span className="avatar">NJ</span>
              <div className="workspace-copy">MIST NJ</div>
            </div>
          </div>
        </aside>
        <div className="main-shell">
          <header className="topbar">
            <HistoryBack />
            <button
              className="menu-button"
              aria-label="Toggle navigation"
              onClick={() => setMenu(!menu)}
            >
              <Menu size={20} />
            </button>
            <form
              className="global-search"
              onSubmit={(e) => {
                e.preventDefault();
                navigate(
                  (can(user, "judges") || can(user, "imports")
                    ? "/judges"
                    : "/tickets") +
                    "?q=" +
                    encodeURIComponent(search),
                );
              }}
            >
              <Search size={17} />
              <input
                aria-label="Global search"
                placeholder={
                  can(user, "judges") || can(user, "imports")
                    ? "Search judges, emails, organizations…"
                    : "Search assigned tickets…"
                }
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </form>
            <div className="sandbox">
              <ShieldCheck size={15} /> SANDBOX EMAIL MODE
            </div>
            <Notifications />
            <ThemeToggle theme={theme} onToggle={toggleTheme} />
            <div className="user">
              <span className="avatar">
                {user.full_name
                  .split(" ")
                  .map((s) => s[0])
                  .join("")
                  .slice(0, 2)}
              </span>
              <span>
                {user.full_name}
                <small>{label(user.role)}</small>
              </span>
            </div>
            <button
              aria-label="Sign out"
              onClick={() => action.mutate({ path: "/auth/logout" })}
            >
              <LogOut size={17} />
            </button>
          </header>
          <main className="content">
            <Routes>
              <Route
                path="/login"
                element={<Navigate to="/dashboard" replace />}
              />
              <Route path="/dashboard" element={<Dashboard />} />
              <Route path="/judges" element={<JudgeDirectory />} />
              <Route path="/contacts" element={<Navigate to="/judges" replace />} />
              <Route path="/judges/:id" element={<Guard permission="campaigns"><JudgeConversation /></Guard>} />
              <Route
                path="/imports"
                element={
                  <Guard permission="imports">
                    <Imports />
                  </Guard>
                }
              />
              <Route
                path="/imports/new"
                element={
                  <Guard permission="imports">
                    <ImportWizard />
                  </Guard>
                }
              />
              <Route
                path="/imports/:id"
                element={
                  <Guard permission="imports">
                    <ImportWizard />
                  </Guard>
                }
              />
              <Route
                path="/duplicates"
                element={
                  <Guard permission="imports">
                    <Duplicates />
                  </Guard>
                }
              />
              <Route
                path="/duplicates/:id"
                element={
                  <Guard permission="imports">
                    <DuplicateDetail />
                  </Guard>
                }
              />
              <Route
                path="/competitions"
                element={<Guard permission="judges"><Competitions /></Guard>}
              />
              <Route
                path="/competitions/:category"
                element={<Guard permission="judges"><CompetitionCategory /></Guard>}
              />
              <Route
                path="/competitions/:category/:id"
                element={<Guard permission="judges"><PilotDetail /></Guard>}
              />
              <Route path="/pilots" element={<Navigate to="/competitions" replace />} />
              <Route path="/pilots/:id" element={<Guard permission="judges"><PilotDetail /></Guard>} />
              <Route path="/campaigns/conversations/judges/:id" element={<Guard permission="campaigns"><JudgeConversation /></Guard>} />
              <Route
                path="/campaigns"
                element={
                  <Guard permission="campaigns">
                    <Campaigns />
                  </Guard>
                }
              />
              <Route
                path="/campaigns/new"
                element={
                  <Guard permission="campaigns">
                    <CampaignNew />
                  </Guard>
                }
              />
              <Route
                path="/campaigns/:id"
                element={
                  <Guard permission="campaigns">
                    <CampaignDetail />
                  </Guard>
                }
              />
              <Route
                path="/outbox"
                element={
                  <Guard permission="outbox">
                    <Outbox />
                  </Guard>
                }
              />
              <Route
                path="/tickets"
                element={
                  <Guard permission="tickets">
                    <Tickets />
                  </Guard>
                }
              />
              <Route
                path="/tickets/new"
                element={
                  <Guard permission="tickets">
                    <TicketNew />
                  </Guard>
                }
              />
              <Route
                path="/tickets/:id"
                element={
                  <Guard permission="tickets">
                    <TicketDetail />
                  </Guard>
                }
              />
              <Route
                path="/audit"
                element={
                  <Guard permission="audit">
                    <AuditPage />
                  </Guard>
                }
              />
              <Route
                path="/competitions/deletions"
                element={<Guard permission="judges"><DeletedCompetitions /></Guard>}
              />
              <Route path="/settings/:kind" element={<Navigate to="/dashboard" replace />} />
              <Route path="/" element={<Navigate to="/dashboard" replace />} />
              <Route
                path="*"
                element={
                  <div className="empty">
                    <h1>Page not found</h1>
                    <Link to="/dashboard">Return to overview</Link>
                  </div>
                }
              />
            </Routes>
          </main>
          <footer className="footer">
            MIST Deck <span>Local prototype · Sandbox email</span>
          </footer>
        </div>
      </div>
    </Auth.Provider>
  );
}
