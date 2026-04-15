import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Briefcase, ExternalLink, Trash2, X, Search,
  ChevronDown, Loader2, CheckCircle, Clock, SkipForward,
} from "lucide-react";
import { getAppliedJobs, deleteAppliedJob, AppliedJob } from "@/lib/mockApi";

// ── Status helpers ────────────────────────────────────────────────────────────

const STATUS_CONFIG = {
  applied: {
    label: "Applied",
    icon:  CheckCircle,
    cls:   "bg-green-500/15 text-green-400 border-green-500/30",
  },
  skipped: {
    label: "Skipped",
    icon:  SkipForward,
    cls:   "bg-yellow-500/15 text-yellow-400 border-yellow-500/30",
  },
  already_applied: {
    label: "Already Applied",
    icon:  Clock,
    cls:   "bg-blue-500/15 text-blue-400 border-blue-500/30",
  },
} as const;

const PLATFORM_COLOR: Record<string, string> = {
  linkedin: "text-blue-400",
  naukri:   "text-orange-400",
};

function StatusBadge({ status }: { status: AppliedJob["status"] }) {
  const cfg  = STATUS_CONFIG[status] ?? STATUS_CONFIG.skipped;
  const Icon = cfg.icon;
  return (
    <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border ${cfg.cls}`}>
      <Icon className="w-3 h-3" />
      {cfg.label}
    </span>
  );
}

function fmtDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
    hour: "2-digit", minute: "2-digit",
  });
}

// ── Detail Drawer ─────────────────────────────────────────────────────────────

function JobDrawer({ job, onClose, onDelete }: {
  job:      AppliedJob;
  onClose:  () => void;
  onDelete: (id: string) => void;
}) {
  const [deleting, setDeleting] = useState(false);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await deleteAppliedJob(job.id);
      onDelete(job.id);
      onClose();
    } catch {
      setDeleting(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-4"
      onClick={onClose}
    >
      {/* backdrop */}
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
            <h3 className="text-lg font-bold text-foreground truncate">{job.title}</h3>
            <p className="text-sm text-muted-foreground">{job.company}</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition shrink-0">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* badges */}
        <div className="flex flex-wrap gap-2">
          <StatusBadge status={job.status} />
          <span className={`text-xs font-medium capitalize ${PLATFORM_COLOR[job.platform] ?? "text-muted-foreground"}`}>
            {job.platform}
          </span>
        </div>

        {/* meta grid */}
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          <div>
            <p className="text-xs text-muted-foreground mb-0.5">Location</p>
            <p className="text-foreground">{job.location || "—"}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-0.5">Applied At</p>
            <p className="text-foreground">{fmtDate(job.applied_at)}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-0.5">Search Role</p>
            <p className="text-foreground">{job.session_role || "—"}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-0.5">Search Location</p>
            <p className="text-foreground">{job.session_location || "—"}</p>
          </div>
        </div>

        {/* reason */}
        {job.reason && (
          <div>
            <p className="text-xs text-muted-foreground mb-1">Reason</p>
            <p className="text-sm text-foreground/80 bg-muted/40 rounded-lg px-3 py-2">{job.reason}</p>
          </div>
        )}

        {/* description */}
        {job.description && (
          <div>
            <p className="text-xs text-muted-foreground mb-1">Job Description</p>
            <p className="text-sm text-foreground/70 bg-muted/40 rounded-lg px-3 py-2 whitespace-pre-wrap line-clamp-6">
              {job.description}
            </p>
          </div>
        )}

        {/* actions */}
        <div className="flex gap-3 pt-2">
          {job.url && (
            <button
              onClick={() => window.location.href = job.url}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg
                         bg-primary/20 border border-primary/40 text-primary text-sm font-medium
                         hover:bg-primary/30 transition"
            >
              <ExternalLink className="w-4 h-4" />
              View Job
            </button>
          )}
          <button
            onClick={handleDelete}
            disabled={deleting}
            className="flex items-center justify-center gap-2 px-4 py-2 rounded-lg
                       bg-red-500/10 border border-red-500/30 text-red-400 text-sm font-medium
                       hover:bg-red-500/20 transition disabled:opacity-50"
          >
            {deleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
            Delete
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

const AppliedJobs = () => {
  const [jobs,     setJobs]     = useState<AppliedJob[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState("");
  const [search,   setSearch]   = useState("");
  const [platform, setPlatform] = useState<"all" | "linkedin" | "naukri">("all");
  const [status,   setStatus]   = useState<"all" | "applied" | "skipped" | "already_applied">("all");
  const [selected, setSelected] = useState<AppliedJob | null>(null);

  useEffect(() => {
    getAppliedJobs()
      .then(setJobs)
      .catch(() => setError("Could not load applied jobs."))
      .finally(() => setLoading(false));
  }, []);

  const filtered = jobs.filter((j) => {
    if (platform !== "all" && j.platform !== platform) return false;
    if (status   !== "all" && j.status   !== status)   return false;
    if (search) {
      const q = search.toLowerCase();
      return (
        j.title.toLowerCase().includes(q) ||
        j.company.toLowerCase().includes(q) ||
        j.location.toLowerCase().includes(q)
      );
    }
    return true;
  });

  const handleDelete = (id: string) => setJobs((prev) => prev.filter((j) => j.id !== id));

  // stats
  const appliedCount  = jobs.filter((j) => j.status === "applied").length;
  const skippedCount  = jobs.filter((j) => j.status === "skipped").length;
  const alreadyCount  = jobs.filter((j) => j.status === "already_applied").length;

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 text-primary animate-spin" />
      </div>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -20 }}
      transition={{ duration: 0.35 }}
      className="w-full max-w-5xl mx-auto"
    >
      <h2 className="text-2xl font-bold text-gradient mb-2">Applied Jobs</h2>
      <p className="text-muted-foreground text-sm mb-6">Your complete automation history across all platforms.</p>

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        {[
          { label: "Applied",        count: appliedCount, cls: "border-green-500/30 bg-green-500/10",  text: "text-green-400" },
          { label: "Skipped",        count: skippedCount, cls: "border-yellow-500/30 bg-yellow-500/10", text: "text-yellow-400" },
          { label: "Already Applied",count: alreadyCount, cls: "border-blue-500/30 bg-blue-500/10",   text: "text-blue-400" },
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
            placeholder="Search title, company, location..."
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-input border border-border text-sm
                       text-foreground placeholder:text-muted-foreground focus:outline-none
                       focus:ring-2 focus:ring-primary/50 transition"
          />
        </div>

        <div className="relative">
          <select
            value={platform}
            onChange={(e) => setPlatform(e.target.value as typeof platform)}
            className="appearance-none pl-3 pr-8 py-2 rounded-lg bg-input border border-border
                       text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition"
          >
            <option value="all">All Platforms</option>
            <option value="linkedin">LinkedIn</option>
            <option value="naukri">Naukri</option>
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
            <option value="applied">Applied</option>
            <option value="skipped">Skipped</option>
            <option value="already_applied">Already Applied</option>
          </select>
          <ChevronDown className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground pointer-events-none" />
        </div>
      </div>

      {/* Error */}
      {error && (
        <p className="text-red-400 text-sm text-center py-8">{error}</p>
      )}

      {/* Empty state */}
      {!error && filtered.length === 0 && (
        <div className="glass-card p-12 text-center">
          <Briefcase className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
          <p className="text-muted-foreground text-sm">
            {jobs.length === 0
              ? "No jobs applied yet. Start an automation run to see your history here."
              : "No results match your filters."}
          </p>
        </div>
      )}

      {/* Jobs list */}
      <div className="space-y-2">
        <AnimatePresence initial={false}>
          {filtered.map((job, i) => (
            <motion.div
              key={job.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, height: 0 }}
              transition={{ delay: i < 20 ? i * 0.02 : 0 }}
              onClick={() => setSelected(job)}
              className="glass-card p-4 flex items-center gap-4 cursor-pointer
                         hover:ring-1 hover:ring-primary/40 transition-all duration-200"
            >
              {/* platform dot */}
              <div className={`w-2 h-2 rounded-full shrink-0 ${
                job.platform === "linkedin" ? "bg-blue-400" : "bg-orange-400"
              }`} />

              {/* main info */}
              <div className="flex-1 min-w-0">
                <p className="text-sm font-semibold text-foreground truncate">{job.title}</p>
                <p className="text-xs text-muted-foreground truncate">{job.company} · {job.location}</p>
              </div>

              {/* status + date */}
              <div className="flex flex-col items-end gap-1 shrink-0">
                <StatusBadge status={job.status} />
                <p className="text-xs text-muted-foreground">{fmtDate(job.applied_at)}</p>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Detail drawer */}
      <AnimatePresence>
        {selected && (
          <JobDrawer
            job={selected}
            onClose={() => setSelected(null)}
            onDelete={handleDelete}
          />
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default AppliedJobs;
