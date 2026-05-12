import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Globe, Search, MapPin, Briefcase, Clock, DollarSign,
  CheckCircle, Loader2, ChevronDown, ChevronUp, X, Filter, Building2, Sparkles,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { getToken } from "@/lib/auth";

const API: string = import.meta.env.VITE_API_URL ?? "";

interface Job {
  id:              string;
  company_name:    string;
  title:           string;
  description:     string;
  skills:          string[];
  location:        string;
  work_mode:       string;
  job_type:        string;
  experience_min:  number;
  experience_max:  number;
  salary_min:      number | null;
  salary_max:      number | null;
  salary_currency: string;
  openings:        number;
  created_at:      string;
  match_score:     number;
  applied:         boolean;
}

const CURRENCIES = ["", "INR", "USD", "EUR", "GBP", "AED", "SGD", "CAD", "AUD"];
const WORK_MODES = [
  { val: "",       label: "Any mode" },
  { val: "onsite", label: "On-site" },
  { val: "remote", label: "Remote" },
  { val: "hybrid", label: "Hybrid" },
];
const JOB_TYPES = [
  { val: "",           label: "Any type" },
  { val: "full-time",  label: "Full-time" },
  { val: "part-time",  label: "Part-time" },
  { val: "contract",   label: "Contract" },
  { val: "internship", label: "Internship" },
  { val: "freelance",  label: "Freelance" },
];
const DATE_OPTS = [
  { val: 0,  label: "Any time" },
  { val: 1,  label: "Last 24 h" },
  { val: 7,  label: "Last 7 days" },
  { val: 30, label: "Last 30 days" },
];
const SORT_OPTS = [
  { val: "recent",       label: "Most recent" },
  { val: "match",        label: "Best match" },
  { val: "salary_high",  label: "Salary: high → low" },
  { val: "salary_low",   label: "Salary: low → high" },
];
const APPLIED_OPTS = [
  { val: "",            label: "All jobs" },
  { val: "not_applied", label: "Not applied" },
  { val: "applied",     label: "Applied" },
];

const cls = "w-full px-3 py-2 rounded-lg bg-input border border-border text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition";
const LIMIT = 10;

