import { useEffect, useState, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Briefcase, MapPin, ExternalLink, Loader2, Search,
  CheckCircle, Bot, ChevronDown, ChevronUp, ArrowDownUp,
} from "lucide-react";
import GlowButton from "./GlowButton";

const API = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

interface Job {
  id:              string;
  title:           string;
  location:        string;
  posted_on:       string;
  apply_url:       string;
  bullet_fields:   string[];
  company:         string;
  company_key:     string;
  match_score:     number;
  has_description: boolean;
}

interface Props {
  companyKey:  string;
  companyName: string;
  accentColor: string;
}

const LIMIT = 20;

export default function JobListingsPanel({ companyKey, companyName }: Props) {
  const [jobs,        setJobs]        = useState<Job[]>([]);
  const [total,       setTotal]       = useState(0);
  const [offset,      setOffset]      = useState(0);
  const [search,      setSearch]      = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState<string | null>(null);
  const [applied,     setApplied]     = useState<Set<string>>(new Set());
  const [applying,    setApplying]    = useState<Set<string>>(new Set());
  const [aiApplying,  setAiApplying]  = useState(false);
  const [aiDone,      setAiDone]      = useState(false);
  const [sortByMatch, setSortByMatch] = useState(false);

  // Description state: jobId → text (loading | "" | actual text)
  const [expanded,    setExpanded]    = useState<Set<string>>(new Set());
  const [descLoading, setDescLoading] = useState<Set<string>>(new Set());
  const [descCache,   setDescCache]   = useState<Record<string, string>>({});

  const fetchJobs = useCallback(async (q: string, off: number) => {
    setLoading(true);
    setError(null);
    try {
      const token = sessionStorage.getItem("auth_token");
      const params = new URLSearchParams({
        search: q,
        limit:  String(LIMIT),
        offset: String(off),
      });
      const res = await fetch(`${API}/api/listings/${companyKey}?${params}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail ?? "Failed to load jobs");
      }
      const data = await res.json();
      setJobs(data.jobs ?? []);
      setTotal(data.total ?? 0);
    } catch (err: any) {
      setError(err.message ?? "Something went wrong");
    } finally {
      setLoading(false);
    }
  }, [companyKey]);

  useEffect(() => {
    fetchJobs(search, offset);
  }, [fetchJobs, search, offset]);

  const handleSearch = () => {
    setOffset(0);
    setSearch(searchInput);
  };

  // ── Apply helpers ──────────────────────────────────────────────────────────

  const applyJob = async (job: Job) => {
    if (applied.has(job.id) || applying.has(job.id)) return;
    setApplying(prev => new Set(prev).add(job.id));
    try {
      const token = sessionStorage.getItem("auth_token");
      await fetch(`${API}/api/listings/apply`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          job_id:      job.id,
          title:       job.title,
          company:     job.company,
          company_key: job.company_key,
          location:    job.location,
          apply_url:   job.apply_url,
          match_score: job.match_score,
        }),
      });
      setApplied(prev => new Set(prev).add(job.id));
    } catch {
      // silently fail — user can retry
    } finally {
      setApplying(prev => { const s = new Set(prev); s.delete(job.id); return s; });
    }
  };

  const handleAiApply = async () => {
    const matched = jobs.filter(j => j.match_score >= 80 && !applied.has(j.id));
    if (!matched.length) return;
    setAiApplying(true);
    for (const job of matched) await applyJob(job);
    setAiApplying(false);
    setAiDone(true);
    setTimeout(() => setAiDone(false), 3000);
  };

  // ── Description helpers ────────────────────────────────────────────────────

  const toggleDescription = async (job: Job) => {
    const id = job.id;

    // Collapse if already open
    if (expanded.has(id)) {
      setExpanded(prev => { const s = new Set(prev); s.delete(id); return s; });
      return;
    }

    setExpanded(prev => new Set(prev).add(id));

    // Already cached
    if (id in descCache) return;

    // Fetch
    setDescLoading(prev => new Set(prev).add(id));
    try {
      const token = sessionStorage.getItem("auth_token");
      const res = await fetch(`${API}/api/listings/ey/${id}/description`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await res.json().catch(() => ({}));
      setDescCache(prev => ({ ...prev, [id]: data.description ?? "" }));
    } catch {
      setDescCache(prev => ({ ...prev, [id]: "" }));
    } finally {
      setDescLoading(prev => { const s = new Set(prev); s.delete(id); return s; });
    }
  };

  // ── Match badge colour ─────────────────────────────────────────────────────

  const matchColor = (score: number) => {
    if (score >= 80) return "text-green-400 border-green-500/40 bg-green-500/10";
    if (score >= 55) return "text-yellow-400 border-yellow-500/40 bg-yellow-500/10";
    return "text-red-400 border-red-500/40 bg-red-500/10";
  };

  const aiEligible  = jobs.filter(j => j.match_score >= 80 && !applied.has(j.id)).length;
  const displayJobs = sortByMatch
    ? [...jobs].sort((a, b) => b.match_score - a.match_score)
    : jobs;

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -16 }}
      transition={{ duration: 0.3 }}
      className="mt-4 space-y-4"
    >
      {/* Header row */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        {/* Search */}
        <div className="flex gap-2 flex-1">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
            <input
              value={searchInput}
              onChange={e => setSearchInput(e.target.value)}
              onKeyDown={e => e.key === "Enter" && handleSearch()}
              placeholder={`Search ${companyName} jobs…`}
              className="w-full pl-9 pr-4 py-2 rounded-lg bg-input border border-border text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
            />
          </div>
          <button
            onClick={handleSearch}
            className="px-4 py-2 rounded-lg bg-muted text-sm text-foreground border border-border hover:bg-muted/80 transition"
          >
            Search
          </button>
          <button
            onClick={() => setSortByMatch(prev => !prev)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border transition whitespace-nowrap
              ${sortByMatch
                ? "bg-primary/20 border-primary/40 text-primary"
                : "bg-muted border-border text-muted-foreground hover:text-foreground"
              }`}
            title="Sort by match score"
          >
            <ArrowDownUp className="w-3.5 h-3.5" />
            {sortByMatch ? "Sorted" : "Sort by Match"}
          </button>
        </div>

        {/* Apply with AI */}
        <GlowButton
          variant="primary"
          onClick={handleAiApply}
          disabled={aiApplying || aiEligible === 0}
          className="text-sm py-2 px-4 whitespace-nowrap"
        >
          {aiApplying ? (
            <span className="flex items-center gap-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Applying {aiEligible} jobs…
            </span>
          ) : aiDone ? (
            <span className="flex items-center gap-2">
              <CheckCircle className="w-3.5 h-3.5 text-green-400" />
              Done!
            </span>
          ) : (
            <span className="flex items-center gap-2">
              <Bot className="w-3.5 h-3.5" />
              Apply with AI
              {aiEligible > 0 && (
                <span className="ml-1 px-1.5 py-0.5 rounded-full bg-white/20 text-xs font-bold">
                  {aiEligible}
                </span>
              )}
            </span>
          )}
        </GlowButton>
      </div>

      <p className="text-xs text-muted-foreground">
        Apply with AI applies all jobs with{" "}
        <span className="text-green-400 font-semibold">≥ 80% match</span> to your profile automatically.
      </p>

      {/* Loading */}
      {loading && (
        <div className="flex items-center justify-center py-16">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
        </div>
      )}

      {/* Error */}
      {!loading && error && (
        <div className="glass-card p-6 text-center">
          <p className="text-red-400 text-sm">{error}</p>
          <button
            onClick={() => fetchJobs(search, offset)}
            className="mt-3 text-xs text-muted-foreground hover:text-foreground underline"
          >
            Retry
          </button>
        </div>
      )}

      {/* Job cards */}
      {!loading && !error && (
        <>
          {jobs.length === 0 ? (
            <div className="glass-card p-10 text-center text-muted-foreground text-sm">
              No jobs found{search ? ` for "${search}"` : ""}. Jobs are synced daily — check back soon.
            </div>
          ) : (
            <div className="space-y-3">
              <AnimatePresence>
                {displayJobs.map((job, i) => (
                  <motion.div
                    key={job.id}
                    initial={{ opacity: 0, y: 12 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.03 }}
                    className="glass-card overflow-hidden"
                  >
                    {/* Main row */}
                    <div className="p-4 flex flex-col sm:flex-row sm:items-center gap-3">
                      {/* Job info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start gap-2 flex-wrap">
                          <h4 className="text-sm font-semibold text-foreground leading-snug">
                            {job.title}
                          </h4>
                          <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${matchColor(job.match_score)}`}>
                            {job.match_score}% match
                          </span>
                        </div>

                        <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5">
                          {job.location && (
                            <span className="flex items-center gap-1 text-xs text-muted-foreground">
                              <MapPin className="w-3 h-3" />
                              {job.location}
                            </span>
                          )}
                          {job.bullet_fields.slice(0, 2).map((b, bi) => (
                            <span key={bi} className="flex items-center gap-1 text-xs text-muted-foreground">
                              <Briefcase className="w-3 h-3" />
                              {b}
                            </span>
                          ))}
                        </div>
                      </div>

                      {/* Action buttons */}
                      <div className="flex items-center gap-2 shrink-0">
                        {/* Expand description */}
                        <button
                          onClick={() => toggleDescription(job)}
                          className="p-2 rounded-lg bg-muted border border-border text-muted-foreground hover:text-foreground hover:bg-muted/80 transition"
                          title="View job description"
                        >
                          {expanded.has(job.id)
                            ? <ChevronUp className="w-4 h-4" />
                            : <ChevronDown className="w-4 h-4" />
                          }
                        </button>

                        {/* Open on EY site */}
                        <a
                          href={job.apply_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="p-2 rounded-lg bg-muted border border-border text-muted-foreground hover:text-foreground hover:bg-muted/80 transition"
                          title="View on EY website"
                        >
                          <ExternalLink className="w-4 h-4" />
                        </a>

                        {/* Apply (record) */}
                        <button
                          onClick={() => applyJob(job)}
                          disabled={applied.has(job.id) || applying.has(job.id)}
                          className={`px-4 py-1.5 rounded-lg text-xs font-semibold transition-all duration-200
                            ${applied.has(job.id)
                              ? "bg-green-500/20 border border-green-500/40 text-green-400 cursor-default"
                              : applying.has(job.id)
                              ? "bg-muted border border-border text-muted-foreground cursor-wait"
                              : "bg-primary/20 border border-primary/40 text-primary hover:bg-primary/30"
                            }`}
                        >
                          {applying.has(job.id) ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : applied.has(job.id) ? (
                            <span className="flex items-center gap-1">
                              <CheckCircle className="w-3.5 h-3.5" /> Applied
                            </span>
                          ) : (
                            "Apply"
                          )}
                        </button>
                      </div>
                    </div>

                    {/* Description panel */}
                    <AnimatePresence>
                      {expanded.has(job.id) && (
                        <motion.div
                          initial={{ height: 0, opacity: 0 }}
                          animate={{ height: "auto", opacity: 1 }}
                          exit={{ height: 0, opacity: 0 }}
                          transition={{ duration: 0.25 }}
                          className="overflow-hidden border-t border-border"
                        >
                          <div className="p-4 bg-muted/30">
                            {descLoading.has(job.id) ? (
                              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                Loading description…
                              </div>
                            ) : descCache[job.id] ? (
                              <pre className="text-xs text-foreground/80 whitespace-pre-wrap font-sans leading-relaxed max-h-72 overflow-y-auto">
                                {descCache[job.id]}
                              </pre>
                            ) : (
                              <p className="text-xs text-muted-foreground italic">
                                No description available. View the full listing on the EY website.
                              </p>
                            )}
                          </div>
                        </motion.div>
                      )}
                    </AnimatePresence>
                  </motion.div>
                ))}
              </AnimatePresence>
            </div>
          )}

          {/* Pagination */}
          {total > LIMIT && (
            <div className="flex items-center justify-center gap-3 pt-2">
              <button
                disabled={offset === 0}
                onClick={() => setOffset(Math.max(0, offset - LIMIT))}
                className="px-4 py-1.5 text-xs rounded-lg bg-muted border border-border text-muted-foreground hover:text-foreground disabled:opacity-40 transition"
              >
                Previous
              </button>
              <span className="text-xs text-muted-foreground">
                {offset + 1}–{Math.min(offset + LIMIT, total)} of {total}
              </span>
              <button
                disabled={offset + LIMIT >= total}
                onClick={() => setOffset(offset + LIMIT)}
                className="px-4 py-1.5 text-xs rounded-lg bg-muted border border-border text-muted-foreground hover:text-foreground disabled:opacity-40 transition"
              >
                Next
              </button>
            </div>
          )}
        </>
      )}
    </motion.div>
  );
}
