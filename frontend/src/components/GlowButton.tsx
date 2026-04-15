import { motion } from "framer-motion";
import { Loader2 } from "lucide-react";

interface GlowButtonProps {
  children:  React.ReactNode;
  onClick?:  () => void;
  disabled?: boolean;
  loading?:  boolean;
  variant?:  "primary" | "orange" | "danger";
  className?: string;
  pulse?:    boolean;
  type?:     "button" | "submit" | "reset";
}

const GlowButton = ({ children, onClick, disabled, loading, variant = "primary", className = "", pulse, type = "button" }: GlowButtonProps) => {
  const bg =
    variant === "orange" ? "from-neon-orange to-neon-red"  :
    variant === "danger"  ? "from-red-600 to-red-700"       :
                            "from-primary to-secondary";

  const glow = variant === "danger" ? "" : (!disabled ? "glow-blue hover:shadow-lg" : "");

  return (
    <motion.button
      type={type}
      whileHover={disabled ? {} : { scale: 1.03 }}
      whileTap={disabled ? {} : { scale: 0.97 }}
      onClick={onClick}
      disabled={disabled || loading}
      className={`relative px-8 py-3 rounded-lg font-semibold text-foreground bg-gradient-to-r ${bg}
        transition-all duration-300 disabled:opacity-40 disabled:cursor-not-allowed
        ${pulse && !disabled ? "animate-pulse-glow" : ""} ${glow} ${className}`}
    >
      {loading ? (
        <span className="flex items-center gap-2">
          <Loader2 className="w-4 h-4 animate-spin" />
          Processing...
        </span>
      ) : children}
    </motion.button>
  );
};

export default GlowButton;