export default function WorldWideJobs({ profileReady = true }: { profileReady?: boolean }) {
  const navigate = useNavigate();
  const [jobs,       setJobs]       = useState<Job[]>([]);
  const [total,      setTotal]      = useState(0);
  const [loading,    setLoading]    = useState(true);
  const [applying,   setApplying]   = useState<string | null>(null);
  const [expanded,   setExpanded]   = useState<string | null>(null);
  const [showFilter, setShowFilter] = useState(false);

  // ── Filters ──────────────────────────────────────────────────────────────────
  const [search,        setSearch]        = useState("");
  const [searchInput,   setSearchInput]   = useState("");
  const [location,      setLocation]      = useState("");
  const [workMode,      setWorkMode]      = useState("");
  const [jobType,       setJobType]       = useState("");
  const [currency,      setCurrency]      = useState("");
  const [company,       setCompany]       = useState("");
  const [expMin,        setExpMin]        = useState("");
  const [expMax,        setExpMax]        = useState("");
  const [salMin,        setSalMin]        = useState("");
  const [salMax,        setSalMax]        = useState("");
  const [daysAgo,       setDaysAgo]       = useState(0);
  const [sortBy,        setSortBy]        = useState("recent");
  const [appliedFilter, setAppliedFilter] = useState("");
  const [offset,        setOffset]        = useState(0);

  const buildParams = (off: number) => {
    const p = new URLSearchParams();
    if (search)        p.set("search",          search);
    if (location)      p.set("location",        location);
    if (workMode)      p.set("work_mode",       workMode);
    if (jobType)       p.set("job_type",        jobType);
    if (currency)      p.set("salary_currency", currency);
    if (company)       p.set("company",         company);
    if (expMin)        p.set("exp_min",         expMin);
    if (expMax)        p.set("exp_max",         expMax);
    if (salMin)        p.set("sal_min",         salMin);
    if (salMax)        p.set("sal_max",         salMax);
    if (daysAgo)       p.set("days_ago",        String(daysAgo));
    if (sortBy)        p.set("sort_by",         sortBy);
    if (appliedFilter) p.set("applied_filter",  appliedFilter);
    p.set("limit",  String(LIMIT));
    p.set("offset", String(off));
    return p;
  };

  const load = async (reset = true) => {
    const token = getToken();
    if (!token) return;
    setLoading(true);
    const off = reset ? 0 : offset;
    try {
      const res = await fetch(`${API}/api/portal/jobs?${buildParams(off)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const data = await res.json();
      if (reset) { setJobs(data.jobs ?? []); setOffset(0); }
      else        setJobs(prev => [...prev, ...(data.jobs ?? [])]);
      setTotal(data.total ?? 0);
    } finally { setLoading(false); }
  };

  const loadMore = async () => {
    const token = getToken();
    if (!token) return;
    const next = offset + LIMIT;
    setOffset(next);
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/portal/jobs?${buildParams(next)}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) return;
      const data = await res.json();
      setJobs(prev => [...prev, ...(data.jobs ?? [])]);
    } finally { setLoading(false); }
  };

  useEffect(() => { load(true); }, [
    search, location, workMode, jobType, currency, company,
    expMin, expMax, salMin, salMax, daysAgo, sortBy, appliedFilter,
  ]);

  const applyToJob = async (jobId: string) => {
    if (!profileReady) {
      navigate("/profile", { state: { applyBlocked: true } });
      return;
    }
    const token = getToken();
    if (!token) return;
    setApplying(jobId);
    try {
      const res = await fetch(`${API}/api/portal/jobs/${jobId}/apply`, {
        method:  "POST",
        headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      });
      if (res.ok || res.status === 409) {
        setJobs(prev => prev.map(j => j.id === jobId ? { ...j, applied: true } : j));
      } else {
        const d = await res.json().catch(() => ({}));
        alert((d as any).detail ?? "Failed to apply.");
      }
    } finally { setApplying(null); }
  };

  const hasFilters = !!(
    search || location || workMode || jobType || currency || company ||
    expMin || expMax || salMin || salMax || daysAgo || appliedFilter
  );

  const clearFilters = () => {
    setSearch(""); setSearchInput(""); setLocation(""); setWorkMode(""); setJobType("");
    setCurrency(""); setCompany(""); setExpMin(""); setExpMax(""); setSalMin(""); setSalMax("");
    setDaysAgo(0); setAppliedFilter("");
  };

  const fmtSalary = (min: number | null, max: number | null, cur: string) => {
    if (!min && !max) return null;
    const fmt = (n: number) => n >= 100000 ? `${(n / 100000).toFixed(n % 100000 ? 1 : 0)}L` : n.toLocaleString();
    if (min && max) return `${cur} ${fmt(min)} – ${fmt(max)}`;
    if (min) return `${cur} ${fmt(min)}+`;
    return `Up to ${cur} ${fmt(max!)}`;
  };

  const scoreColor = (s: number) =>
    s >= 70 ? "text-blue-700 bg-blue-50 border-blue-200"
    : s >= 45 ? "text-amber-700 bg-amber-50 border-amber-200"
    : "text-slate-500 bg-slate-100 border-slate-200";

  return (
    <section className="w-full max-w-5xl mx-auto px-4 py-10">

      {/* Section header */}
      <div className="flex items-center gap-3 mb-5">
        <div className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center">
          <Globe className="w-5 h-5 text-white" />
        </div>
        <div>
          <h2 className="text-xl font-bold text-foreground">World Wide Jobs</h2>
          <p className="text-xs text-muted-foreground">Explore opportunities from all recruiters on the platform</p>
        </div>
        <span className="ml-auto text-xs text-muted-foreground">{total} job{total !== 1 ? "s" : ""} found</span>
      </div>

      {/* Top bar: search + sort + filter toggle */}
      <div className="flex gap-2 mb-3 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter") setSearch(searchInput); }}
            onBlur={() => setSearch(searchInput)}
            placeholder="Search by title, skill, company…"
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-input border border-border text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>

        {/* Sort by */}
        <select
          value={sortBy}
          onChange={e => setSortBy(e.target.value)}
          className="px-3 py-2 rounded-lg bg-input border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
        >
          {SORT_OPTS.map(o => <option key={o.val} value={o.val}>{o.label}</option>)}
        </select>

        {/* Filter toggle */}
        <button
          onClick={() => setShowFilter(!showFilter)}
          className={`flex items-center gap-1.5 px-3 py-2 rounded-lg border text-sm font-medium transition
            ${showFilter || hasFilters
              ? "bg-primary/10 border-primary/40 text-primary"
              : "bg-muted border-border text-muted-foreground hover:text-foreground"
            }`}
        >
          <Filter className="w-4 h-4" />
          Filters
          {hasFilters && <span className="w-2 h-2 rounded-full bg-primary shrink-0" />}
        </button>

        {hasFilters && (
          <button
            onClick={clearFilters}
            className="flex items-center gap-1 px-3 py-2 rounded-lg bg-muted border border-border text-xs text-muted-foreground hover:text-foreground transition"
          >
            <X className="w-3.5 h-3.5" /> Clear
          </button>
        )}
      </div>

      {/* Applied filter quick tabs */}
      <div className="flex gap-2 mb-3 flex-wrap">
        {APPLIED_OPTS.map(o => (
          <button
            key={o.val}
            onClick={() => setAppliedFilter(o.val)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition
              ${appliedFilter === o.val
                ? "bg-primary/15 border-primary/50 text-primary"
                : "bg-muted border-border text-muted-foreground hover:text-foreground"
              }`}
          >
            {o.label}
          </button>
        ))}

        {/* Date posted quick tabs */}
        {DATE_OPTS.map(o => (
          <button
            key={o.val}
            onClick={() => setDaysAgo(o.val)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition
              ${daysAgo === o.val
                ? "bg-primary/10 border-primary/40 text-primary"
                : "bg-muted border-border text-muted-foreground hover:text-foreground"
              }`}
          >
            {o.label}
          </button>
        ))}
      </div>

      {/* Expanded filter panel */}
      <AnimatePresence>
        {showFilter && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <div className="glass-card p-4 mb-4 grid grid-cols-2 sm:grid-cols-3 gap-3">
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Company</label>
                <input value={company} onChange={e => setCompany(e.target.value)}
                  placeholder="e.g. Acme Corp" className={cls} />
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Location</label>
                <input value={location} onChange={e => setLocation(e.target.value)}
                  placeholder="e.g. Mumbai" className={cls} />
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Work Mode</label>
                <select value={workMode} onChange={e => setWorkMode(e.target.value)} className={cls}>
                  {WORK_MODES.map(m => <option key={m.val} value={m.val}>{m.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Job Type</label>
                <select value={jobType} onChange={e => setJobType(e.target.value)} className={cls}>
                  {JOB_TYPES.map(t => <option key={t.val} value={t.val}>{t.label}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Min Exp (yrs)</label>
                <input type="number" min={0} value={expMin} onChange={e => setExpMin(e.target.value)}
                  placeholder="0" className={cls} />
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Max Exp (yrs)</label>
                <input type="number" min={0} value={expMax} onChange={e => setExpMax(e.target.value)}
                  placeholder="Any" className={cls} />
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Currency</label>
                <select value={currency} onChange={e => setCurrency(e.target.value)} className={cls}>
                  {CURRENCIES.map(c => <option key={c} value={c}>{c || "Any"}</option>)}
                </select>
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Min Salary</label>
                <input type="number" min={0} value={salMin} onChange={e => setSalMin(e.target.value)}
                  placeholder="0" className={cls} />
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Max Salary</label>
                <input type="number" min={0} value={salMax} onChange={e => setSalMax(e.target.value)}
                  placeholder="Any" className={cls} />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Job list */}
      {loading && jobs.length === 0 ? (
        <div className="flex justify-center py-16">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
        </div>
      ) : jobs.length === 0 ? (
        <div className="glass-card p-10 text-center text-muted-foreground text-sm">
          <Globe className="w-10 h-10 mx-auto mb-3 opacity-30" />
          No jobs found matching your criteria. Try adjusting the filters.
        </div>
      ) : (
        <div className="space-y-3">
          <AnimatePresence>
            {jobs.map((job, i) => {
              const salary     = fmtSalary(job.salary_min, job.salary_max, job.salary_currency);
              const isExpanded = expanded === job.id;

              return (
                <motion.div
                  key={job.id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: Math.min(i, 5) * 0.04 }}
                  className="glass-card overflow-hidden"
                >
                  <div className="p-4">
                    <div className="flex items-start gap-4">
                      <div className="flex-1 min-w-0">

                        {/* Title + badges */}
                        <div className="flex items-center gap-2 flex-wrap mb-0.5">
                          <h3 className="font-semibold text-foreground">{job.title}</h3>
                          {job.match_score === 0 ? (
                            <button
                              onClick={e => { e.stopPropagation(); navigate("/profile"); }}
                              className="flex items-center gap-1 text-xs font-medium px-2.5 py-0.5 rounded-full border border-violet-300 bg-violet-50 text-violet-700 hover:bg-violet-100 transition-colors"
                            >
                              <Sparkles className="w-3 h-3" />
                              Complete profile to see your match
                            </button>
                          ) : (
                            <span className={`text-xs font-bold px-2 py-0.5 rounded-full border ${scoreColor(job.match_score)}`}>
                              {job.match_score}% match
                            </span>
                          )}
                          {job.applied && (
                            <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full bg-green-500/10 border border-green-500/30 text-emerald-700 font-medium">
                              <CheckCircle className="w-3 h-3" /> Applied
                            </span>
                          )}
                        </div>

                        {/* Company */}
                        <p className="flex items-center gap-1 text-sm text-muted-foreground mb-2">
                          <Building2 className="w-3.5 h-3.5 shrink-0" />
                          {job.company_name}
                        </p>

                        {/* Meta row */}
                        <div className="flex flex-wrap gap-x-4 gap-y-1">
                          {job.location && (
                            <span className="flex items-center gap-1 text-xs text-muted-foreground">
                              <MapPin className="w-3 h-3" />{job.location}
                            </span>
                          )}
                          <span className="text-xs text-muted-foreground capitalize">{job.work_mode}</span>
                          <span className="text-xs text-muted-foreground capitalize">{job.job_type}</span>
                          <span className="flex items-center gap-1 text-xs text-muted-foreground">
                            <Briefcase className="w-3 h-3" />
                            {job.experience_min}–{job.experience_max} yrs
                          </span>
                          {salary && (
                            <span className="flex items-center gap-1 text-xs text-muted-foreground">
                              <DollarSign className="w-3 h-3" />{salary}
                            </span>
                          )}
                          <span className="flex items-center gap-1 text-xs text-muted-foreground">
                            <Clock className="w-3 h-3" />
                            {new Date(job.created_at).toLocaleDateString("en-IN", {
                              day: "numeric", month: "short", year: "numeric",
                            })}
                          </span>
                        </div>

                        {/* Skills */}
                        {job.skills.length > 0 && (
                          <div className="flex flex-wrap gap-1 mt-2">
                            {job.skills.slice(0, 6).map(s => (
                              <span key={s} className="text-xs px-2 py-0.5 rounded-full bg-muted border border-border text-muted-foreground">
                                {s}
                              </span>
                            ))}
                            {job.skills.length > 6 && (
                              <span className="text-xs text-muted-foreground self-center">+{job.skills.length - 6}</span>
                            )}
                          </div>
                        )}
                      </div>

                      {/* Actions */}
                      <div className="flex flex-col items-end gap-2 shrink-0">
                        {job.applied ? (
                          <span className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-emerald-50 border border-emerald-200 text-emerald-700">
                            <CheckCircle className="w-3.5 h-3.5" /> Applied
                          </span>
                        ) : (
                          <button
                            onClick={() => applyToJob(job.id)}
                            disabled={applying === job.id}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition"
                          >
                            {applying === job.id
                              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              : "Quick Apply"
                            }
                          </button>
                        )}
                        <button
                          onClick={() => setExpanded(isExpanded ? null : job.id)}
                          className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition"
                        >
                          {isExpanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
                          {isExpanded ? "Less" : "Details"}
                        </button>
                      </div>
                    </div>
                  </div>

                  {/* Expanded description */}
                  <AnimatePresence>
                    {isExpanded && (
                      <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        className="overflow-hidden border-t border-border"
                      >
                        <div className="p-4 bg-muted/20">
                          <p className="text-xs text-muted-foreground whitespace-pre-line leading-relaxed">
                            {job.description}
                          </p>
                          {job.openings > 1 && (
                            <p className="text-xs text-primary mt-2 font-medium">{job.openings} openings</p>
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </motion.div>
              );
            })}
          </AnimatePresence>

          {/* Load more */}
          {jobs.length < total && (
            <div className="flex justify-center pt-2">
              <button
                onClick={loadMore}
                disabled={loading}
                className="flex items-center gap-2 px-5 py-2 rounded-lg bg-muted border border-border text-sm text-muted-foreground hover:text-foreground transition disabled:opacity-50"
              >
                {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Load more"}
              </button>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
