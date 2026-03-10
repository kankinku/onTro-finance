import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { SettingsDialog } from "../components/SettingsDialog";
import { useI18n } from "./i18n";

export const ConsoleLayout = () => {
  const { t } = useI18n();
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  const navItems = [
    { to: "/", label: t("layout.nav.overview"), end: true },
    { to: "/intake", label: t("layout.nav.intake") },
    { to: "/saved", label: t("layout.nav.saved") },
    { to: "/graph", label: t("layout.nav.graph") },
    { to: "/council", label: t("layout.nav.council") },
  ];

  return (
    <div className="shell">
      <aside className="sidebar">
        <p className="sidebar-eyebrow">{t("layout.eyebrow")}</p>
        <h1>{t("layout.title")}</h1>
        <p className="sidebar-copy">{t("layout.copy")}</p>

        <nav aria-label={t("layout.navLabel")} className="nav">
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

        <div className="sidebar-footer">
          <button
            aria-label={t("settings.openButton")}
            className="settings-trigger"
            onClick={() => setIsSettingsOpen(true)}
            type="button"
          >
            <svg aria-hidden="true" className="settings-trigger-icon" viewBox="0 0 24 24">
              <path
                d="M10.4 2.2h3.2l.5 2.4c.4.1.8.3 1.2.5l2.2-1.1 2.3 2.3-1.1 2.2c.2.4.4.8.5 1.2l2.4.5v3.2l-2.4.5c-.1.4-.3.8-.5 1.2l1.1 2.2-2.3 2.3-2.2-1.1c-.4.2-.8.4-1.2.5l-.5 2.4h-3.2l-.5-2.4c-.4-.1-.8-.3-1.2-.5l-2.2 1.1-2.3-2.3 1.1-2.2c-.2-.4-.4-.8-.5-1.2l-2.4-.5v-3.2l2.4-.5c.1-.4.3-.8.5-1.2L3.4 6.1l2.3-2.3 2.2 1.1c.4-.2.8-.4 1.2-.5z"
                fill="none"
                stroke="currentColor"
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="1.5"
              />
              <circle cx="12" cy="12" fill="none" r="3.2" stroke="currentColor" strokeWidth="1.5" />
            </svg>
            <span>{t("settings.openButton")}</span>
          </button>
        </div>
      </aside>

      <main className="main-panel">
        <Outlet />
      </main>

      <SettingsDialog isOpen={isSettingsOpen} onClose={() => setIsSettingsOpen(false)} />
    </div>
  );
};
