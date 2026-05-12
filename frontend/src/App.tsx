import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { Toaster as Sonner } from "@/components/ui/sonner";
import { Toaster } from "@/components/ui/toaster";
import { TooltipProvider } from "@/components/ui/tooltip";

import Landing           from "./pages/Landing";
import Login             from "./pages/auth/Login";
import Signup            from "./pages/auth/Signup";
import VerifyOTP         from "./pages/auth/VerifyOTP";
import Dashboard         from "./pages/Index";
import Profile           from "./pages/Profile";
import AppliedJobs       from "./pages/AppliedJobs";
import ShortlistedPortal from "./pages/ShortlistedPortal";
import NotFound          from "./pages/NotFound";
import CompanyPortal     from "./pages/CompanyPortal";
import ProtectedRoute    from "./components/ProtectedRoute";

const queryClient = new QueryClient();

const App = () => (
  <QueryClientProvider client={queryClient}>
    <TooltipProvider>
      <Toaster />
      <Sonner />
      <BrowserRouter>
        <Routes>
          {/* ── Public ── */}
          <Route path="/"              element={<Landing />} />
          <Route path="/auth/login"    element={<Login />} />
          <Route path="/auth/signup"   element={<Signup />} />
          <Route path="/auth/verify"   element={<VerifyOTP />} />
          <Route path="/company"       element={<CompanyPortal />} />
          <Route path="/company/login" element={<CompanyPortal />} />

          {/* ── Protected ── */}
          <Route
            path="/dashboard"
            element={<ProtectedRoute><Dashboard /></ProtectedRoute>}
          />
          <Route
            path="/profile"
            element={<ProtectedRoute><Profile /></ProtectedRoute>}
          />
          <Route
            path="/applications"
            element={<ProtectedRoute><AppliedJobs /></ProtectedRoute>}
          />
          <Route
            path="/shortlisted"
            element={<ProtectedRoute><ShortlistedPortal /></ProtectedRoute>}
          />

          {/* ── Fallback ── */}
          <Route path="*" element={<NotFound />} />
        </Routes>
      </BrowserRouter>
    </TooltipProvider>
  </QueryClientProvider>
);

export default App;
