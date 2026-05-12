import { motion } from "framer-motion";
import { LogOut } from "lucide-react";
import { useNavigate, useLocation } from "react-router-dom";

interface NavbarProps {
  currentStep: number;
  user?:       { first_name: string; last_name: string; email: string } | null;
  onLogout?:   () => void;
  showAppNav?: boolean;
}

const steps = ["Onboarding", "Profile", "Apply"];

const APP_NAV = [
  { label: "Jobs",            path: "/dashboard"    },
  { label: "My Applications", path: "/applications" },
  { label: "Shortlisted",     path: "/shortlisted"  },
];

const Navbar = ({
  currentStep,
  user,
  onLogout,
  showAppNav = false,
}: NavbarProps) => {
  const navigate = useNavigate();
  const { pathname } = useLocation();

  return (
    <motion.nav
      initial={{ y: -60, opacity: 0 }}
      animate={{ y: 0,   opacity: 1 }}
      className="fixed top-0 left-0 right-0 z-50 bg-white border-b border-border"
      style={{ boxShadow: "0 1px 4px 0 rgb(0 0 0 / 0.08)" }}
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6
                      flex items-center justify-between gap-4
                      h-[64px] sm:h-[72px] lg:h-[80px]">

        {/* ── Logo ── */}
        <div
          className="flex items-center flex-shrink-0 cursor-pointer"
          onClick={() => showAppNav && navigate("/dashboard")}
        >
          <img
            src="/logo.png"
            alt="NewAgeNaukri"
            className="h-[44px] sm:h-[54px] lg:h-[62px] w-auto object-contain"
          />
        </div>

        {/* ── App nav tabs (dashboard / applications / shortlisted) ── */}
        {showAppNav ? (
          <div className="hidden sm:flex items-center gap-1">
            {APP_NAV.map((link) => {
              const active = pathname === link.path;
              return (
                <button
                  key={link.path}
                  onClick={() => navigate(link.path)}
                  className={`px-4 py-2 rounded-lg text-base font-medium transition-all duration-200
                    ${active
                      ? "bg-primary/15 text-primary border border-primary/30"
                      : "text-muted-foreground hover:text-foreground hover:bg-muted/40"
                    }`}
                >
                  {link.label}
                </button>
              );
            })}
          </div>
        ) : (
          <>
            {/* ── Step indicators (desktop) ── */}
            <div className="hidden sm:flex items-center gap-2">
              {steps.map((step, i) => (
                <div key={step} className="flex items-center gap-2">
                  <div className="flex items-center gap-1.5">
                    <div
                      className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold transition-all duration-300
                        ${i < currentStep
                          ? "gradient-blue-purple text-primary-foreground glow-blue"
                          : i === currentStep
                          ? "border-2 border-primary text-primary"
                          : "border border-muted-foreground/30 text-muted-foreground"
                        }`}
                    >
                      {i < currentStep ? "✓" : i + 1}
                    </div>
                    <span className={`text-sm ${i <= currentStep ? "text-foreground" : "text-muted-foreground"}`}>
                      {step}
                    </span>
                  </div>
                  {i < steps.length - 1 && (
                    <div className={`w-8 h-px ${i < currentStep ? "bg-primary" : "bg-muted"}`} />
                  )}
                </div>
              ))}
            </div>

            {/* ── Mobile step counter ── */}
            <div className="sm:hidden text-sm text-muted-foreground">
              Step {currentStep + 1}/3
            </div>
          </>
        )}

        {/* ── Right side: user info + actions ── */}
        <div className="flex items-center gap-2 flex-shrink-0">

          {/* User avatar + name — click to open profile */}
          {user && (
            <button
              onClick={() => navigate("/profile")}
              title="Edit your profile"
              className="hidden sm:flex items-center gap-2 px-2 py-1 rounded-lg
                         hover:bg-muted transition-colors duration-150"
            >
              <div className="w-9 h-9 rounded-full bg-gradient-to-br from-primary to-secondary
                              flex items-center justify-center text-sm font-bold text-white flex-shrink-0">
                {`${user.first_name.charAt(0)}${user.last_name?.charAt(0) ?? ""}`.toUpperCase()}
              </div>
              <span className="text-base font-medium text-foreground">
                {user.first_name}
              </span>
            </button>
          )}

          {/* Logout */}
          {onLogout && (
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={onLogout}
              title="Log out"
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                         text-muted-foreground border border-border hover:border-border
                         hover:text-foreground hover:bg-muted/40 transition-all duration-200"
            >
              <LogOut className="w-4 h-4" />
              <span className="hidden sm:inline">Logout</span>
            </motion.button>
          )}
        </div>

      </div>

      {/* ── Mobile app nav (below main row) ── */}
      {showAppNav && (
        <div className="sm:hidden flex border-t border-glass-border">
          {APP_NAV.map((link) => {
            const active = pathname === link.path;
            return (
              <button
                key={link.path}
                onClick={() => navigate(link.path)}
                className={`flex-1 py-2 text-xs font-medium transition-all duration-200
                  ${active ? "text-primary border-b-2 border-primary" : "text-muted-foreground"}`}
              >
                {link.label}
              </button>
            );
          })}
        </div>
      )}
    </motion.nav>
  );
};

export default Navbar;
