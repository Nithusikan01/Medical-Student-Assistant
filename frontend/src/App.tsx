import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AdminRoute, ProtectedRoute } from "./components/RouteGuards";
import { AdminDocumentsPage } from "./pages/AdminDocumentsPage";
import { ChatPage } from "./pages/ChatPage";
import { LoginPage } from "./pages/LoginPage";
import { RegisterPage } from "./pages/RegisterPage";

// Split out: the charting library is ~400 kB, and this page is admin-only
// and rarely opened. Students loading the chat should not pay for it.
const AdminMonitoringPage = lazy(() =>
  import("./pages/AdminMonitoringPage").then((module) => ({
    default: module.AdminMonitoringPage,
  })),
);

const AdminTracesPage = lazy(() =>
  import("./pages/AdminTracesPage").then((module) => ({
    default: module.AdminTracesPage,
  })),
);

const AdminTraceDetailPage = lazy(() =>
  import("./pages/AdminTraceDetailPage").then((module) => ({
    default: module.AdminTraceDetailPage,
  })),
);

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      <Route
        path="/"
        element={
          <ProtectedRoute>
            <ChatPage />
          </ProtectedRoute>
        }
      />

      <Route
        path="/c/:conversationId"
        element={
          <ProtectedRoute>
            <ChatPage />
          </ProtectedRoute>
        }
      />

      <Route
        path="/admin/documents"
        element={
          <AdminRoute>
            <AdminDocumentsPage />
          </AdminRoute>
        }
      />

      <Route
        path="/admin/monitoring"
        element={
          <AdminRoute>
            <Suspense fallback={<p className="mon-boot">Loading monitoring&hellip;</p>}>
              <AdminMonitoringPage />
            </Suspense>
          </AdminRoute>
        }
      />

      <Route
        path="/admin/traces"
        element={
          <AdminRoute>
            <Suspense fallback={<p className="mon-boot">Loading traces&hellip;</p>}>
              <AdminTracesPage />
            </Suspense>
          </AdminRoute>
        }
      />

      <Route
        path="/admin/traces/:traceId"
        element={
          <AdminRoute>
            <Suspense fallback={<p className="mon-boot">Loading trace&hellip;</p>}>
              <AdminTraceDetailPage />
            </Suspense>
          </AdminRoute>
        }
      />

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
