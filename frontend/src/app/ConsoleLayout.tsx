import { NavLink, Outlet } from "react-router-dom";

const navItems = [
  { to: "/", label: "Overview", end: true },
  { to: "/intake", label: "Data Intake" },
  { to: "/saved", label: "Saved Data" },
  { to: "/graph", label: "Graph Explorer" },
  { to: "/council", label: "Council & Ask" },
];

export const ConsoleLayout = () => (
  <div className="shell">
    <aside className="sidebar">
      <p className="sidebar-eyebrow">onTro Finance</p>
      <h1>Operations Workbench</h1>
      <p className="sidebar-copy">
        Internal console for ingest review, graph inspection, council handling, and reasoning support.
      </p>

      <nav aria-label="Primary" className="nav">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            className={({ isActive }) => `nav-link${isActive ? " is-active" : ""}`}
            end={item.end}
            to={item.to}
          >
            {item.label}
          </NavLink>
        ))}
      </nav>
    </aside>

    <main className="main-panel">
      <Outlet />
    </main>
  </div>
);
