import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Linkedin, Briefcase, Rocket, History, Star } from "lucide-react";
import PlatformSection from "./PlatformSection";
import AppliedJobs from "@/pages/AppliedJobs";
import ShortlistedJobs from "@/pages/ShortlistedJobs";
import { ProfileData } from "@/lib/mockApi";

const platforms = [
  {
    id: "linkedin" as const,
    name: "LinkedIn",
    label: "Apply on LinkedIn",
    icon: Linkedin,
    gradient: "from-[hsl(210,80%,40%)] to-[hsl(210,90%,55%)]",
    enabled: true,
  },
  {
    id: "naukri" as const,
    name: "Naukri",
    label: "Apply on Naukri",
    icon: Briefcase,
    gradient: "from-[hsl(25,95%,45%)] to-[hsl(35,95%,55%)]",
    enabled: true,
  },
  {
    id: "wellfound" as const,
    name: "Wellfound",
    label: "Coming Soon",
    icon: Rocket,
    gradient: "from-[hsl(220,20%,20%)] to-[hsl(220,20%,30%)]",
    enabled: false,
  },
];

interface StepPlatformProps { profileData: ProfileData; }

type ActiveView = "linkedin" | "naukri" | "wellfound" | "applied_jobs" | "shortlisted" | null;

const StepPlatform = ({ profileData }: StepPlatformProps) => {
  const [selected, setSelected] = useState<ActiveView>(null);

  const toggle = (id: ActiveView) => setSelected((prev) => (prev === id ? null : id));

  return (
    <motion.div
      initial={{ opacity: 0, x: 80 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -80 }}
      transition={{ duration: 0.4 }}
      className="w-full max-w-5xl mx-auto"
    >
      <h2 className="text-2xl font-bold text-gradient mb-6 text-center">Choose Job Platform</h2>

      {/* Platform cards + Applied Jobs button */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4 mb-4">
        {platforms.map((p, i) => (
          <motion.div
            key={p.id}
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.1 }}
            whileHover={p.enabled ? { scale: 1.03, y: -4 } : {}}
            whileTap={p.enabled ? { scale: 0.98 } : {}}
            onClick={() => p.enabled && toggle(p.id)}
            className={`relative glass-card p-6 text-center cursor-pointer transition-all duration-300 overflow-hidden
              ${!p.enabled ? "opacity-50 cursor-not-allowed" : ""}
              ${selected === p.id ? "ring-2 ring-primary glow-blue" : ""}
            `}
          >
            <div className={`w-14 h-14 rounded-xl mx-auto mb-3 bg-gradient-to-br ${p.gradient} flex items-center justify-center`}>
              <p.icon className="w-7 h-7 text-foreground" />
            </div>
            <h3 className="font-semibold text-foreground mb-1">{p.name}</h3>
            <p className="text-xs text-muted-foreground">{p.label}</p>

            {!p.enabled && (
              <div className="absolute inset-0 flex items-center justify-center bg-background/60 backdrop-blur-sm">
                <div className="relative overflow-hidden px-4 py-2 rounded-full border border-border bg-muted">
                  <span className="text-sm font-bold text-muted-foreground">Coming Soon</span>
                  <div className="absolute inset-0 bg-gradient-to-r from-transparent via-foreground/5 to-transparent animate-shimmer" />
                </div>
              </div>
            )}
          </motion.div>
        ))}

        {/* Applied Jobs card */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.3 }}
          whileHover={{ scale: 1.03, y: -4 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => toggle("applied_jobs")}
          className={`glass-card p-6 text-center cursor-pointer transition-all duration-300
            ${selected === "applied_jobs" ? "ring-2 ring-purple-500 glow-purple" : ""}
          `}
        >
          <div className="w-14 h-14 rounded-xl mx-auto mb-3 bg-gradient-to-br from-purple-700 to-purple-500 flex items-center justify-center">
            <History className="w-7 h-7 text-foreground" />
          </div>
          <h3 className="font-semibold text-foreground mb-1">Applied Jobs</h3>
          <p className="text-xs text-muted-foreground">View your history</p>
        </motion.div>

        {/* Shortlisted card */}
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.35 }}
          whileHover={{ scale: 1.03, y: -4 }}
          whileTap={{ scale: 0.98 }}
          onClick={() => toggle("shortlisted")}
          className={`glass-card p-6 text-center cursor-pointer transition-all duration-300
            ${selected === "shortlisted" ? "ring-2 ring-violet-500 glow-purple" : ""}
          `}
        >
          <div className="w-14 h-14 rounded-xl mx-auto mb-3 bg-gradient-to-br from-violet-700 to-violet-400 flex items-center justify-center">
            <Star className="w-7 h-7 text-foreground" />
          </div>
          <h3 className="font-semibold text-foreground mb-1">Shortlisted</h3>
          <p className="text-xs text-muted-foreground">Jobs you're shortlisted for</p>
        </motion.div>
      </div>

      {/* Expanded panel */}
      <AnimatePresence mode="wait">
        {selected === "linkedin" && <PlatformSection key="linkedin" platform="linkedin" profileData={profileData} />}
        {selected === "naukri"   && <PlatformSection key="naukri"   platform="naukri"   profileData={profileData} />}
        {selected === "applied_jobs" && (
          <motion.div
            key="applied_jobs"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
            className="mt-6"
          >
            <AppliedJobs />
          </motion.div>
        )}
        {selected === "shortlisted" && (
          <motion.div
            key="shortlisted"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -20 }}
            transition={{ duration: 0.3 }}
            className="mt-6"
          >
            <ShortlistedJobs />
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default StepPlatform;
