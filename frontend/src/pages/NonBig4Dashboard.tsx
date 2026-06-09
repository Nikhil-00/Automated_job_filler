import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Building2, Users, Briefcase, PlusCircle, Search, Download,
  MapPin, Clock, Loader2, LogOut, Mail, Phone,
  CheckCircle, XCircle, MessageSquare, Send, X, Bot,
  ToggleLeft, ToggleRight, Trash2, ChevronDown, Sparkles,
  Upload, Star,
} from "lucide-react";
import AgenticChatPanel from "../components/AgenticChatPanel";

const API: string = import.meta.env.VITE_API_URL ?? "";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Job {
  id:              string;
  title:           string;
  location:        string;
  work_mode:       string;
  job_type:        string;
  experience_min:  number;
  experience_max:  number;
  salary_min:      number | null;
  salary_max:      number | null;
  salary_currency: string;
  openings:        number;
  is_active:       boolean;
  created_at:      string;
  skills:          string[];
  applicant_count: number;
}

interface PortalApplicant {
  application_id:  string;
  applied_at:      string;
  status:          string;
  ai_match_score:  number | null;
  ai_score_reason: string | null;
  job_posting_id:  string;
  applied_for:     string;
  location:        string;
  user_id:         number;
  first_name:      string;
  last_name:       string;
  email:           string;
  phone:           string;
  has_cv:          boolean;
  is_match?:       boolean;
}

interface Props {
  token:       string;
  companyName: string;
  officerName: string;
  onLogout:    () => void;
}

type Tab = "candidates" | "post-job" | "my-jobs";

const cls = "w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition text-sm";

// ── Main Component ────────────────────────────────────────────────────────────

export default function NonBig4Dashboard({ token, companyName, officerName, onLogout }: Props) {
  const [tab,          setTab]          = useState<Tab>("candidates");
  const [agenticOpen,  setAgenticOpen]  = useState(false);

  const authH = { Authorization: `Bearer ${token}` };

  return (
    <div className="min-h-screen px-4 py-8">
      <div className="max-w-6xl mx-auto">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-600 to-violet-400 flex items-center justify-center">
              <Building2 className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-foreground">{companyName}</h1>
              <p className="text-xs text-muted-foreground">Welcome, {officerName}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={onLogout}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition">
              <LogOut className="w-4 h-4" /> Logout
            </button>
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex border-b border-border mb-6">
          {([
            { key: "candidates", label: "Candidates", icon: Users },
            { key: "post-job",   label: "Post a Job",  icon: PlusCircle },
            { key: "my-jobs",    label: "My Jobs",     icon: Briefcase },
          ] as { key: Tab; label: string; icon: any }[]).map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTab(key)}
              className={`flex items-center gap-1.5 px-5 py-3 text-sm font-semibold transition-colors
                ${tab === key
                  ? "text-violet-400 border-b-2 border-violet-400 bg-violet-500/5"
                  : "text-muted-foreground hover:text-foreground"
                }`}
            >
              <Icon className="w-4 h-4" />
              {label}
            </button>
          ))}
        </div>

        {tab === "candidates" && <CandidatesTab token={token} authH={authH} />}
        {tab === "post-job"   && <PostJobTab   token={token} authH={authH} onPosted={() => setTab("my-jobs")} />}
        {tab === "my-jobs"    && <MyJobsTab    token={token} authH={authH} />}
      </div>

      <AgenticChatPanel
        token={token}
        isOpen={agenticOpen}
        onClose={() => setAgenticOpen(false)}
      />

      {/* ── AI Recruiter FAB ── */}
      <AIRecruiterFAB onClick={() => setAgenticOpen(true)} />
    </div>
  );
}

// ── Floating AI Recruiter Button ──────────────────────────────────────────────

const AI_LINES = [
  { title: "Your AI hiring partner is here.", sub: "Let me scan every CV and surface your top 3 hires — instantly." },
  { title: "Stop reading resumes.", sub: "I already did. Ask me who to shortlist." },
  { title: "100 applicants? No problem.", sub: "I'll rank them by fit, skills & experience in seconds." },
];

function AIRecruiterFAB({ onClick }: { onClick: () => void }) {
  const [visible, setVisible] = useState(false);
  const [hovered, setHovered] = useState(false);
  const line = AI_LINES[0];

  useEffect(() => {
    const show = setTimeout(() => setVisible(true), 1200);
    const hide = setTimeout(() => setVisible(false), 6000);
    return () => { clearTimeout(show); clearTimeout(hide); };
  }, []);

  const isOpen = visible || hovered;

  return (
    <div className="fixed bottom-8 right-8 z-40 flex flex-col items-end gap-3">
      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: 12, scale: 0.92 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.92 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            className="bg-white border border-violet-200 shadow-xl rounded-2xl px-5 py-4 max-w-[240px]"
            style={{ boxShadow: "0 8px 32px rgba(139,92,246,0.18)" }}
          >
            <p className="text-sm font-bold text-violet-700 leading-snug">{line.title}</p>
            <p className="text-xs text-muted-foreground mt-1 leading-relaxed">{line.sub}</p>
            <button
              onClick={onClick}
              className="mt-3 w-full text-xs font-semibold py-1.5 rounded-lg
                         bg-violet-600 text-white hover:bg-violet-700 transition"
            >
              Try AI Recruiter →
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <motion.button
        onClick={onClick}
        onMouseEnter={() => setHovered(true)}
        onMouseLeave={() => setHovered(false)}
        whileHover={{ scale: 1.12 }}
        whileTap={{ scale: 0.95 }}
        className="relative w-16 h-16 rounded-full bg-gradient-to-br from-violet-600 to-violet-400
                   flex items-center justify-center shadow-xl border-2 border-white"
        style={{ boxShadow: "0 8px 32px rgba(139,92,246,0.45)" }}
      >
        {/* Pulse ring */}
        <span className="absolute inset-0 rounded-full bg-violet-400 opacity-30 animate-ping" />
        <Sparkles className="w-7 h-7 text-white relative z-10" />
      </motion.button>
    </div>
  );
}


// ── Candidates Tab ────────────────────────────────────────────────────────────

