import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Briefcase, X, Search, ChevronDown, Loader2,
  CheckCircle, Clock, XCircle, Eye, Sparkles,
} from "lucide-react";
import { getAllApplications, PortalApplication } from "@/lib/portalApi";
import Navbar             from "@/components/Navbar";
import AnimatedBackground from "@/components/AnimatedBackground";
import { getMe, logout }  from "@/lib/auth";

// ── Status helpers ────────────────────────────────────────────────────────────

const STATUS_CONFIG: Record<string, { label: string; icon: React.ElementType; cls: string }> = {
  pending: {
    label: "Pending",
    icon:  Clock,
    cls:   "bg-amber-50 text-amber-700 border-amber-200",
  },
  reviewed: {
    label: "Reviewed",
    icon:  Eye,
    cls:   "bg-blue-50 text-blue-700 border-blue-200",
  },
  shortlisted: {
    label: "Shortlisted",
    icon:  CheckCircle,
    cls:   "bg-emerald-50 text-emerald-700 border-emerald-200",
  },
  rejected: {
    label: "Rejected",
    icon:  XCircle,
    cls:   "bg-red-50 text-red-600 border-red-200",
  },
};

function StatusBadge({ status }: { status: string }) {
  const cfg  = STATUS_CONFIG[status] ?? STATUS_CONFIG.pending;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border ${cfg.cls}`}>
      <Icon className="w-3 h-3" />
      {cfg.label}
    </span>
  );
}

function SourceBadge({ source }: { source: string }) {
  if (source === "Match") {
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border bg-primary/10 text-primary border-primary/30">
        <Sparkles className="w-3 h-3" />
        AI Match
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border bg-primary/10 text-primary border-primary/30">
      <Briefcase className="w-3 h-3" />
      Portal
    </span>
  );
}

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

// ── Detail Drawer ─────────────────────────────────────────────────────────────

function AppDrawer({ app, onClose }: { app: PortalApplication; onClose: () => void }) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
      onClick={onClose}
    >
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />

      <motion.div
        initial={{ opacity: 0, y: 40, scale: 0.97 }}
        animate={{ opacity: 1, y: 0,  scale: 1 }}
        exit={{ opacity: 0,  y: 40, scale: 0.97 }}
        transition={{ duration: 0.25 }}
        onClick={(e) => e.stopPropagation()}
        className="relative z-10 w-full max-w-lg glass-card p-6 space-y-4 max-h-[85vh] overflow-y-auto"
      >
        {/* header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <h3 className="text-lg font-bold text-foreground truncate">{app.title}</h3>
            <p className="text-sm text-muted-foreground">{app.company}</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition shrink-0">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* badges */}
        <div className="flex flex-wrap gap-2">
          <StatusBadge status={app.status} />
          <SourceBadge source={app.source} />
        </div>

        {/* meta grid */}
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <div>
            <p className="text-xs text-muted-foreground mb-0.5">Location</p>
            <p className="text-foreground">{app.location || "—"}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-0.5">Applied / Matched</p>
            <p className="text-foreground">{fmtDate(app.applied_at)}</p>
          </div>
          {app.work_mode && (
            <div>
              <p className="text-xs text-muted-foreground mb-0.5">Work Mode</p>
              <p className="text-foreground capitalize">{app.work_mode}</p>
            </div>
          )}
          {app.job_type && (
            <div>
              <p className="text-xs text-muted-foreground mb-0.5">Job Type</p>
              <p className="text-foreground capitalize">{app.job_type}</p>
            </div>
          )}
          {app.ai_match_score != null && (
            <div>
              <p className="text-xs text-muted-foreground mb-0.5">AI Match Score</p>
              <p className="text-primary font-semibold">{app.ai_match_score}%</p>
            </div>
          )}
        </div>

        {/* AI reasoning */}
        {app.ai_score_reason && (
          <div>
            <p className="text-xs text-muted-foreground mb-1">AI Reasoning</p>
            <p className="text-sm text-foreground/80 bg-muted/40 rounded-lg px-3 py-2">
              {app.ai_score_reason}
            </p>
          </div>
        )}
      </motion.div>
    </motion.div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

type DashUser = { first_name: string; last_name: string; email: string };

const AppliedJobs = () => {
  const [apps,     setApps]     = useState<PortalApplication[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState("");
  const [search,   setSearch]   = useState("");
  const [source,   setSource]   = useState<"all" | "Portal" | "Match">("all");
  const [status,   setStatus]   = useState<"all" | "pending" | "reviewed" | "shortlisted" | "rejected">("all");
  const [selected, setSelected] = useState<PortalApplication | null>(null);
  const [user,     setUser]     = useState<DashUser | null>(null);

  useEffect(() => {
    getAllApplications()
      .then(setApps)
      .catch(() => setError("Could not load applications."))
      .finally(() => setLoading(false));
    getMe().then(setUser).catch(() => {});
  }, []);

  const filtered = apps.filter((a) => {
    if (source !== "all" && a.source !== source) return false;
    if (status !== "all" && a.status !== status) return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        a.title.toLowerCase().includes(q) ||
        a.company.toLowerCase().includes(q) ||
        (a.location ?? "").toLowerCase().includes(q)
      );
    }
    return true;
  });

  const totalCount       = apps.length;
  const shortlistedCount = apps.filter((a) => a.status === "shortlisted").length;
  const pendingCount     = apps.filter((a) => a.status === "pending").length;

  if (loading) {
    return (
      <div className="min-h-screen">
        <AnimatedBackground />
        <Navbar currentStep={2} user={user} onLogout={logout} showAppNav />
        <div className="flex items-center justify-center pt-48 sm:pt-40">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <AnimatedBackground />
      <Navbar currentStep={2} user={user} onLogout={logout} showAppNav />

      <main className="pt-[120px] sm:pt-[80px] lg:pt-[88px] pb-12 px-4 sm:px-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        transition={{ duration: 0.35 }}
        className="w-full max-w-5xl mx-auto"
      >
      <h2 className="text-2xl font-bold text-gradient mb-2">My Applications</h2>
      <p className="text-muted-foreground text-sm mb-6">
        All portal applications and AI-matched jobs in one place.
      </p>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        {[
          { label: "Total",       count: totalCount,       cls: "border-border bg-muted/40",       text: "text-foreground" },
          { label: "Shortlisted", count: shortlistedCount, cls: "border-emerald-200 bg-emerald-50", text: "text-emerald-700" },
          { label: "Pending",     count: pendingCount,     cls: "border-amber-200 bg-amber-50",    text: "text-amber-700" },
        ].map(({ label, count, cls, text }) => (
          <div key={label} className={`glass-card p-4 border ${cls} text-center`}>
            <p className={`text-2xl font-bold ${text}`}>{count}</p>
            <p className="text-xs text-muted-foreground mt-1">{label}</p>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5">
        <div className="relative flex-1 min-w-[180px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search title, company, location…"
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-input border border-border text-sm
                       text-foreground placeholder:text-muted-foreground focus:outline-none
                       focus:ring-2 focus:ring-primary/50 transition"
          />
        </div>

        <div className="relative">
          <select
            value={source}
            onChange={(e) => setSource(e.target.value as typeof source)}
            className="appearance-none pl-3 pr-8 py-2 rounded-lg bg-input border border-border
                       text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition"
          >
            <option value="all">All Sources</option>
            <option value="Portal">Portal</option>
            <option value="Match">AI Match</option>
          </select>
          <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
        </div>

        <div className="relative">
          <select
            value={status}
            onChange={(e) => setStatus(e.target.value as typeof status)}
            className="appearance-none pl-3 pr-8 py-2 rounded-lg bg-input border border-border
                       text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition"
          >
            <option value="all">All Statuses</option>
            <option value="pending">Pending</option>
            <option value="reviewed">Reviewed</option>
            <option value="shortlisted">Shortlisted</option>
            <option value="rejected">Rejected</option>
          </select>
          <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
        </div>
      </div>

      {/* Error */}
      {error && <p className="text-red-400 text-sm text-center py-8">{error}</p>}

      {/* Empty state */}
      {!error && filtered.length === 0 && (
        <div className="glass-card p-12 text-center">
          <Briefcase className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
          <p className="text-muted-foreground text-sm">
            {apps.length === 0
              ? "No applications yet. Browse jobs on the dashboard to get started."
              : "No results match your filters."}
          </p>
        </div>
      )}

      {/* Applications list */}
      <div className="space-y-2">
        <AnimatePresence initial={false}>
          {filtered.map((app, i) => (
            <motion.div
              key={app.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ delay: i < 20 ? i * 0.02 : 0 }}
              onClick={() => setSelected(app)}
              className="glass-card p-4 flex items-center gap-4 cursor-pointer
                         hover:ring-1 hover:ring-primary/40 transition-all duration-200"
            >
              {/* source dot */}
              <div className={`w-2 h-2 rounded-full shrink-0 ${
                app.source === "Match" ? "bg-primary/60" : "bg-primary"
              }`} />

              {/* main info */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-foreground truncate">{app.title}</p>
                <p className="text-xs text-muted-foreground truncate">
                  {app.company}{app.location ? ` · ${app.location}` : ""}
                </p>
              </div>

              {/* source + status + date */}
              <div className="flex flex-col items-end gap-1 shrink-0">
                <div className="flex items-center gap-1.5">
                  <SourceBadge source={app.source} />
                  <StatusBadge status={app.status} />
                </div>
                <p className="text-xs text-muted-foreground">{fmtDate(app.applied_at)}</p>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Detail drawer */}
      <AnimatePresence>
        {selected && (
          <AppDrawer
            app={selected}
            onClose={() => setSelected(null)}
          />
        )}
      </AnimatePresence>
    </motion.div>
      </main>
    </div>
  );
};

export default AppliedJobs;
