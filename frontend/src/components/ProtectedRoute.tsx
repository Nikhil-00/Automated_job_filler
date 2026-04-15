/**
 * ProtectedRoute
 * ───────────────
 * Wraps a route that requires authentication.
 * Redirects to /auth/login if no JWT token is found in localStorage.
 */
import { Navigate } from "react-router-dom";
import { isLoggedIn } from "@/lib/auth";

interface ProtectedRouteProps {
  children: React.ReactNode;
}

const ProtectedRoute = ({ children }: ProtectedRouteProps) => {
  if (!isLoggedIn()) {
    return <Navigate to="/auth/login" replace />;
  }
  return <>{children}</>;
};

export default ProtectedRoute;