function CandidatesTab({ token, authH }: { token: string; authH: Record<string, string> }) {
  const [applicants,   setApplicants]   = useState<PortalApplicant[]>([]);
  const [loading,      setLoading]      = useState(true);
  const [searchInput,  setSearchInput]  = useState("");
  const [search,       setSearch]       = useState("");
  const [jobFilter,    setJobFilter]    = useState("");
  const [status,       setStatus]       = useState("");        // "" | applied | shortlisted | rejected
  const [sortBy,       setSortBy]       = useState("recent");  // recent | score_high | score_low | name
  const [scoreTier,    setScoreTier]    = useState("");        // "" | high | medium | low
  const [hasCv,        setHasCv]        = useState("");        // "" | yes | no
  const [jobs,         setJobs]         = useState<{ id: string; title: string }[]>([]);
  const [downloading,  setDownloading]  = useState<number | null>(null);
  const [actioning,    setActioning]    = useState<string | null>(null);

  type AiScore = { score: number; reason: string };
  const [aiScores,   setAiScores]   = useState<Record<string, AiScore>>({});
  const [scoringIds, setScoringIds] = useState<Set<string>>(new Set());

  type ChatMsg = { role: "user" | "assistant"; content: string };
  const [chatApplicant, setChatApplicant] = useState<PortalApplicant | null>(null);
  const [chatMessages,  setChatMessages]  = useState<ChatMsg[]>([]);
  const [chatInput,     setChatInput]     = useState("");
  const [chatSending,   setChatSending]   = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const loadJobs = async () => {
    try {
      const res = await fetch(`${API}/api/company/jobs`, { headers: authH });
      if (res.ok) {
        const data = await res.json();
        setJobs((data.jobs ?? []).map((j: any) => ({ id: j.id, title: j.title })));
      }
    } catch { /* ignore */ }
  };

  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search)    params.set("search",     search);
      if (jobFilter) params.set("job_id",     jobFilter);
      if (status)    params.set("status",     status);
      if (sortBy)    params.set("sort_by",    sortBy);
      if (scoreTier) params.set("score_tier", scoreTier);
      if (hasCv)     params.set("has_cv",     hasCv);
      const res = await fetch(`${API}/api/company/portal-applicants?${params}`, { headers: authH });
      if (res.status === 401) return;
      const data = await res.json();
      setApplicants(data.applicants ?? []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); loadJobs(); }, []);
  useEffect(() => { load(); }, [search, jobFilter, status, sortBy, scoreTier, hasCv]);

  // Auto-fire AI scoring for unscored applicants with CVs
  useEffect(() => {
    const unscored = applicants.filter(
      a => a.has_cv && a.ai_match_score === null && !a.is_match && !scoringIds.has(a.application_id)
    );
    if (!unscored.length) return;

    setScoringIds(prev => {
      const next = new Set(prev);
      unscored.forEach(a => next.add(a.application_id));
      return next;
    });

    unscored.forEach(async (a) => {
      try {
        const res = await fetch(`${API}/api/company/candidate/portal-ai-score`, {
          method:  "POST",
          headers: { "Content-Type": "application/json", ...authH },
          body:    JSON.stringify({
            application_id: a.application_id,
            user_id:        a.user_id,
            job_posting_id: a.job_posting_id,
            job_title:      a.applied_for,
          }),
        });
        if (res.ok) {
          const data = await res.json();
          setAiScores(prev => ({ ...prev, [a.application_id]: { score: data.score, reason: data.reason } }));
        }
      } catch { /* skip silently */ }
      finally {
        setScoringIds(prev => { const s = new Set(prev); s.delete(a.application_id); return s; });
      }
    });
  }, [applicants]);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  const openChat = (a: PortalApplicant) => {
    setChatApplicant(a);
    setChatMessages([]);
    setChatInput("");
  };

  const sendChatMessage = async () => {
    if (!chatInput.trim() || chatSending || !chatApplicant) return;
    const userMsg = chatInput.trim();
    setChatInput("");
    setChatMessages(prev => [...prev, { role: "user", content: userMsg }]);
    setChatSending(true);
    setChatMessages(prev => [...prev, { role: "assistant", content: "" }]);

    try {
      const res = await fetch(`${API}/api/company/candidate/${chatApplicant.user_id}/chat`, {
        method:  "POST",
        headers: { "Content-Type": "application/json", ...authH },
        body: JSON.stringify({
          message:        userMsg,
          history:        chatMessages,
          job_posting_id: chatApplicant.job_posting_id,
          job_title:      chatApplicant.applied_for,
        }),
      });

      if (!res.ok || !res.body) {
        const d = await res.json().catch(() => ({}));
        setChatMessages(prev => {
          const msgs = [...prev];
          msgs[msgs.length - 1] = { role: "assistant", content: (d as any).detail ?? "An error occurred." };
          return msgs;
        });
        return;
      }

      const reader  = res.body.getReader();
      const decoder = new TextDecoder();
      let   buffer  = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";
        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const raw = line.slice(6).trim();
          if (raw === "[DONE]") break;
          try {
            const parsed = JSON.parse(raw);
            if (parsed.error) {
              setChatMessages(prev => {
                const msgs = [...prev];
                msgs[msgs.length - 1] = { role: "assistant", content: parsed.error };
                return msgs;
              });
            } else if (parsed.text) {
              setChatMessages(prev => {
                const msgs = [...prev];
                msgs[msgs.length - 1] = { role: "assistant", content: msgs[msgs.length - 1].content + parsed.text };
                return msgs;
              });
            }
          } catch { /* malformed chunk */ }
        }
      }
    } catch {
      setChatMessages(prev => {
        const msgs = [...prev];
        msgs[msgs.length - 1] = { role: "assistant", content: "Failed to connect. Please try again." };
        return msgs;
      });
    } finally {
      setChatSending(false);
    }
  };

  const downloadCV = async (userId: number, name: string) => {
    setDownloading(userId);
    try {
      const res = await fetch(`${API}/api/company/cv/${userId}`, { headers: authH });
      if (!res.ok) { alert("CV not available."); return; }
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href = url; a.download = `${name}_CV.pdf`; a.click();
      URL.revokeObjectURL(url);
    } finally { setDownloading(null); }
  };

  const handleAction = async (appId: string, action: "shortlist" | "reject", applicant?: PortalApplicant) => {
    setActioning(appId);
    try {
      const url = applicant?.is_match
        ? `${API}/api/company/jobs/${applicant.job_posting_id}/matched-candidates/${applicant.user_id}/status`
        : `${API}/api/company/portal-applicants/${appId}/status`;
      const res = await fetch(url, {
        method:  "PATCH",
        headers: { "Content-Type": "application/json", ...authH },
        body:    JSON.stringify({ action }),
      });
      if (!res.ok) { const d = await res.json(); alert(d.detail ?? "Failed."); return; }
      if (action === "reject") {
        setApplicants(prev => prev.filter(a => a.application_id !== appId));
      } else {
        setApplicants(prev => prev.map(a =>
          a.application_id === appId ? { ...a, status: "shortlisted" } : a
        ));
      }
    } finally { setActioning(null); }
  };

  return (
    <>
      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-6">
        <div className="glass-card p-4 text-center">
          <p className="text-2xl font-bold text-foreground">{applicants.length}</p>
          <p className="text-xs text-muted-foreground mt-0.5">Total Applicants</p>
        </div>
        <div className="glass-card p-4 text-center">
          <p className="text-2xl font-bold text-green-400">
            {applicants.filter(a => {
              const s = a.ai_match_score ?? aiScores[a.application_id]?.score ?? 0;
              return s >= 70;
            }).length}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">High Match (≥70%)</p>
        </div>
        <div className="glass-card p-4 text-center sm:col-span-1 col-span-2">
          <p className="text-2xl font-bold text-yellow-400">
            {applicants.filter(a => a.has_cv).length}
          </p>
          <p className="text-xs text-muted-foreground mt-0.5">CVs Available</p>
        </div>
      </div>

      {/* Search + sort + job filter */}
      <div className="flex flex-wrap gap-2 mb-3">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <input
            value={searchInput}
            onChange={e => setSearchInput(e.target.value)}
            onKeyDown={e => e.key === "Enter" && setSearch(searchInput)}
            placeholder="Search by name, email…"
            className="w-full pl-9 pr-4 py-2 rounded-lg bg-input border border-border text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
          />
        </div>
        <select
          value={jobFilter}
          onChange={e => setJobFilter(e.target.value)}
          className="px-3 py-2 rounded-lg bg-input border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
        >
          <option value="">All Jobs</option>
          {jobs.map(j => <option key={j.id} value={j.id}>{j.title}</option>)}
        </select>
        <select
          value={sortBy}
          onChange={e => setSortBy(e.target.value)}
          className="px-3 py-2 rounded-lg bg-input border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
        >
          <option value="recent">Most recent</option>
          <option value="score_high">Score: high → low</option>
          <option value="score_low">Score: low → high</option>
          <option value="name">Name A–Z</option>
        </select>
        <button
          onClick={() => setSearch(searchInput)}
          className="px-4 py-2 rounded-lg bg-muted text-sm text-foreground border border-border hover:bg-muted/80 transition"
        >
          Search
        </button>
      </div>

      {/* Quick filter chips */}
      <div className="flex flex-wrap gap-2 mb-5">
        {/* Status */}
        {(["", "applied", "shortlisted", "rejected"] as const).map(s => (
          <button key={s} onClick={() => setStatus(s)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition
              ${status === s
                ? "bg-primary/15 border-primary/50 text-primary"
                : "bg-muted border-border text-muted-foreground hover:text-foreground"
              }`}>
            {s === "" ? "All status" : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}

        <span className="self-center text-border">|</span>

        {/* AI score tier */}
        {([
          { val: "",       label: "All scores" },
          { val: "high",   label: "≥70% match" },
          { val: "medium", label: "45–69%" },
          { val: "low",    label: "<45%" },
        ]).map(o => (
          <button key={o.val} onClick={() => setScoreTier(o.val)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition
              ${scoreTier === o.val
                ? "bg-violet-500/15 border-violet-500/50 text-violet-400"
                : "bg-muted border-border text-muted-foreground hover:text-foreground"
              }`}>
            {o.label}
          </button>
        ))}

        <span className="self-center text-border">|</span>

        {/* Has CV */}
        {([
          { val: "",    label: "All" },
          { val: "yes", label: "Has CV" },
          { val: "no",  label: "No CV" },
        ]).map(o => (
          <button key={o.val} onClick={() => setHasCv(o.val)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition
              ${hasCv === o.val
                ? "bg-yellow-500/15 border-yellow-500/50 text-yellow-400"
                : "bg-muted border-border text-muted-foreground hover:text-foreground"
              }`}>
            {o.label}
          </button>
        ))}
      </div>

      {/* Applicant list */}
      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
        </div>
      ) : applicants.length === 0 ? (
        <div className="glass-card p-10 text-center text-muted-foreground text-sm">
          <Users className="w-10 h-10 mx-auto mb-3 opacity-30" />
          No applicants yet. Post a job to start receiving applications.
        </div>
      ) : (
        <AnimatePresence>
          <div className="space-y-3">
            {applicants.map((a, i) => {
              const cached  = a.ai_match_score;
              const runtime = aiScores[a.application_id];
              const scoring = scoringIds.has(a.application_id);
              const score   = cached ?? runtime?.score ?? null;
              const reason  = a.ai_score_reason ?? runtime?.reason ?? "";

              return (
                <motion.div
                  key={a.application_id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, x: -40, height: 0, marginBottom: 0 }}
                  transition={{ delay: i * 0.03 }}
                  className="glass-card p-4"
                >
                  <div className="flex flex-col sm:flex-row sm:items-center gap-4">
                    <div className="flex-1 min-w-0 space-y-1.5">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="font-semibold text-foreground">
                          {a.first_name} {a.last_name}
                        </span>

                        {a.is_match && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-violet-500/10 border border-violet-500/30 text-violet-400">
                            Auto-Match
                          </span>
                        )}

                        {score !== null ? (
                          <span
                            title={reason || "AI match score"}
                            className={`flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full border cursor-help
                              ${score >= 70 ? "text-green-400 border-green-500/40 bg-green-500/10"
                              : score >= 45 ? "text-yellow-400 border-yellow-500/40 bg-yellow-500/10"
                              : "text-red-400 border-red-500/40 bg-red-500/10"}`}
                          >
                            <Bot className="w-3 h-3" />{score}% AI match
                          </span>
                        ) : scoring ? (
                          <span className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border border-border text-muted-foreground">
                            <Loader2 className="w-3 h-3 animate-spin" /> Scoring…
                          </span>
                        ) : null}

                        {a.status === "shortlisted" && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/10 border border-green-500/30 text-green-400">
                            Shortlisted
                          </span>
                        )}
                        {a.status === "rejected" && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/10 border border-red-500/30 text-red-400">
                            Rejected
                          </span>
                        )}
                      </div>

                      <div className="flex flex-wrap gap-x-4 gap-y-1">
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                          <Mail className="w-3 h-3" />{a.email}
                        </span>
                        {a.phone && (
                          <span className="flex items-center gap-1 text-xs text-muted-foreground">
                            <Phone className="w-3 h-3" />{a.phone}
                          </span>
                        )}
                      </div>

                      <div className="flex flex-wrap gap-x-4 gap-y-1">
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                          <Briefcase className="w-3 h-3" />
                          <span className="truncate max-w-xs">{a.applied_for}</span>
                        </span>
                        {a.location && (
                          <span className="flex items-center gap-1 text-xs text-muted-foreground">
                            <MapPin className="w-3 h-3" />{a.location}
                          </span>
                        )}
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                          <Clock className="w-3 h-3" />
                          {new Date(a.applied_at).toLocaleDateString("en-IN", {
                            day: "numeric", month: "short", year: "numeric",
                          })}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-1 shrink-0 flex-nowrap">
                      <button
                        onClick={() => openChat(a)}
                        className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-[11px] font-semibold bg-violet-500/10 border border-violet-500/30 text-violet-400 hover:bg-violet-500/20 transition whitespace-nowrap"
                        title="Ask AI about this candidate"
                      >
                        <MessageSquare className="w-3 h-3 shrink-0" /> Ask AI
                      </button>

                      <button
                        onClick={() => downloadCV(a.user_id, `${a.first_name}_${a.last_name}`)}
                        disabled={!a.has_cv || downloading === a.user_id}
                        className={`flex items-center gap-1 px-2 py-1.5 rounded-lg text-[11px] font-semibold transition whitespace-nowrap
                          ${a.has_cv
                            ? "bg-primary/20 border border-primary/40 text-primary hover:bg-primary/30"
                            : "bg-muted border border-border text-muted-foreground opacity-40 cursor-not-allowed"
                          }`}
                        title={a.has_cv ? "Download CV" : "No CV uploaded"}
                      >
                        {downloading === a.user_id
                          ? <Loader2 className="w-3 h-3 animate-spin shrink-0" />
                          : <Download className="w-3 h-3 shrink-0" />
                        }
                        CV
                      </button>

                      {a.status === "shortlisted" ? (
                        <span className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-[11px] font-semibold bg-green-500/10 border border-green-500/30 text-green-400 whitespace-nowrap">
                          <CheckCircle className="w-3 h-3 shrink-0" /> Shortlisted
                        </span>
                      ) : a.status === "rejected" ? (
                        <span className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-[11px] font-semibold bg-red-500/10 border border-red-500/30 text-red-400 whitespace-nowrap">
                          <XCircle className="w-3 h-3 shrink-0" /> Rejected
                        </span>
                      ) : (
                        <>
                          <button
                            onClick={() => handleAction(a.application_id, "shortlist", a)}
                            disabled={actioning === a.application_id}
                            className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-[11px] font-semibold bg-green-500/10 border border-green-500/30 text-green-400 hover:bg-green-500/20 transition disabled:opacity-50 whitespace-nowrap"
                          >
                            {actioning === a.application_id
                              ? <Loader2 className="w-3 h-3 animate-spin shrink-0" />
                              : <CheckCircle className="w-3 h-3 shrink-0" />
                            }
                            Shortlist
                          </button>
                          <button
                            onClick={() => handleAction(a.application_id, "reject", a)}
                            disabled={actioning === a.application_id}
                            className="flex items-center gap-1 px-2 py-1.5 rounded-lg text-[11px] font-semibold bg-red-500/10 border border-red-500/30 text-red-400 hover:bg-red-500/20 transition disabled:opacity-50 whitespace-nowrap"
                          >
                            {actioning === a.application_id
                              ? <Loader2 className="w-3 h-3 animate-spin shrink-0" />
                              : <XCircle className="w-3 h-3 shrink-0" />
                            }
                            Reject
                          </button>
                        </>
                      )}
                    </div>
                  </div>
                </motion.div>
              );
            })}
          </div>
        </AnimatePresence>
      )}

      {/* Chat Drawer */}
      <AnimatePresence>
        {chatApplicant && (
          <motion.div
            className="fixed inset-0 z-50 flex"
            initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}
          >
            <div className="flex-1 bg-black/50 backdrop-blur-sm" onClick={() => setChatApplicant(null)} />
            <motion.div
              initial={{ x: "100%" }} animate={{ x: 0 }} exit={{ x: "100%" }}
              transition={{ type: "spring", damping: 30, stiffness: 300 }}
              className="w-full max-w-md bg-background border-l border-border flex flex-col shadow-2xl"
            >
              <div className="flex items-center justify-between p-4 border-b border-border shrink-0">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-violet-500/20 border border-violet-500/30 flex items-center justify-center">
                    <Bot className="w-4 h-4 text-violet-400" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-foreground leading-none">Talk to CV</p>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      {chatApplicant.first_name} {chatApplicant.last_name}
                    </p>
                  </div>
                </div>
                <button onClick={() => setChatApplicant(null)}
                  className="p-1.5 rounded-lg hover:bg-muted transition text-muted-foreground hover:text-foreground">
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {chatMessages.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-12 text-center px-6">
                    <div className="w-12 h-12 rounded-xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center mb-3">
                      <MessageSquare className="w-6 h-6 text-violet-400 opacity-60" />
                    </div>
                    <p className="text-sm font-medium text-foreground mb-1">Ask anything about this candidate</p>
                    <p className="text-xs text-muted-foreground">
                      Answers are grounded on their CV and profile. Try: "What are their key skills?"
                    </p>
                  </div>
                )}
                {chatMessages.map((msg, i) => (
                  <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[85%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap
                      ${msg.role === "user"
                        ? "bg-primary text-primary-foreground rounded-br-sm"
                        : "bg-muted text-foreground rounded-bl-sm border border-border"
                      }`}>
                      {msg.content}
                    </div>
                  </div>
                ))}
                {chatSending && chatMessages.at(-1)?.role === "assistant" && chatMessages.at(-1)?.content === "" && (
                  <div className="flex justify-start">
                    <div className="bg-muted border border-border px-3.5 py-2.5 rounded-2xl rounded-bl-sm flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "0ms" }} />
                      <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "150ms" }} />
                      <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "300ms" }} />
                    </div>
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>

              <div className="p-4 border-t border-border shrink-0">
                <div className="flex gap-2">
                  <input
                    value={chatInput}
                    onChange={e => setChatInput(e.target.value)}
                    onKeyDown={e => e.key === "Enter" && !e.shiftKey && sendChatMessage()}
                    placeholder="Ask about skills, experience, education…"
                    disabled={chatSending}
                    className="flex-1 px-3 py-2 rounded-lg bg-input border border-border text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-50"
                  />
                  <button
                    onClick={sendChatMessage}
                    disabled={chatSending || !chatInput.trim()}
                    className="p-2.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition shrink-0"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </div>
                <p className="text-xs text-muted-foreground mt-2">
                  AI answers are based solely on this candidate's CV and profile data.
                </p>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}


