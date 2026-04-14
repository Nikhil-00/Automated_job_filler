import { motion } from "framer-motion";
import { Zap } from "lucide-react";

interface NavbarProps {
  currentStep: number;
}

const steps = ["Onboarding", "Profile", "Apply"];

const Navbar = ({ currentStep }: NavbarProps) => {
  return (
    <motion.nav
      initial={{ y: -60, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="fixed top-0 left-0 right-0 z-50 glass-card border-b border-glass-border px-4 sm:px-6 py-3"
    >
      <div className="max-w-6xl mx-auto flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Zap className="w-6 h-6 text-primary" />
          <span className="text-lg font-bold text-gradient">AutoApply AI</span>
        </div>

        <div className="hidden sm:flex items-center gap-2">
          {steps.map((step, i) => (
            <div key={step} className="flex items-center gap-2">
              <div className="flex items-center gap-1.5">
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold transition-all duration-300 ${
                    i < currentStep
                      ? "gradient-blue-purple text-primary-foreground glow-blue"
                      : i === currentStep
                      ? "border-2 border-primary text-primary"
                      : "border border-muted-foreground/30 text-muted-foreground"
                  }`}
                >
                  {i < currentStep ? "✓" : i + 1}
                </div>
                <span
                  className={`text-sm ${
                    i <= currentStep ? "text-foreground" : "text-muted-foreground"
                  }`}
                >
                  {step}
                </span>
              </div>
              {i < steps.length - 1 && (
                <div
                  className={`w-8 h-px ${
                    i < currentStep ? "bg-primary" : "bg-muted"
                  }`}
                />
              )}
            </div>
          ))}
        </div>

        <div className="sm:hidden text-sm text-muted-foreground">
          Step {currentStep + 1}/3
        </div>
      </div>
    </motion.nav>
  );
};

export default Navbar;
