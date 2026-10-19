import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, isTenantAdmin, useAuth } from "./auth";
import { Layout } from "./components/Layout";
import { Loading } from "./components/ui";
import { AdminDevices, AdminTenants } from "./pages/Admin";
import { CameraDetail } from "./pages/CameraDetail";
import { Cameras } from "./pages/Cameras";
import { Dashboard } from "./pages/Dashboard";
import { Events } from "./pages/Events";
import { Login } from "./pages/Login";
import { Rules } from "./pages/Rules";
import { Settings } from "./pages/Settings";

function Routed() {
  const { me, loading } = useAuth();
  if (loading) return <Loading />;
  if (!me) return <Login />;
  const superadmin = me.role === "superadmin";
  const admin = isTenantAdmin(me);
  return (
    <Routes>
      <Route element={<Layout />}>
        {superadmin ? (
          <>
            <Route path="/admin/tenants" element={<AdminTenants />} />
            <Route path="/admin/devices" element={<AdminDevices />} />
            <Route path="*" element={<Navigate to="/admin/tenants" replace />} />
          </>
        ) : (
          <>
            <Route path="/" element={<Dashboard />} />
            <Route path="/cameras" element={<Cameras />} />
            <Route path="/cameras/:id" element={<CameraDetail />} />
            <Route path="/events" element={<Events />} />
            {admin && <Route path="/rules" element={<Rules />} />}
            {admin && <Route path="/settings" element={<Settings />} />}
            <Route path="*" element={<Navigate to="/" replace />} />
          </>
        )}
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routed />
      </AuthProvider>
    </BrowserRouter>
  );
}
