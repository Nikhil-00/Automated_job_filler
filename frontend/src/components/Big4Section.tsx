import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Lock } from "lucide-react";
import JobListingsPanel from "./JobListingsPanel";

interface Company {
  key:       string;
  name:      string;
  fullName:  string;
  logo:      string;   // emoji or initials
  gradient:  string;
  enabled:   boolean;
}

const COMPANIES: Company[] = [
  {
    key:      "ey",
    name:     "EY",
    fullName: "Ernst & Young",
    logo:     "EY",
    gradient: "from-yellow-600 to-yellow-400",
    enabled:  true,
  },
  {
    key:      "deloitte",
    name:     "Deloitte",
    fullName: "Deloitte",
    logo:     "D",
    gradient: "from-green-700 to-green-500",
    enabled:  false,
  },
  {
    key:      "kpmg",
    name:     "KPMG",
    fullName: "KPMG",
    logo:     "KP",
    gradient: "from-blue-700 to-blue-500",
    enabled:  false,
  },
  {
    key:      "pwc",
    name:     "PwC",
    fullName: "PricewaterhouseCoopers",
    logo:     "PwC",
    gradient: "from-red-700 to-red-500",
    enabled:  false,
  },
];

export default function Big4Section() {
  const [selected, setSelected] = useState<string | null>(null);

  const toggle = (key: string) =>
    setSelected(prev => (prev === key ? null : key));

  const activeCompany = COMPANIES.find(c => c.key === selected);

  return (
    <motion.div
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: "auto", opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      transition={{ duration: 0.4 }}
      className="overflow-hidden mt-6"
    >
      <div className="glass-card p-5">
        <h3 className="text-sm font-semibold text-foreground mb-1">
          Big 4 Consulting Firms
        </h3>
        <p className="text-xs text-muted-foreground mb-4">
          Browse and apply to open positions directly from their career portals.
        </p>

        {/* Company sub-cards */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-2">
          {COMPANIES.map((c, i) => (
            <motion.div
              key={c.key}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.07 }}
              whileHover={c.enabled ? { scale: 1.03, y: -3 } : {}}
              whileTap={c.enabled ? { scale: 0.97 } : {}}
              onClick={() => c.enabled && toggle(c.key)}
              className={`relative glass-card p-4 text-center transition-all duration-300 overflow-hidden
                ${c.enabled ? "cursor-pointer" : "cursor-not-allowed opacity-50"}
                ${selected === c.key ? "ring-2 ring-yellow-400/60 glow-blue" : ""}
              `}
            >
              {/* Logo circle */}
              <div
                className={`w-12 h-12 rounded-xl mx-auto mb-2 bg-gradient-to-br ${c.gradient}
                  flex items-center justify-center text-white font-bold text-sm`}
              >
                {c.logo}
              </div>
              <p className="text-sm font-semibold text-foreground">{c.name}</p>
              <p className="text-xs text-muted-foreground truncate">{c.fullName}</p>

              {/* Coming soon overlay */}
              {!c.enabled && (
                <div className="absolute inset-0 flex items-center justify-center bg-background/60 backdrop-blur-sm rounded-xl">
                  <div className="relative overflow-hidden px-3 py-1.5 rounded-full border border-border bg-muted flex items-center gap-1.5">
                    <Lock className="w-3 h-3 text-muted-foreground" />
                    <span className="text-xs font-bold text-muted-foreground">
                      Coming Soon
                    </span>
                  </div>
                </div>
              )}
            </motion.div>
          ))}
        </div>

        {/* Job listings for selected company */}
        <AnimatePresence mode="wait">
          {selected && activeCompany?.enabled && (
            <JobListingsPanel
              key={selected}
              companyKey={selected}
              companyName={activeCompany.fullName}
              accentColor="yellow"
            />
          )}
        </AnimatePresence>
      </div>
    </motion.div>
  );
}
