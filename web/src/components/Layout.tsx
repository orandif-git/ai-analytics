import { NavLink, Outlet } from "react-router-dom";
import { isTenantAdmin, useAuth } from "../auth";

export function Layout() {
  const { me, logout } = useAuth();
  const admin = isTenantAdmin(me);
  const link = (to: string, text: string) => <NavLink to={to} className={({ isActive }) => (isActive ? "active" : "")}>{text}</NavLink>;
  return (
    <div className="shell">
      <aside>
        <div className="brand">AI Analytics</div>
        <nav aria-label="Main">
          {me?.role === "superadmin" ? (
            <>
              {link("/admin/tenants", "Customers")}
              {link("/admin/devices", "Edge devices")}
            </>
          ) : (
            <>
              {link("/", "Dashboard")}
              {link("/cameras", "Cameras")}
              {link("/events", "Events")}
              {admin && link("/rules", "Rules & alerts")}
              {admin && link("/settings", "Settings")}
            </>
          )}
        </nav>
        <div className="who">
          <div>{me?.tenant?.name ?? "Platform admin"}</div>
          <div className="muted">{me?.email} · {me?.role}</div>
          <button onClick={logout}>Sign out</button>
        </div>
      </aside>
      <main><Outlet /></main>
    </div>
  );
}
