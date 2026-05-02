import { motion } from "framer-motion";
import { ExternalLink, Building2 } from "lucide-react";

const BIG4 = [
  {
    name:    "Ernst & Young",
    short:   "EY",
    color:   "from-yellow-700 to-yellow-500",
    careers: "https://careers.ey.com",
  },
  {
    name:    "Deloitte",
    short:   "Deloitte",
    color:   "from-green-800 to-green-600",
    careers: "https://careers.deloitte.com",
  },
  {
    name:    "KPMG",
    short:   "KPMG",
    color:   "from-blue-800 to-blue-600",
    careers: "https://kpmgcareers.com",
  },
  {
    name:    "PricewaterhouseCoopers",
    short:   "PwC",
    color:   "from-red-800 to-red-600",
    careers: "https://careers.pwc.com",
  },
];

export default function Big4Section() {
  return (
    <motion.div
      key="big4"
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.3 }}
      className="mt-6 glass-card p-6"
    >
      <div className="flex items-center gap-3 mb-4">
        <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-yellow-700 to-yellow-500 flex items-center justify-center shrink-0">
          <Building2 className="w-4 h-4 text-white" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-foreground leading-none">Big 4 Careers</h3>
          <p className="text-xs text-muted-foreground mt-0.5">EY · Deloitte · KPMG · PwC</p>
        </div>
      </div>

      <p className="text-xs text-muted-foreground mb-5 leading-relaxed">
        Big 4 firms post jobs directly on their career portals. Visit the links below to browse
        and apply. Your applied history will reflect in your dashboard automatically.
      </p>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {BIG4.map((firm) => (
          <a
            key={firm.short}
            href={firm.careers}
            target="_blank"
            rel="noopener noreferrer"
            className="flex flex-col items-center gap-2 p-4 rounded-xl bg-muted border border-border hover:border-primary/40 hover:bg-muted/80 transition group"
          >
            <div className={`w-12 h-12 rounded-xl bg-gradient-to-br ${firm.color} flex items-center justify-center`}>
              <span className="text-white text-xs font-bold">{firm.short}</span>
            </div>
            <span className="text-xs font-medium text-foreground text-center leading-tight">{firm.name}</span>
            <span className="flex items-center gap-1 text-xs text-muted-foreground group-hover:text-primary transition">
              <ExternalLink className="w-3 h-3" /> Careers
            </span>
          </a>
        ))}
      </div>
    </motion.div>
  );
}
