import { useEffect, useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { Loader2 } from "lucide-react";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";

import Landing         from "./pages/Landing";
import Login           from "./pages/auth/Login";
import Signup          from "./pages/auth/Signup";
import VerifyOTP       from "./pages/auth/VerifyOTP";
import Dashboard       from "./pages/Index";
import CVBuilder       from "./pages/CVBuilder";
import ProfileSetup    from "./pages/ProfileSetup";
import NotFound        from "./pages/NotFound";
import CompanyPortal   from "./pages/CompanyPortal";
import AdminPortal     from "./pages/AdminPortal";
import ProtectedRoute  from "./components/ProtectedRoute";
import { AutomationProvider } from "./contexts/AutomationContext";
import { isLoggedIn }        from "./lib/auth";
import { getCVBuilder }      from "./lib/cvBuilderApi";

// ── CV completion guard (wraps /dashboard) ────────────────────────────────────

const CVGuard = ({ children }: { children: React.ReactNode }) => {
  const [status, setStatus] = useState<"checking" | "ok" | "redirect">("checking");

  useEffect(() => {
    if (!isLoggedIn()) { setStatus("ok"); return; }   // auth guard handles this
    getCVBuilder()
      .then(() => setStatus("ok"))
      .catch((err: Error) => {
        // NOT_FOUND → mandatory CV builder; any other error → let through
        setStatus(err.message === "NOT_FOUND" ? "redirect" : "ok");
      });
  }, []);

  if (status === "checking") {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }
  if (status === "redirect") return <Navigate to="/cv-builder" replace />;
  return <>{children}</>;
};

// ── If already logged-in + has CV, skip /cv-builder back to dashboard ─────────

const CVBuilderGuard = ({ children }: { children: React.ReactNode }) => {
  const location = useLocation();
  // Allow explicit ?edit=1 to bypass (future feature: "Edit CV" from dashboard)
  const forceEdit = new URLSearchParams(location.search).get("edit") === "1";
  const [status, setStatus] = useState<"checking" | "ok">("checking");

  useEffect(() => {
    if (forceEdit || !isLoggedIn()) { setStatus("ok"); return; }
    // Don't redirect — users can always revisit /cv-builder to update their CV
    setStatus("ok");
  }, [forceEdit]);

  if (status === "checking") {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
      </div>
    );
  }
  return <>{children}</>;
};

// ── App ───────────────────────────────────────────────────────────────────────

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <AutomationProvider>
        <Toaster />
        <Sonner />
        <BrowserRouter>
          <Routes>
            {/* ── Public ── */}
            <Route path="/"                element={<Landing />} />
            <Route path="/auth/login"      element={<Login />} />
            <Route path="/auth/signup"     element={<Signup />} />
            <Route path="/auth/verify"     element={<VerifyOTP />} />
            <Route path="/admin"           element={<AdminPortal />} />
            <Route path="/admin/login"     element={<AdminPortal />} />
            <Route path="/company"         element={<CompanyPortal />} />
            <Route path="/company/login"   element={<CompanyPortal />} />

            {/* ── CV Builder (protected — mandatory for new users) ── */}
            <Route
              path="/cv-builder"
              element={
                <ProtectedRoute>
                  <CVBuilderGuard>
                    <CVBuilder />
                  </CVBuilderGuard>
                </ProtectedRoute>
              }
            />

            {/* ── Profile Setup (protected — fills salary/notice after CV Builder) ── */}
            <Route
              path="/profile-setup"
              element={
                <ProtectedRoute>
                  <CVGuard>
                    <ProfileSetup />
                  </CVGuard>
                </ProtectedRoute>
              }
            />

            {/* ── Dashboard (protected + requires completed CV) ── */}
            <Route
              path="/dashboard"
              element={
                <ProtectedRoute>
                  <CVGuard>
                    <Dashboard />
                  </CVGuard>
                </ProtectedRoute>
              }
            />

            {/* ── Fallback ── */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </BrowserRouter>
      </AutomationProvider>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
