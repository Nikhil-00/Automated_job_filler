import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Building2, Users, LogOut, Search, Download, Loader2,
  Mail, Phone, MapPin, Clock, Bot, CheckCircle, XCircle,
  MessageSquare, Send, X, Sparkles,
} from "lucide-react";
import AgenticChatPanel from "../components/AgenticChatPanel";

const API = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

// ── Types ─────────────────────────────────────────────────────────────────────

interface Applicant {
  application_id:  string;
  applied_for:     string;
  location:        string;
  applied_at:      string;
  job_url:         string | null;
  match_score:     number;
  ai_match_score:  number | null;
  ai_score_reason: string | null;
  status:          string;
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
  companyKey:  string;
  onLogout:    () => void;
}

// ── Main ─────────────────────────────────────────────────────────────────────

export default function CompanyDashboard({ token, companyName, officerName, companyKey, onLogout }: Props) {
  const [agenticOpen, setAgenticOpen] = useState(false);
  const authH = { Authorization: `Bearer ${token}` };

  return (
    <div className="min-h-screen px-4 py-8">
      <div className="max-w-6xl mx-auto">

        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-yellow-600 to-yellow-400 flex items-center justify-center">
              <Building2 className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-foreground">{companyName}</h1>
              <p className="text-xs text-muted-foreground">Welcome, {officerName} · {companyKey.toUpperCase()}</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setAgenticOpen(true)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-yellow-500/10 border border-yellow-500/30 text-yellow-400 hover:bg-yellow-500/20 transition"
            >
              <Sparkles className="w-3.5 h-3.5" /> AI Recruiter
            </button>
            <button
              onClick={onLogout}
              className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition"
            >
              <LogOut className="w-4 h-4" /> Logout
            </button>
          </div>
        </div>

        <CandidatesPanel token={token} authH={authH} companyKey={companyKey} />
      </div>

      <AgenticChatPanel
        token={token}
        companyType="big4"
        isOpen={agenticOpen}
        onClose={() => setAgenticOpen(false)}
      />
    </div>
  );
}


// ── Candidates Panel ──────────────────────────────────────────────────────────

const SORT_MAP = {
  recent:     "Most recent",
  score_high: "Score: high → low",
  score_low:  "Score: low → high",
  name:       "Name A–Z",
};

