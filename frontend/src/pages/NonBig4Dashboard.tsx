import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Building2, Users, Briefcase, PlusCircle, Search, Download,
  MapPin, Clock, Loader2, LogOut, Mail, Phone,
  CheckCircle, XCircle, MessageSquare, Send, X, Bot,
  ToggleLeft, ToggleRight, Trash2, ChevronDown,
} from "lucide-react";

const API = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

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
  const [tab, setTab] = useState<Tab>("candidates");

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
          <button onClick={onLogout}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition">
            <LogOut className="w-4 h-4" /> Logout
          </button>
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
      a => a.has_cv && a.ai_match_score === null && !scoringIds.has(a.application_id)
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

  const handleAction = async (appId: string, action: "shortlist" | "reject") => {
    setActioning(appId);
    try {
      const res = await fetch(`${API}/api/company/portal-applicants/${appId}/status`, {
        method:  "PATCH",
        headers: { "Content-Type": "application/json", ...authH },
        body:    JSON.stringify({ action }),
      });
      if (!res.ok) { const d = await res.json(); alert(d.detail ?? "Failed."); return; }
      setApplicants(prev => prev.map(a =>
        a.application_id === appId
          ? { ...a, status: action === "shortlist" ? "shortlisted" : "rejected" }
          : a
      ));
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

                    <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
                      <button
                        onClick={() => openChat(a)}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-violet-500/10 border border-violet-500/30 text-violet-400 hover:bg-violet-500/20 transition"
                        title="Ask AI about this candidate"
                      >
                        <MessageSquare className="w-3.5 h-3.5" /> Ask AI
                      </button>

                      <button
                        onClick={() => downloadCV(a.user_id, `${a.first_name}_${a.last_name}`)}
                        disabled={!a.has_cv || downloading === a.user_id}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition
                          ${a.has_cv
                            ? "bg-primary/20 border border-primary/40 text-primary hover:bg-primary/30"
                            : "bg-muted border border-border text-muted-foreground opacity-40 cursor-not-allowed"
                          }`}
                        title={a.has_cv ? "Download CV" : "No CV uploaded"}
                      >
                        {downloading === a.user_id
                          ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          : <Download className="w-3.5 h-3.5" />
                        }
                        {a.has_cv ? "CV" : "No CV"}
                      </button>

                      {a.status === "shortlisted" ? (
                        <span className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-green-500/10 border border-green-500/30 text-green-400">
                          <CheckCircle className="w-3.5 h-3.5" /> Shortlisted
                        </span>
                      ) : a.status === "rejected" ? (
                        <span className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-500/10 border border-red-500/30 text-red-400">
                          <XCircle className="w-3.5 h-3.5" /> Rejected
                        </span>
                      ) : (
                        <>
                          <button
                            onClick={() => handleAction(a.application_id, "shortlist")}
                            disabled={actioning === a.application_id}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-green-500/10 border border-green-500/30 text-green-400 hover:bg-green-500/20 transition disabled:opacity-50"
                          >
                            {actioning === a.application_id
                              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              : <CheckCircle className="w-3.5 h-3.5" />
                            }
                            Shortlist
                          </button>
                          <button
                            onClick={() => handleAction(a.application_id, "reject")}
                            disabled={actioning === a.application_id}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-500/10 border border-red-500/30 text-red-400 hover:bg-red-500/20 transition disabled:opacity-50"
                          >
                            {actioning === a.application_id
                              ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                              : <XCircle className="w-3.5 h-3.5" />
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
  const [title,       setTitle]       = useState("");
  const [description, setDescription] = useState("");
  const [skillsRaw,   setSkillsRaw]   = useState(""); // comma-separated
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
          salary_min:     salMin  ? parseInt(salMin)  : null,
          salary_max:     salMax  ? parseInt(salMax)  : null,
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

  return (
    <form onSubmit={handleSubmit} className="glass-card p-6 space-y-5 max-w-2xl">
      <h2 className="text-base font-semibold text-foreground">Post a New Job</h2>

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

function MyJobsTab({ token, authH }: { token: string; authH: Record<string, string> }) {
  const [jobs,      setJobs]      = useState<Job[]>([]);
  const [loading,   setLoading]   = useState(true);
  const [toggling,  setToggling]  = useState<string | null>(null);
  const [deleting,  setDeleting]  = useState<string | null>(null);
  const [expanded,  setExpanded]  = useState<string | null>(null);

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

                {job.skills.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {job.skills.slice(0, 6).map(s => (
                      <span key={s} className="text-xs px-2 py-0.5 rounded-full bg-muted border border-border text-muted-foreground">
                        {s}
                      </span>
                    ))}
                    {job.skills.length > 6 && (
                      <span className="text-xs text-muted-foreground">+{job.skills.length - 6} more</span>
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
                  onClick={() => setExpanded(expanded === job.id ? null : job.id)}
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
                <div className="p-4 bg-muted/30">
                  <p className="text-xs text-muted-foreground whitespace-pre-line leading-relaxed">
                    {/* show first 500 chars of description */}
                    {/* description is not in list response — show openings info instead */}
                    <span className="font-medium text-foreground">Openings:</span> {job.openings}
                  </p>
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </motion.div>
      ))}
    </div>
  );
}
