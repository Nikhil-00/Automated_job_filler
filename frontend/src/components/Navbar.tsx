import { motion } from "framer-motion";
import { LogOut, RotateCcw, Zap } from "lucide-react";

interface NavbarProps {
  currentStep:   number;
  user?:         { first_name: string; last_name: string; email: string } | null;
  showReset?:    boolean;
  onResetClick?: () => void;
  onLogout?:     () => void;
}

const steps = ["Onboarding", "Profile", "Apply"];

const Navbar = ({
  currentStep,
  user,
  showReset    = false,
  onResetClick,
  onLogout,
}: NavbarProps) => {
  return (
    <motion.nav
      initial={{ y: -60, opacity: 0 }}
      animate={{ y: 0,   opacity: 1 }}
      className="fixed top-0 left-0 right-0 z-50 glass-card border-b border-glass-border px-4 sm:px-6 py-3"
    >
      <div className="max-w-6xl mx-auto flex items-center justify-between gap-4">

        {/* ── Logo ── */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <Zap className="w-5 h-5 text-primary" />
          <span className="text-base font-bold text-gradient">AutoApply AI</span>
        </div>

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

        {/* ── Right side: user info + actions ── */}
        <div className="flex items-center gap-2 flex-shrink-0">

          {/* User avatar + name */}
          {user && (
            <div className="hidden sm:flex items-center gap-2">
              <div className="w-7 h-7 rounded-full bg-gradient-to-br from-primary to-secondary
                              flex items-center justify-center text-xs font-bold text-white flex-shrink-0">
                {user.first_name.charAt(0).toUpperCase()}
              </div>
              <span className="text-sm text-muted-foreground">
                {user.first_name}
              </span>
            </div>
          )}

          {/* Reset Profile button — only shown when user has a saved profile */}
          {showReset && onResetClick && (
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={onResetClick}
              title="Reset profile — re-upload CV and refill your details"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                         text-muted-foreground border border-border hover:border-red-500/50
                         hover:text-red-400 hover:bg-red-500/10 transition-all duration-200"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Reset Profile</span>
            </motion.button>
          )}

          {/* Logout */}
          {onLogout && (
            <motion.button
              whileHover={{ scale: 1.05 }}
              whileTap={{ scale: 0.95 }}
              onClick={onLogout}
              title="Log out"
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium
                         text-muted-foreground border border-border hover:border-border
                         hover:text-foreground hover:bg-muted/40 transition-all duration-200"
            >
              <LogOut className="w-3.5 h-3.5" />
              <span className="hidden sm:inline">Logout</span>
            </motion.button>
          )}
        </div>

      </div>
    </motion.nav>
  );
};

export default Navbar;