// ── Post Job Tab ──────────────────────────────────────────────────────────────

const CURRENCIES = ["INR", "USD", "EUR", "GBP", "AED", "SGD", "CAD", "AUD"];

function PostJobTab({ token, authH, onPosted }: { token: string; authH: Record<string, string>; onPosted: () => void }) {
  // Step 1 = give us your JD, Step 2 = review + post
  const [step,        setStep]        = useState<1 | 2>(1);
  const [jdMode,      setJdMode]      = useState<"upload" | "paste">("upload");
  const [pasteText,   setPasteText]   = useState("");
  const [parsing,     setParsing]     = useState(false);
  const [parseError,  setParseError]  = useState("");

  // Form fields (populated by AI, editable by recruiter)
  const [title,       setTitle]       = useState("");
  const [description, setDescription] = useState("");
  const [skillsRaw,   setSkillsRaw]   = useState("");
  const [location,    setLocation]    = useState("");
  const [workMode,    setWorkMode]    = useState("onsite");
  const [jobType,     setJobType]     = useState("full-time");
  const [expMin,      setExpMin]      = useState(0);
  const [expMax,      setExpMax]      = useState(5);
  const [salMin,      setSalMin]      = useState("");
  const [salMax,      setSalMax]      = useState("");
  const [currency,    setCurrency]    = useState("INR");
  const [openings,    setOpenings]    = useState(1);
  const [loading,     setLoading]     = useState(false);
  const [error,       setError]       = useState("");
  const [success,     setSuccess]     = useState("");

  const applyParsed = (data: any) => {
    if (data.title)                   setTitle(data.title);
    if (data.description)             setDescription(data.description);
    if (data.skills?.length)          setSkillsRaw(data.skills.join(", "));
    if (data.experience_min != null)  setExpMin(data.experience_min);
    if (data.experience_max != null)  setExpMax(data.experience_max);
    if (data.salary_min)              setSalMin(String(data.salary_min));
    if (data.salary_max)              setSalMax(String(data.salary_max));
    if (data.location)                setLocation(data.location);
    if (data.work_mode)               setWorkMode(data.work_mode);
    if (data.job_type)                setJobType(data.job_type);
  };

  // Upload PDF / TXT
  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setParseError(""); setParsing(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res  = await fetch(`${API}/api/company/parse-jd`, { method: "POST", headers: authH, body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Parsing failed.");
      applyParsed(data);
      setStep(2);
    } catch (err: any) {
      setParseError(err.message ?? "Could not parse the file. Please try paste instead.");
    } finally {
      setParsing(false);
      e.target.value = "";
    }
  };

  // Paste text → AI parse
  const handleParseText = async () => {
    if (!pasteText.trim()) return;
    setParseError(""); setParsing(true);
    try {
      const res  = await fetch(`${API}/api/company/parse-jd-text`, {
        method:  "POST",
        headers: { "Content-Type": "application/json", ...authH },
        body:    JSON.stringify({ text: pasteText }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Parsing failed.");
      applyParsed(data);
      setStep(2);
    } catch (err: any) {
      setParseError(err.message ?? "Could not parse. Please check the text and try again.");
    } finally {
      setParsing(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(""); setSuccess(""); setLoading(true);
    try {
      const skills = skillsRaw.split(",").map(s => s.trim()).filter(Boolean);
      const res = await fetch(`${API}/api/company/jobs`, {
        method:  "POST",
        headers: { "Content-Type": "application/json", ...authH },
        body: JSON.stringify({
          title, description, skills, location,
          work_mode: workMode, job_type: jobType,
          experience_min: expMin, experience_max: expMax,
          salary_min:     salMin ? parseInt(salMin) : null,
          salary_max:     salMax ? parseInt(salMax) : null,
          salary_currency: currency,
          openings,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Failed to post job.");
      setSuccess("Job posted successfully!");
      setTimeout(onPosted, 1200);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // ── Step 1: Give us your JD ───────────────────────────────────────────────
  if (step === 1) {
    return (
      <div className="glass-card p-8 max-w-2xl space-y-6">
        {/* Header */}
        <div className="text-center space-y-1">
          <div className="w-12 h-12 rounded-xl bg-violet-500/15 border border-violet-500/30 flex items-center justify-center mx-auto mb-3">
            <Sparkles className="w-6 h-6 text-violet-400" />
          </div>
          <h2 className="text-lg font-bold text-foreground">Post a Job with AI</h2>
          <p className="text-sm text-muted-foreground">
            Give us your job description — upload a PDF or paste the text.<br />
            AI will fill all the fields for you instantly.
          </p>
        </div>

        {/* Mode toggle */}
        <div className="flex rounded-lg border border-border overflow-hidden">
          {(["upload", "paste"] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => { setJdMode(m); setParseError(""); }}
              className={`flex-1 py-2 text-sm font-medium transition ${
                jdMode === m
                  ? "bg-violet-500/20 text-violet-400 border-b-2 border-violet-400"
                  : "text-muted-foreground hover:text-foreground hover:bg-muted/30"
              }`}
            >
              {m === "upload" ? "📄 Upload PDF / TXT" : "📋 Paste Text"}
            </button>
          ))}
        </div>

        {/* Upload */}
        {jdMode === "upload" && (
          <label className={`flex flex-col items-center justify-center gap-3 p-10 rounded-xl border-2 border-dashed cursor-pointer transition
            ${parsing ? "border-border opacity-60 pointer-events-none" : "border-violet-500/40 hover:border-violet-500/70 hover:bg-violet-500/5"}`}
          >
            {parsing
              ? <><Loader2 className="w-8 h-8 text-violet-400 animate-spin" /><p className="text-sm text-muted-foreground">Parsing with AI…</p></>
              : <>
                  <Upload className="w-8 h-8 text-violet-400 opacity-70" />
                  <div className="text-center">
                    <p className="text-sm font-medium text-foreground">Drop your JD here or click to browse</p>
                    <p className="text-xs text-muted-foreground mt-0.5">PDF, TXT, DOC, DOCX supported</p>
                  </div>
                </>
            }
            <input type="file" accept=".pdf,.txt,.doc,.docx" className="hidden" onChange={handleFileUpload} disabled={parsing} />
          </label>
        )}

        {/* Paste */}
        {jdMode === "paste" && (
          <div className="space-y-3">
            <textarea
              value={pasteText}
              onChange={e => setPasteText(e.target.value)}
              rows={10}
              placeholder="Paste the full job description here…&#10;&#10;e.g. We are looking for a Senior Software Engineer…"
              className={`${cls} resize-y`}
              disabled={parsing}
            />
            <button
              type="button"
              onClick={handleParseText}
              disabled={parsing || !pasteText.trim()}
              className="w-full py-2.5 px-4 rounded-lg bg-gradient-to-r from-violet-600 to-violet-400 text-white text-sm font-semibold hover:opacity-90 disabled:opacity-50 transition flex items-center justify-center gap-2"
            >
              {parsing
                ? <><Loader2 className="w-4 h-4 animate-spin" /> Parsing with AI…</>
                : <><Sparkles className="w-4 h-4" /> Parse & Fill Fields</>
              }
            </button>
          </div>
        )}

        {parseError && (
          <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{parseError}</p>
        )}

        {/* Skip AI */}
        <p className="text-center text-xs text-muted-foreground">
          Prefer to fill manually?{" "}
          <button type="button" onClick={() => setStep(2)} className="text-violet-400 hover:underline">
            Skip and fill form yourself
          </button>
        </p>
      </div>
    );
  }

  // ── Step 2: Review & post ─────────────────────────────────────────────────
  return (
    <form onSubmit={handleSubmit} className="glass-card p-6 space-y-5 max-w-2xl">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold text-foreground">Review & Post Job</h2>
        <button
          type="button"
          onClick={() => setStep(1)}
          className="text-xs text-violet-400 hover:underline flex items-center gap-1"
        >
          <Upload className="w-3 h-3" /> Re-upload JD
        </button>
      </div>

      <div>
        <label className="block text-xs text-muted-foreground mb-1">Job Title *</label>
        <input value={title} onChange={e => setTitle(e.target.value)} required placeholder="e.g. Senior Software Engineer" className={cls} />
      </div>

      <div>
        <label className="block text-xs text-muted-foreground mb-1">Job Description *</label>
        <textarea
          value={description} onChange={e => setDescription(e.target.value)} required
          rows={6} placeholder="Describe the role, responsibilities, and requirements…"
          className={`${cls} resize-y`}
        />
      </div>

      <div>
        <label className="block text-xs text-muted-foreground mb-1">Required Skills (comma-separated)</label>
        <input value={skillsRaw} onChange={e => setSkillsRaw(e.target.value)}
          placeholder="e.g. Python, SQL, React, AWS" className={cls} />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Location</label>
          <input value={location} onChange={e => setLocation(e.target.value)} placeholder="e.g. Mumbai, India" className={cls} />
        </div>
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Work Mode</label>
          <select value={workMode} onChange={e => setWorkMode(e.target.value)} className={cls}>
            <option value="onsite">On-site</option>
            <option value="remote">Remote</option>
            <option value="hybrid">Hybrid</option>
          </select>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Job Type</label>
          <select value={jobType} onChange={e => setJobType(e.target.value)} className={cls}>
            <option value="full-time">Full-time</option>
            <option value="part-time">Part-time</option>
            <option value="contract">Contract</option>
            <option value="internship">Internship</option>
            <option value="freelance">Freelance</option>
          </select>
        </div>
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Openings</label>
          <input type="number" min={1} value={openings} onChange={e => setOpenings(parseInt(e.target.value) || 1)} className={cls} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Min Experience (years)</label>
          <input type="number" min={0} max={50} value={expMin} onChange={e => setExpMin(parseInt(e.target.value) || 0)} className={cls} />
        </div>
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Max Experience (years)</label>
          <input type="number" min={0} max={50} value={expMax} onChange={e => setExpMax(parseInt(e.target.value) || 5)} className={cls} />
        </div>
      </div>

      <div>
        <label className="block text-xs text-muted-foreground mb-1">Salary Range (optional)</label>
        <div className="flex gap-2 items-center">
          <select value={currency} onChange={e => setCurrency(e.target.value)}
            className="px-3 py-2.5 rounded-lg bg-input border border-border text-sm text-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 shrink-0">
            {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
          <input type="number" min={0} value={salMin} onChange={e => setSalMin(e.target.value)}
            placeholder="Min salary" className={`${cls} flex-1`} />
          <span className="text-muted-foreground text-sm shrink-0">–</span>
          <input type="number" min={0} value={salMax} onChange={e => setSalMax(e.target.value)}
            placeholder="Max salary" className={`${cls} flex-1`} />
        </div>
      </div>

      {error   && <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">{error}</p>}
      {success && <p className="text-sm text-green-400 bg-green-500/10 border border-green-500/20 rounded-lg px-3 py-2">{success}</p>}

      <button type="submit" disabled={loading}
        className="w-full py-2.5 px-4 rounded-lg bg-gradient-to-r from-violet-600 to-violet-400 text-white text-sm font-semibold hover:opacity-90 disabled:opacity-50 transition flex items-center justify-center gap-2">
        {loading ? <><Loader2 className="w-4 h-4 animate-spin" />Posting…</> : "Post Job"}
      </button>
    </form>
  );
}


// ── My Jobs Tab ───────────────────────────────────────────────────────────────

interface MatchedCandidate {
  match_id:         number;
  user_id:          number;
  first_name:       string;
  last_name:        string;
  email:            string;
  phone:            string;
  ai_score:         number | null;
  ai_reasoning:     string | null;
  shortlist_status: string;
  current_job_title: string | null;
  years_experience: number | null;
  expected_ctc:     number | null;
  has_cv:           boolean;
}

function MyJobsTab({ token, authH }: { token: string; authH: Record<string, string> }) {
  const [jobs,             setJobs]             = useState<Job[]>([]);
  const [loading,          setLoading]          = useState(true);
  const [toggling,         setToggling]         = useState<string | null>(null);
  const [deleting,         setDeleting]         = useState<string | null>(null);
  const [expanded,         setExpanded]         = useState<string | null>(null);
  const [matchedMap,       setMatchedMap]       = useState<Record<string, MatchedCandidate[]>>({});
  const [matchLoading,     setMatchLoading]     = useState<string | null>(null);
  const [matchActioning,   setMatchActioning]   = useState<string | null>(null);
  const [matchDownloading, setMatchDownloading] = useState<number | null>(null);

  const loadMatched = async (jobId: string, force = false) => {
    if (!force && matchedMap[jobId] !== undefined) return;
    setMatchLoading(jobId);
    try {
      const res = await fetch(`${API}/api/company/jobs/${jobId}/matched-candidates`, { headers: authH });
      if (res.ok) {
        const data = await res.json();
        setMatchedMap(prev => ({ ...prev, [jobId]: data.candidates ?? [] }));
      }
    } catch { /* ignore */ } finally {
      setMatchLoading(null);
    }
  };

  const reRunMatch = async (jobId: string) => {
    setMatchLoading(jobId);
    try {
      await fetch(`${API}/api/company/jobs/${jobId}/re-match`, { method: "POST", headers: authH });
      // wait ~3s for background thread then reload
      setTimeout(() => loadMatched(jobId, true), 3000);
    } catch {
      setMatchLoading(null);
    }
  };

  const handleMatchAction = async (jobId: string, userId: number, action: "shortlist" | "reject") => {
    const key = `${jobId}_${userId}`;
    setMatchActioning(key);
    try {
      const res = await fetch(`${API}/api/company/jobs/${jobId}/matched-candidates/${userId}/status`, {
        method:  "PATCH",
        headers: { "Content-Type": "application/json", ...authH },
        body:    JSON.stringify({ action }),
      });
      if (res.ok) {
        if (action === "reject") {
          setMatchedMap(prev => ({
            ...prev,
            [jobId]: (prev[jobId] ?? []).filter(c => c.user_id !== userId),
          }));
        } else {
          setMatchedMap(prev => ({
            ...prev,
            [jobId]: (prev[jobId] ?? []).map(c =>
              c.user_id === userId ? { ...c, shortlist_status: "shortlisted" } : c
            ),
          }));
        }
      }
    } finally {
      setMatchActioning(null);
    }
  };

  const downloadMatchedCV = async (userId: number, name: string) => {
    setMatchDownloading(userId);
    try {
      const res = await fetch(`${API}/api/company/cv/${userId}`, { headers: authH });
      if (!res.ok) { alert("CV not available."); return; }
      const blob = await res.blob();
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href = url; a.download = `${name}_CV.pdf`; a.click();
      URL.revokeObjectURL(url);
    } finally { setMatchDownloading(null); }
  };

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/company/jobs`, { headers: authH });
      if (res.ok) {
        const data = await res.json();
        setJobs(data.jobs ?? []);
      }
    } finally { setLoading(false); }
  };

  useEffect(() => { load(); }, []);

  const toggleStatus = async (job: Job) => {
    setToggling(job.id);
    try {
      const res = await fetch(`${API}/api/company/jobs/${job.id}/status`, {
        method:  "PATCH",
        headers: { "Content-Type": "application/json", ...authH },
        body:    JSON.stringify({ is_active: !job.is_active }),
      });
      if (res.ok) setJobs(prev => prev.map(j => j.id === job.id ? { ...j, is_active: !j.is_active } : j));
    } finally { setToggling(null); }
  };

  const deleteJob = async (jobId: string) => {
    if (!confirm("Delete this job posting and all its applications?")) return;
    setDeleting(jobId);
    try {
      const res = await fetch(`${API}/api/company/jobs/${jobId}`, { method: "DELETE", headers: authH });
      if (res.ok) setJobs(prev => prev.filter(j => j.id !== jobId));
      else { const d = await res.json(); alert(d.detail ?? "Failed to delete."); }
    } finally { setDeleting(null); }
  };

  const fmt = (n: number | null, currency: string) =>
    n != null ? `${currency} ${n.toLocaleString()}` : null;

  if (loading) return <div className="flex justify-center py-16"><Loader2 className="w-8 h-8 text-primary animate-spin" /></div>;

  if (jobs.length === 0) return (
    <div className="glass-card p-10 text-center text-muted-foreground text-sm">
      <Briefcase className="w-10 h-10 mx-auto mb-3 opacity-30" />
      No jobs posted yet. Use the "Post a Job" tab to get started.
    </div>
  );

  return (
    <div className="space-y-3">
      {jobs.map((job, i) => (
        <motion.div
          key={job.id}
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, x: -40, height: 0 }}
          transition={{ delay: i * 0.03 }}
          className="glass-card overflow-hidden"
        >
          <div className="p-4">
            <div className="flex items-start justify-between gap-4">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap mb-1">
                  <h3 className="font-semibold text-foreground">{job.title}</h3>
                  <span className={`text-xs px-2 py-0.5 rounded-full border font-medium
                    ${job.is_active
                      ? "text-green-400 border-green-500/40 bg-green-500/10"
                      : "text-muted-foreground border-border bg-muted"
                    }`}>
                    {job.is_active ? "Active" : "Paused"}
                  </span>
                  <span className="text-xs px-2 py-0.5 rounded-full bg-primary/10 border border-primary/30 text-primary">
                    {job.applicant_count} applicant{job.applicant_count !== 1 ? "s" : ""}
                  </span>
                </div>

                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  {job.location && (
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <MapPin className="w-3 h-3" />{job.location}
                    </span>
                  )}
                  <span className="text-xs text-muted-foreground capitalize">{job.work_mode}</span>
                  <span className="text-xs text-muted-foreground capitalize">{job.job_type}</span>
                  <span className="text-xs text-muted-foreground">
                    {job.experience_min}–{job.experience_max} yrs
                  </span>
                  {(job.salary_min || job.salary_max) && (
                    <span className="text-xs text-muted-foreground">
                      {[fmt(job.salary_min, job.salary_currency), fmt(job.salary_max, job.salary_currency)]
                        .filter(Boolean).join(" – ")}
                    </span>
                  )}
                  <span className="flex items-center gap-1 text-xs text-muted-foreground">
                    <Clock className="w-3 h-3" />
                    {new Date(job.created_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
                  </span>
                </div>

                {(job.skills?.length ?? 0) > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {(job.skills ?? []).slice(0, 6).map(s => (
                      <span key={s} className="text-xs px-2 py-0.5 rounded-full bg-muted border border-border text-muted-foreground">
                        {s}
                      </span>
                    ))}
                    {(job.skills?.length ?? 0) > 6 && (
                      <span className="text-xs text-muted-foreground">+{(job.skills?.length ?? 0) - 6} more</span>
                    )}
                  </div>
                )}
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <button
                  onClick={() => toggleStatus(job)}
                  disabled={toggling === job.id}
                  title={job.is_active ? "Pause job" : "Activate job"}
                  className="p-2 rounded-lg hover:bg-muted transition text-muted-foreground hover:text-foreground disabled:opacity-50"
                >
                  {toggling === job.id
                    ? <Loader2 className="w-4 h-4 animate-spin" />
                    : job.is_active
                      ? <ToggleRight className="w-4 h-4 text-green-400" />
                      : <ToggleLeft className="w-4 h-4" />
                  }
                </button>
                <button
                  onClick={() => deleteJob(job.id)}
                  disabled={deleting === job.id}
                  title="Delete job"
                  className="p-2 rounded-lg hover:bg-red-500/10 transition text-muted-foreground hover:text-red-400 disabled:opacity-50"
                >
                  {deleting === job.id
                    ? <Loader2 className="w-4 h-4 animate-spin" />
                    : <Trash2 className="w-4 h-4" />
                  }
                </button>
                <button
                  onClick={() => {
                    const next = expanded === job.id ? null : job.id;
                    setExpanded(next);
                    if (next) loadMatched(next);
                  }}
                  className="p-2 rounded-lg hover:bg-muted transition text-muted-foreground hover:text-foreground"
                  title="Toggle details"
                >
                  <ChevronDown className={`w-4 h-4 transition-transform ${expanded === job.id ? "rotate-180" : ""}`} />
                </button>
              </div>
            </div>
          </div>

          <AnimatePresence>
            {expanded === job.id && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden border-t border-border"
              >
                <div className="p-4 bg-muted/30 space-y-3">
                  <p className="text-xs text-muted-foreground">
                    <span className="font-medium text-foreground">Openings:</span> {job.openings}
                  </p>

                  {/* Auto-matched candidates */}
                  <div>
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2">
                        <Star className="w-3.5 h-3.5 text-violet-400" />
                        <span className="text-xs font-semibold text-foreground">Auto-Matched Candidates</span>
                      </div>
                      <button
                        onClick={() => reRunMatch(job.id)}
                        disabled={matchLoading === job.id}
                        className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium bg-violet-500/10 border border-violet-500/30 text-violet-400 hover:bg-violet-500/20 transition disabled:opacity-50"
                      >
                        {matchLoading === job.id
                          ? <><Loader2 className="w-3 h-3 animate-spin" /> Running…</>
                          : <><Sparkles className="w-3 h-3" /> Re-run Match</>}
                      </button>
                    </div>

                    {matchLoading === job.id ? (
                      <div className="flex items-center gap-2 py-3 text-xs text-muted-foreground">
                        <Loader2 className="w-3.5 h-3.5 animate-spin" /> Running matching…
                      </div>
                    ) : !matchedMap[job.id] || matchedMap[job.id].length === 0 ? (
                      <p className="text-xs text-muted-foreground py-2">
                        No auto-matched candidates yet. Click "Re-run Match" to search now.
                      </p>
                    ) : (
                      <div className="space-y-2">
                        {matchedMap[job.id].map(c => {
                          const actionKey = `${job.id}_${c.user_id}`;
                          return (
                            <div key={c.user_id} className="flex flex-col sm:flex-row sm:items-center gap-3 p-3 rounded-lg bg-background border border-border">
                              <div className="flex-1 min-w-0 space-y-1">
                                <div className="flex items-center gap-2 flex-wrap">
                                  <span className="text-sm font-semibold text-foreground">{c.first_name} {c.last_name}</span>
                                  {c.ai_score !== null && (
                                    <span className={`flex items-center gap-1 text-xs font-bold px-2 py-0.5 rounded-full border
                                      ${c.ai_score >= 70 ? "text-green-400 border-green-500/40 bg-green-500/10"
                                      : c.ai_score >= 45 ? "text-yellow-400 border-yellow-500/40 bg-yellow-500/10"
                                      : "text-red-400 border-red-500/40 bg-red-500/10"}`}
                                      title={c.ai_reasoning ?? ""}
                                    >
                                      <Bot className="w-3 h-3" />{c.ai_score}%
                                    </span>
                                  )}
                                  <span className="text-xs px-2 py-0.5 rounded-full bg-violet-500/10 border border-violet-500/30 text-violet-400">
                                    Auto-Match
                                  </span>
                                  {c.shortlist_status === "shortlisted" && (
                                    <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/10 border border-green-500/30 text-green-400">Shortlisted</span>
                                  )}
                                  {c.shortlist_status === "rejected" && (
                                    <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/10 border border-red-500/30 text-red-400">Rejected</span>
                                  )}
                                </div>
                                <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                                  <span className="flex items-center gap-1"><Mail className="w-3 h-3" />{c.email}</span>
                                  {c.current_job_title && <span className="flex items-center gap-1"><Briefcase className="w-3 h-3" />{c.current_job_title}</span>}
                                  {c.years_experience != null && <span>{c.years_experience} yrs exp</span>}
                                  {c.expected_ctc && <span>CTC: ₹{c.expected_ctc.toLocaleString()}</span>}
                                </div>
                              </div>
                              <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
                                <button
                                  onClick={() => downloadMatchedCV(c.user_id, `${c.first_name}_${c.last_name}`)}
                                  disabled={!c.has_cv || matchDownloading === c.user_id}
                                  className={`flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold transition
                                    ${c.has_cv ? "bg-primary/20 border border-primary/40 text-primary hover:bg-primary/30" : "bg-muted border border-border text-muted-foreground opacity-40 cursor-not-allowed"}`}
                                >
                                  {matchDownloading === c.user_id ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
                                  CV
                                </button>
                                {c.shortlist_status === "pending" && (
                                  <>
                                    <button
                                      onClick={() => handleMatchAction(job.id, c.user_id, "shortlist")}
                                      disabled={matchActioning === actionKey}
                                      className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-green-500/10 border border-green-500/30 text-green-400 hover:bg-green-500/20 transition disabled:opacity-50"
                                    >
                                      {matchActioning === actionKey ? <Loader2 className="w-3 h-3 animate-spin" /> : <CheckCircle className="w-3 h-3" />}
                                      Shortlist
                                    </button>
                                    <button
                                      onClick={() => handleMatchAction(job.id, c.user_id, "reject")}
                                      disabled={matchActioning === actionKey}
                                      className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg text-xs font-semibold bg-red-500/10 border border-red-500/30 text-red-400 hover:bg-red-500/20 transition disabled:opacity-50"
                                    >
                                      {matchActioning === actionKey ? <Loader2 className="w-3 h-3 animate-spin" /> : <XCircle className="w-3 h-3" />}
                                      Reject
                                    </button>
                                  </>
                                )}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      ))}
    </div>
  );
}
