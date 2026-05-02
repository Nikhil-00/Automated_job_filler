import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Star, X, ExternalLink, Loader2, Search,
  Briefcase, MapPin, IndianRupee, BadgeCheck,
} from "lucide-react";
import { getShortlistedJobs, ShortlistedJob } from "@/lib/mockApi";

// ── Helpers ───────────────────────────────────────────────────────────────────

function fmtDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
  });
}

function fmtSalary(min: number | null, max: number | null, currency: string | null) {
  if (!min && !max) return null;
  const cur = currency ?? "INR";
  const fmt = (n: number) =>
    cur === "INR"
      ? `₹${(n / 100000).toFixed(1)}L`
      : `${cur} ${(n / 1000).toFixed(0)}K`;
  if (min && max) return `${fmt(min)} – ${fmt(max)}`;
  if (max) return `Up to ${fmt(max)}`;
  return `From ${fmt(min!)}`;
}

function platformLabel(platform: string | null) {
  if (!platform) return "";
  if (platform.startsWith("big4_")) return `Big4 · ${platform.replace("big4_", "").toUpperCase()}`;
  return platform.charAt(0).toUpperCase() + platform.slice(1);
}

// ── Detail Modal ──────────────────────────────────────────────────────────────

function JobModal({ job, onClose }: { job: ShortlistedJob; onClose: () => void }) {
  const salary = fmtSalary(job.salary_min, job.salary_max, job.salary_currency);

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
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-0.5">
              <BadgeCheck className="w-4 h-4 text-violet-400 shrink-0" />
              <span className="text-xs font-semibold text-violet-400">Shortlisted</span>
            </div>
            <h3 className="text-lg font-bold text-foreground">{job.title}</h3>
            <p className="text-sm text-muted-foreground">{job.company}</p>
          </div>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground transition shrink-0">
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tags */}
        <div className="flex flex-wrap gap-2">
          {job.source === "portal" && job.work_mode && (
            <span className="text-xs px-2.5 py-1 rounded-full border border-border bg-muted/40 text-muted-foreground">
              {job.work_mode}
            </span>
          )}
          {job.source === "portal" && job.job_type && (
            <span className="text-xs px-2.5 py-1 rounded-full border border-border bg-muted/40 text-muted-foreground">
              {job.job_type}
            </span>
          )}
          {job.source === "automation" && job.platform && (
            <span className="text-xs px-2.5 py-1 rounded-full border border-blue-500/30 bg-blue-500/10 text-blue-400">
              {platformLabel(job.platform)}
            </span>
          )}
          {job.ai_match_score != null && (
            <span className="text-xs px-2.5 py-1 rounded-full border border-green-500/30 bg-green-500/10 text-green-400">
              {job.ai_match_score}% match
            </span>
          )}
        </div>

        {/* Meta */}
        <div className="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
          {job.location && (
            <div>
              <p className="text-xs text-muted-foreground mb-0.5">Location</p>
              <p className="text-foreground flex items-center gap-1">
                <MapPin className="w-3 h-3 shrink-0" />{job.location}
              </p>
            </div>
          )}
          {salary && (
            <div>
              <p className="text-xs text-muted-foreground mb-0.5">Salary</p>
              <p className="text-foreground flex items-center gap-1">
                <IndianRupee className="w-3 h-3 shrink-0" />{salary}
              </p>
            </div>
          )}
          <div>
            <p className="text-xs text-muted-foreground mb-0.5">Applied</p>
            <p className="text-foreground">{fmtDate(job.applied_at)}</p>
          </div>
        </div>

        {/* Skills */}
        {job.skills.length > 0 && (
          <div>
            <p className="text-xs text-muted-foreground mb-1.5">Skills Required</p>
            <div className="flex flex-wrap gap-1.5">
              {job.skills.map((s) => (
                <span key={s} className="text-xs px-2 py-0.5 rounded-md bg-muted border border-border text-muted-foreground">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Action */}
        {job.job_url && (
          <button
            onClick={() => window.open(job.job_url!, "_blank")}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg
                       bg-violet-500/20 border border-violet-500/40 text-violet-400 text-sm font-medium
                       hover:bg-violet-500/30 transition"
          >
            <ExternalLink className="w-4 h-4" />
            View Original Job
          </button>
        )}
      </motion.div>
    </motion.div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

const ShortlistedJobs = () => {
  const [jobs,     setJobs]     = useState<ShortlistedJob[]>([]);
  const [loading,  setLoading]  = useState(true);
  const [error,    setError]    = useState("");
  const [search,   setSearch]   = useState("");
  const [selected, setSelected] = useState<ShortlistedJob | null>(null);

  useEffect(() => {
    getShortlistedJobs()
      .then(setJobs)
      .catch(() => setError("Could not load shortlisted jobs."))
      .finally(() => setLoading(false));
  }, []);

  const filtered = jobs.filter((j) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      j.title.toLowerCase().includes(q) ||
      j.company.toLowerCase().includes(q) ||
      (j.location ?? "").toLowerCase().includes(q)
    );
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="w-8 h-8 text-violet-400 animate-spin" />
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
      <div className="flex items-center gap-3 mb-2">
        <div className="w-9 h-9 rounded-lg bg-violet-500/15 border border-violet-500/30 flex items-center justify-center shrink-0">
          <Star className="w-4 h-4 text-violet-400" />
        </div>
        <div>
          <h2 className="text-2xl font-bold text-gradient leading-none">Shortlisted</h2>
          <p className="text-muted-foreground text-sm mt-0.5">Jobs where you've been shortlisted by a company.</p>
        </div>
      </div>

      {/* Count pill */}
      <div className="mt-4 mb-5 flex items-center gap-3">
        <div className="px-4 py-2 rounded-xl border border-violet-500/30 bg-violet-500/10 text-center">
          <p className="text-2xl font-bold text-violet-400">{jobs.length}</p>
          <p className="text-xs text-muted-foreground mt-0.5">Shortlisted</p>
        </div>
      </div>

      {/* Search */}
      <div className="relative mb-5">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search title, company, location..."
          className="w-full pl-9 pr-4 py-2 rounded-lg bg-input border border-border text-sm
                     text-foreground placeholder:text-muted-foreground focus:outline-none
                     focus:ring-2 focus:ring-violet-500/50 transition"
        />
      </div>

      {/* Error */}
      {error && <p className="text-red-400 text-sm text-center py-8">{error}</p>}

      {/* Empty state */}
      {!error && filtered.length === 0 && (
        <div className="glass-card p-12 text-center">
          <Star className="w-10 h-10 text-muted-foreground mx-auto mb-3 opacity-40" />
          <p className="text-muted-foreground text-sm">
            {jobs.length === 0
              ? "No shortlists yet. Once a company shortlists you, the job will appear here."
              : "No results match your search."}
          </p>
        </div>
      )}

      {/* Jobs list */}
      <div className="space-y-2">
        <AnimatePresence initial={false}>
          {filtered.map((job, i) => {
            const salary = fmtSalary(job.salary_min, job.salary_max, job.salary_currency);
            return (
              <motion.div
                key={job.application_id}
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ delay: i < 20 ? i * 0.03 : 0 }}
                onClick={() => setSelected(job)}
                className="glass-card p-4 flex items-center gap-4 cursor-pointer
                           hover:ring-1 hover:ring-violet-500/40 transition-all duration-200"
              >
                {/* Icon */}
                <div className="w-8 h-8 rounded-lg bg-violet-500/15 border border-violet-500/30 flex items-center justify-center shrink-0">
                  <BadgeCheck className="w-4 h-4 text-violet-400" />
                </div>

                {/* Main info */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-foreground truncate">{job.title}</p>
                  <p className="text-xs text-muted-foreground truncate flex items-center gap-1">
                    <Briefcase className="w-3 h-3 shrink-0" />
                    {job.company}
                    {job.location && <> · <MapPin className="w-3 h-3 shrink-0" />{job.location}</>}
                  </p>
                </div>

                {/* Right side */}
                <div className="flex flex-col items-end gap-1 shrink-0 text-right">
                  {salary && (
                    <span className="text-xs text-muted-foreground">{salary}</span>
                  )}
                  {job.source === "automation" && job.platform && (
                    <span className="text-xs text-blue-400">{platformLabel(job.platform)}</span>
                  )}
                  <span className="text-xs text-muted-foreground">{fmtDate(job.applied_at)}</span>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {/* Detail modal */}
      <AnimatePresence>
        {selected && (
          <JobModal job={selected} onClose={() => setSelected(null)} />
        )}
      </AnimatePresence>
    </motion.div>
  );
};

export default ShortlistedJobs;