function CandidatesPanel({ authH, companyKey }: { token: string; authH: Record<string, string>; companyKey: string }) {
  const [applicants,   setApplicants]   = useState<Applicant[]>([]);
  const [loading,      setLoading]      = useState(true);
  const [searchInput,  setSearchInput]  = useState("");
  const [search,       setSearch]       = useState("");
  const [status,       setStatus]       = useState("");
  const [sortBy,       setSortBy]       = useState("recent");
  const [scoreTier,    setScoreTier]    = useState("");
  const [hasCv,        setHasCv]        = useState("");
  const [downloading,  setDownloading]  = useState<number | null>(null);
  const [actioning,    setActioning]    = useState<string | null>(null);

  type AiScore = { score: number; reason: string };
  const [aiScores,   setAiScores]   = useState<Record<string, AiScore>>({});
  const [scoringIds, setScoringIds] = useState<Set<string>>(new Set());

  type ChatMsg = { role: "user" | "assistant"; content: string };
  const [chatApplicant, setChatApplicant] = useState<Applicant | null>(null);
  const [chatMessages,  setChatMessages]  = useState<ChatMsg[]>([]);
  const [chatInput,     setChatInput]     = useState("");
  const [chatSending,   setChatSending]   = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);

  const load = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (search)    params.set("search",     search);
      if (status)    params.set("status",     status);
      if (sortBy)    params.set("sort_by",    sortBy);
      if (scoreTier) params.set("score_tier", scoreTier);
      if (hasCv)     params.set("has_cv",     hasCv);
      const res = await fetch(`${API}/api/company/applicants?${params}`, { headers: authH });
      if (res.status === 401) return;
      const data = await res.json();
      setApplicants(data.applicants ?? []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, []);
  useEffect(() => { load(); }, [search, status, sortBy, scoreTier, hasCv]);

  // Auto-fire AI scoring for unscored applicants that have CVs
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
        const res = await fetch(`${API}/api/company/candidate/ai-score`, {
          method:  "POST",
          headers: { "Content-Type": "application/json", ...authH },
          body:    JSON.stringify({
            application_id: a.application_id,
            user_id:        a.user_id,
            job_url:        a.job_url,
            job_title:      a.applied_for,
            source:         "big4",
          }),
        });
        if (res.ok) {
          const d = await res.json();
          setAiScores(prev => ({ ...prev, [a.application_id]: { score: d.score, reason: d.reason } }));
        }
      } catch { /* skip */ } finally {
        setScoringIds(prev => { const s = new Set(prev); s.delete(a.application_id); return s; });
      }
    });
  }, [applicants]);

  useEffect(() => { chatEndRef.current?.scrollIntoView({ behavior: "smooth" }); }, [chatMessages]);

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
      const res = await fetch(`${API}/api/company/applicants/${appId}/status`, {
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

  const sendChatMessage = async () => {
    if (!chatInput.trim() || chatSending || !chatApplicant) return;
    const msg = chatInput.trim();
    setChatInput("");
    setChatMessages(prev => [...prev, { role: "user", content: msg }]);
    setChatSending(true);
    setChatMessages(prev => [...prev, { role: "assistant", content: "" }]);

    try {
      const res = await fetch(`${API}/api/company/candidate/${chatApplicant.user_id}/chat`, {
        method:  "POST",
        headers: { "Content-Type": "application/json", ...authH },
        body:    JSON.stringify({
          message:   msg,
          history:   chatMessages,
          job_url:   chatApplicant.job_url,
          job_title: chatApplicant.applied_for,
        }),
      });
      if (!res.ok || !res.body) {
        const d = await res.json().catch(() => ({}));
        setChatMessages(prev => { const m = [...prev]; m[m.length - 1] = { role: "assistant", content: (d as any).detail ?? "Error." }; return m; });
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
            if (parsed.text) {
              setChatMessages(prev => {
                const m = [...prev];
                m[m.length - 1] = { role: "assistant", content: m[m.length - 1].content + parsed.text };
                return m;
              });
            }
          } catch { /* skip */ }
        }
      }
    } catch {
      setChatMessages(prev => { const m = [...prev]; m[m.length - 1] = { role: "assistant", content: "Failed to connect." }; return m; });
    } finally { setChatSending(false); }
  };

  // Stats
  const highMatch = applicants.filter(a => (a.ai_match_score ?? aiScores[a.application_id]?.score ?? 0) >= 70).length;
  const withCv    = applicants.filter(a => a.has_cv).length;

  return (
    <>
      {/* Stats */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 mb-6">
        <div className="glass-card p-4 text-center">
          <p className="text-2xl font-bold text-foreground">{applicants.length}</p>
          <p className="text-xs text-muted-foreground mt-0.5">Total Applicants</p>
        </div>
        <div className="glass-card p-4 text-center">
          <p className="text-2xl font-bold text-green-400">{highMatch}</p>
          <p className="text-xs text-muted-foreground mt-0.5">High Match (≥70%)</p>
        </div>
        <div className="glass-card p-4 text-center sm:col-span-1 col-span-2">
          <p className="text-2xl font-bold text-yellow-400">{withCv}</p>
          <p className="text-xs text-muted-foreground mt-0.5">CVs Available</p>
        </div>
      </div>

      {/* Filters */}
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
          value={sortBy}
          onChange={e => setSortBy(e.target.value)}
          className="px-3 py-2 rounded-lg bg-input border border-border text-sm text-foreground focus:outline-none"
        >
          {Object.entries(SORT_MAP).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
        <button
          onClick={() => setSearch(searchInput)}
          className="px-4 py-2 rounded-lg bg-muted text-sm text-foreground border border-border hover:bg-muted/80 transition"
        >
          Search
        </button>
      </div>

      {/* Filter chips */}
      <div className="flex flex-wrap gap-2 mb-5">
        {(["", "applied", "shortlisted", "rejected"] as const).map(s => (
          <button key={s} onClick={() => setStatus(s)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition
              ${status === s ? "bg-primary/15 border-primary/50 text-primary" : "bg-muted border-border text-muted-foreground hover:text-foreground"}`}>
            {s === "" ? "All status" : s.charAt(0).toUpperCase() + s.slice(1)}
          </button>
        ))}
        <span className="self-center text-border">|</span>
        {([
          { val: "", label: "All scores" },
          { val: "high",   label: "≥70% match" },
          { val: "medium", label: "45–69%" },
          { val: "low",    label: "<45%" },
        ]).map(o => (
          <button key={o.val} onClick={() => setScoreTier(o.val)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition
              ${scoreTier === o.val ? "bg-yellow-500/15 border-yellow-500/50 text-yellow-400" : "bg-muted border-border text-muted-foreground hover:text-foreground"}`}>
            {o.label}
          </button>
        ))}
        <span className="self-center text-border">|</span>
        {([{ val: "", label: "All" }, { val: "yes", label: "Has CV" }, { val: "no", label: "No CV" }]).map(o => (
          <button key={o.val} onClick={() => setHasCv(o.val)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium border transition
              ${hasCv === o.val ? "bg-yellow-500/15 border-yellow-500/50 text-yellow-400" : "bg-muted border-border text-muted-foreground hover:text-foreground"}`}>
            {o.label}
          </button>
        ))}
      </div>

      {/* Applicant list */}
      {loading ? (
        <div className="flex justify-center py-16"><Loader2 className="w-8 h-8 text-primary animate-spin" /></div>
      ) : applicants.length === 0 ? (
        <div className="glass-card p-10 text-center text-muted-foreground text-sm">
          <Users className="w-10 h-10 mx-auto mb-3 opacity-30" />
          No applicants yet for {companyKey.toUpperCase()} jobs.
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
                        <span className="font-semibold text-foreground">{a.first_name} {a.last_name}</span>

                        {score !== null ? (
                          <span
                            title={reason}
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
                          <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/10 border border-green-500/30 text-green-400">Shortlisted</span>
                        )}
                        {a.status === "rejected" && (
                          <span className="text-xs px-2 py-0.5 rounded-full bg-red-500/10 border border-red-500/30 text-red-400">Rejected</span>
                        )}
                      </div>

                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1"><Mail className="w-3 h-3" />{a.email}</span>
                        {a.phone && <span className="flex items-center gap-1"><Phone className="w-3 h-3" />{a.phone}</span>}
                      </div>

                      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
                        <span className="flex items-center gap-1 truncate max-w-xs">{a.applied_for}</span>
                        {a.location && <span className="flex items-center gap-1"><MapPin className="w-3 h-3" />{a.location}</span>}
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          {new Date(a.applied_at).toLocaleDateString("en-IN", { day: "numeric", month: "short", year: "numeric" })}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0 flex-wrap justify-end">
                      <button
                        onClick={() => { setChatApplicant(a); setChatMessages([]); setChatInput(""); }}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-yellow-500/10 border border-yellow-500/30 text-yellow-400 hover:bg-yellow-500/20 transition"
                      >
                        <MessageSquare className="w-3.5 h-3.5" /> Ask AI
                      </button>

                      <button
                        onClick={() => downloadCV(a.user_id, `${a.first_name}_${a.last_name}`)}
                        disabled={!a.has_cv || downloading === a.user_id}
                        className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition
                          ${a.has_cv ? "bg-primary/20 border border-primary/40 text-primary hover:bg-primary/30" : "bg-muted border border-border text-muted-foreground opacity-40 cursor-not-allowed"}`}
                      >
                        {downloading === a.user_id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
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
                            {actioning === a.application_id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />}
                            Shortlist
                          </button>
                          <button
                            onClick={() => handleAction(a.application_id, "reject")}
                            disabled={actioning === a.application_id}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-500/10 border border-red-500/30 text-red-400 hover:bg-red-500/20 transition disabled:opacity-50"
                          >
                            {actioning === a.application_id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <XCircle className="w-3.5 h-3.5" />}
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

      {/* Per-candidate chat drawer */}
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
                  <div className="w-8 h-8 rounded-lg bg-yellow-500/20 border border-yellow-500/30 flex items-center justify-center">
                    <Bot className="w-4 h-4 text-yellow-400" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-foreground leading-none">Talk to CV</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{chatApplicant.first_name} {chatApplicant.last_name}</p>
                  </div>
                </div>
                <button onClick={() => setChatApplicant(null)} className="p-1.5 rounded-lg hover:bg-muted transition text-muted-foreground hover:text-foreground">
                  <X className="w-4 h-4" />
                </button>
              </div>

              <div className="flex-1 overflow-y-auto p-4 space-y-3">
                {chatMessages.length === 0 && (
                  <div className="flex flex-col items-center justify-center py-12 text-center px-6">
                    <div className="w-12 h-12 rounded-xl bg-yellow-500/10 border border-yellow-500/20 flex items-center justify-center mb-3">
                      <MessageSquare className="w-6 h-6 text-yellow-400 opacity-60" />
                    </div>
                    <p className="text-sm font-medium text-foreground mb-1">Ask anything about this candidate</p>
                    <p className="text-xs text-muted-foreground">Try: "What are their key skills?"</p>
                  </div>
                )}
                {chatMessages.map((msg, i) => (
                  <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                    <div className={`max-w-[85%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap
                      ${msg.role === "user" ? "bg-primary text-primary-foreground rounded-br-sm" : "bg-muted text-foreground rounded-bl-sm border border-border"}`}>
                      {msg.content}
                    </div>
                  </div>
                ))}
                {chatSending && chatMessages.at(-1)?.content === "" && (
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
                    placeholder="Ask about skills, experience…"
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
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
