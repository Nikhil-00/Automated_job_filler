import { motion } from "framer-motion";
import { Link } from "react-router-dom";
import { Construction } from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";

interface ComingSoonProps {
  portalName: string;
}

const ComingSoon = ({ portalName }: ComingSoonProps) => (
  <div className="min-h-screen flex items-center justify-center px-4">
    <AnimatedBackground />

    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.4 }}
      className="text-center max-w-sm"
    >
      <div className="glass-card p-10 rounded-2xl glow-purple">
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-br from-violet-600 to-pink-600 mx-auto mb-5 flex items-center justify-center">
          <Construction className="w-8 h-8 text-white" />
        </div>
        <h1 className="text-2xl font-bold text-gradient mb-2">{portalName} Portal</h1>
        <p className="text-muted-foreground text-sm mb-6">
          This portal is under construction and will be available soon.
          We're working hard to bring you an amazing experience.
        </p>
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-sm text-primary hover:underline font-medium"
        >
          ← Back to portal selection
        </Link>
      </div>
    </motion.div>
  </div>
);

export default ComingSoon;
