import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bot, X, Send, Search, ChevronDown, Mail, Check, Ban,
  Briefcase, Users, Loader2, Sparkles, AlertTriangle, Info,
} from "lucide-react";

const API = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

// ── Types ─────────────────────────────────────────────────────────────────────

interface AgenticJob {
  id:              string;
  title:           string;
  location:        string;
  status:          string;
  created_at:      string;
  applicant_count: number;
}

interface EmailPreview {
  candidate_id: number;
  job_id:       string;
  to_name:      string;
  to_email:     string;
  email_type:   string;
  subject:      string;
  body:         string;
  warnings:     string[];
  already_sent: boolean;
}

type MsgRole = "user" | "assistant" | "tool_call" | "email_preview";

interface ChatMessage {
  role:      MsgRole;
  content:   string;
  toolName?: string;
  preview?:  EmailPreview;
}

interface SessionState {
  last_shown_candidates:    Array<{ id: number; name: string }>;
  last_discussed_candidate: { id: number; name: string } | null;
}

interface Props {
  token:   string;
  isOpen:  boolean;
  onClose: () => void;
}

// ── Tool label map ────────────────────────────────────────────────────────────

const TOOL_LABELS: Record<string, string> = {
  get_candidates:         "Looking up candidates…",
  prepare_email_preview:  "Preparing email preview…",
  get_application_status: "Checking application status…",
  get_job_details:        "Loading job details…",
};

const EMAIL_TYPE_LABELS: Record<string, string> = {
  shortlist:        "Shortlist",
  interview_invite: "Interview Invite",
  rejection:        "Rejection",
  offer:            "Job Offer",
};

// ── Main component ────────────────────────────────────────────────────────────

export default function AgenticChatPanel({ token, isOpen, onClose }: Props) {
  const authH = { Authorization: `Bearer ${token}` };

  // Jobs
  const [jobs,          setJobs]          = useState<AgenticJob[]>([]);
  const [jobsLoading,   setJobsLoading]   = useState(false);
  const [jobSearch,     setJobSearch]     = useState("");
  const [dropdownOpen,  setDropdownOpen]  = useState(false);
  const [selectedJob,   setSelectedJob]   = useState<AgenticJob | null>(null);

  // Chat
  const [messages,      setMessages]      = useState<ChatMessage[]>([]);
  const [input,         setInput]         = useState("");
  const [sending,       setSending]       = useState(false);
  const [sessionState,  setSessionState]  = useState<SessionState>({
    last_shown_candidates:    [],
    last_discussed_candidate: null,
  });

  // Email confirmation
  const [confirmingEmail, setConfirmingEmail] = useState(false);
  const [emailSent,        setEmailSent]       = useState(false);

  const messagesEndRef  = useRef<HTMLDivElement>(null);
  const dropdownRef     = useRef<HTMLDivElement>(null);
  const inputRef        = useRef<HTMLInputElement>(null);

  // ── Fetch jobs on open ──────────────────────────────────────────────────────
  useEffect(() => {
    if (!isOpen) return;
    setJobsLoading(true);
    fetch(`${API}/api/company/agentic-jobs`, { headers: authH })
      .then(r => r.json())
      .then(d => setJobs(d.jobs ?? []))
      .catch(() => setJobs([]))
      .finally(() => setJobsLoading(false));
  }, [isOpen]);

  // ── Auto-scroll ─────────────────────────────────────────────────────────────
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // ── Close dropdown on outside click ────────────────────────────────────────
  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ── Reset when panel closes ─────────────────────────────────────────────────
  useEffect(() => {
    if (!isOpen) {
      setMessages([]);
      setInput("");
      setSelectedJob(null);
      setSessionState({ last_shown_candidates: [], last_discussed_candidate: null });
      setEmailSent(false);
    }
  }, [isOpen]);

  // ── Filtered jobs for dropdown ──────────────────────────────────────────────
  const filteredJobs = jobs.filter(j =>
    j.title.toLowerCase().includes(jobSearch.toLowerCase())
  );

  // ── Send message ────────────────────────────────────────────────────────────
  const sendMessage = async () => {
    if (!input.trim() || sending || !selectedJob) return;
    const userText = input.trim();
    setInput("");

    const history = messages
      .filter(m => m.role === "user" || m.role === "assistant")
      .map(m => ({ role: m.role as "user" | "assistant", content: m.content }));

    setMessages(prev => [...prev, { role: "user", content: userText }]);
    setSending(true);

    // Seed empty assistant bubble
    setMessages(prev => [...prev, { role: "assistant", content: "" }]);

    try {
      const res = await fetch(`${API}/api/company/agentic-chat`, {
        method:  "POST",
        headers: { "Content-Type": "application/json", ...authH },
        body:    JSON.stringify({
          message:       userText,
          job_id:        selectedJob.id,
          history,
          session_state: sessionState,
        }),
      });

      if (!res.ok || !res.body) {
        const d = await res.json().catch(() => ({}));
        setMessages(prev => {
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

          let parsed: any;
          try { parsed = JSON.parse(raw); } catch { continue; }

          if (parsed.error) {
            setMessages(prev => {
              const msgs = [...prev];
              msgs[msgs.length - 1] = { role: "assistant", content: parsed.error };
              return msgs;
            });
          } else if (parsed.type === "tool_call") {
            setMessages(prev => [
              ...prev.slice(0, -1),  // remove empty assistant bubble
              { role: "tool_call", content: TOOL_LABELS[parsed.tool] ?? `Running ${parsed.tool}…`, toolName: parsed.tool },
              { role: "assistant", content: "" },  // re-add empty bubble
            ]);
          } else if (parsed.type === "email_preview") {
            setMessages(prev => [
              ...prev.slice(0, -1),
              { role: "email_preview", content: "", preview: parsed.preview },
              { role: "assistant", content: "" },
            ]);
            setEmailSent(false);
          } else if (parsed.type === "session_state") {
            setSessionState(parsed.state);
          } else if (parsed.text) {
            setMessages(prev => {
              const msgs = [...prev];
              msgs[msgs.length - 1] = {
                ...msgs[msgs.length - 1],
                content: msgs[msgs.length - 1].content + parsed.text,
              };
              return msgs;
            });
          }
        }
      }

      // Remove trailing empty assistant bubble if nothing was written
      setMessages(prev => {
        const last = prev[prev.length - 1];
        if (last?.role === "assistant" && last.content === "") {
          return prev.slice(0, -1);
        }
        return prev;
      });
    } catch {
      setMessages(prev => {
        const msgs = [...prev];
        msgs[msgs.length - 1] = { role: "assistant", content: "Connection failed. Please try again." };
        return msgs;
      });
    } finally {
      setSending(false);
      inputRef.current?.focus();
    }
  };

  // ── Confirm & Send email ────────────────────────────────────────────────────
  const confirmSendEmail = async (preview: EmailPreview) => {
    setConfirmingEmail(true);
    try {
      const res = await fetch(`${API}/api/company/send-email`, {
        method:  "POST",
        headers: { "Content-Type": "application/json", ...authH },
        body:    JSON.stringify({
          candidate_id: preview.candidate_id,
          job_id:       preview.job_id,
          email_type:   preview.email_type,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setMessages(prev => [...prev, {
          role:    "assistant",
          content: `Failed to send email: ${data.detail ?? "Unknown error."}`,
        }]);
        return;
      }
      setEmailSent(true);
      setMessages(prev => [...prev, {
        role:    "assistant",
        content: `Email sent successfully to ${preview.to_name} (${preview.to_email}).`,
      }]);
    } finally {
      setConfirmingEmail(false);
    }
  };

  const cancelEmail = () => {
    setMessages(prev => [...prev, {
      role:    "assistant",
      content: "Email cancelled. No email was sent.",
    }]);
  };

  // ── Render ──────────────────────────────────────────────────────────────────
  return (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          key="agentic-backdrop"
          className="fixed inset-0 z-50 flex"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          {/* Backdrop */}
          <div
            className="flex-1 bg-black/50 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            key="agentic-panel"
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", damping: 30, stiffness: 300 }}
            className="w-full max-w-lg bg-background border-l border-border flex flex-col shadow-2xl"
          >
            {/* ── Header ───────────────────────────────────────────────────── */}
            <div className="flex items-center justify-between p-4 border-b border-border shrink-0">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-violet-500/20 border border-violet-500/30 flex items-center justify-center">
                  <Sparkles className="w-4 h-4 text-violet-400" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-foreground leading-none">AI Recruiter Assistant</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {selectedJob ? selectedJob.title : "Select a job to begin"}
                  </p>
                </div>
              </div>
              <button
                onClick={onClose}
                className="p-1.5 rounded-lg hover:bg-muted transition text-muted-foreground hover:text-foreground"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* ── Job selector ─────────────────────────────────────────────── */}
            <div className="p-3 border-b border-border shrink-0" ref={dropdownRef}>
              {jobsLoading ? (
                <div className="flex items-center gap-2 px-3 py-2 text-sm text-muted-foreground">
                  <Loader2 className="w-4 h-4 animate-spin" /> Loading jobs…
                </div>
              ) : jobs.length === 0 ? (
                <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-muted/50 border border-border text-sm text-muted-foreground">
                  <Briefcase className="w-4 h-4 shrink-0" />
                  You have no active job postings. Create one first.
                </div>
              ) : (
                <div className="relative">
                  <button
                    onClick={() => setDropdownOpen(v => !v)}
                    className="w-full flex items-center justify-between px-3 py-2 rounded-lg bg-input border border-border text-sm text-foreground hover:border-primary/50 transition"
                  >
                    <span className="flex items-center gap-2 min-w-0">
                      <Briefcase className="w-4 h-4 text-muted-foreground shrink-0" />
                      {selectedJob ? (
                        <span className="truncate font-medium">{selectedJob.title}</span>
                      ) : (
                        <span className="text-muted-foreground">Select a job posting…</span>
                      )}
                    </span>
                    {selectedJob && (
                      <span className="flex items-center gap-1.5 ml-2 shrink-0">
                        <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${
                          selectedJob.status === "active"
                            ? "bg-green-500/10 text-green-400 border border-green-500/30"
                            : "bg-muted text-muted-foreground border border-border"
                        }`}>
                          {selectedJob.status}
                        </span>
                        <span className="flex items-center gap-1 text-xs text-muted-foreground">
                          <Users className="w-3 h-3" />{selectedJob.applicant_count}
                        </span>
                      </span>
                    )}
                    <ChevronDown className={`w-4 h-4 ml-2 text-muted-foreground shrink-0 transition-transform ${dropdownOpen ? "rotate-180" : ""}`} />
                  </button>

                  <AnimatePresence>
                    {dropdownOpen && (
                      <motion.div
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        exit={{ opacity: 0, y: -4 }}
                        transition={{ duration: 0.12 }}
                        className="absolute left-0 right-0 top-full mt-1 z-10 bg-background border border-border rounded-lg shadow-xl overflow-hidden"
                      >
                        {/* Search within dropdown */}
                        <div className="p-2 border-b border-border">
                          <div className="relative">
                            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
                            <input
                              value={jobSearch}
                              onChange={e => setJobSearch(e.target.value)}
                              placeholder="Search jobs…"
                              className="w-full pl-8 pr-3 py-1.5 rounded-md bg-input border border-border text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/50"
                              autoFocus
                            />
                          </div>
                        </div>

                        <div className="max-h-52 overflow-y-auto">
                          {filteredJobs.length === 0 ? (
                            <p className="px-3 py-4 text-sm text-muted-foreground text-center">No jobs found.</p>
                          ) : (
                            filteredJobs.map(job => (
                              <button
                                key={job.id}
                                onClick={() => {
                                  setSelectedJob(job);
                                  setDropdownOpen(false);
                                  setJobSearch("");
                                  setMessages([]);
                                  setSessionState({ last_shown_candidates: [], last_discussed_candidate: null });
                                }}
                                className={`w-full text-left px-3 py-2.5 flex items-center justify-between hover:bg-muted transition ${
                                  selectedJob?.id === job.id ? "bg-primary/10" : ""
                                }`}
                              >
                                <div className="min-w-0">
                                  <p className="text-sm font-medium text-foreground truncate">{job.title}</p>
                                  {job.location && (
                                    <p className="text-xs text-muted-foreground truncate">{job.location}</p>
                                  )}
                                </div>
                                <div className="flex items-center gap-2 ml-3 shrink-0">
                                  <span className={`text-xs px-1.5 py-0.5 rounded-full font-medium ${
                                    job.status === "active"
                                      ? "bg-green-500/10 text-green-400 border border-green-500/30"
                                      : "bg-muted text-muted-foreground border border-border"
                                  }`}>
                                    {job.status}
                                  </span>
                                  <span className="flex items-center gap-1 text-xs text-muted-foreground">
                                    <Users className="w-3 h-3" />{job.applicant_count}
                                  </span>
                                </div>
                              </button>
                            ))
                          )}
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              )}
            </div>

            {/* ── Messages ─────────────────────────────────────────────────── */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {!selectedJob ? (
                <div className="flex flex-col items-center justify-center h-full text-center px-6">
                  <div className="w-14 h-14 rounded-2xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center mb-4">
                    <Sparkles className="w-7 h-7 text-violet-400 opacity-70" />
                  </div>
                  <p className="text-sm font-semibold text-foreground mb-1">Select a job to start</p>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    Choose a job posting above, then ask anything — find top candidates,
                    compare profiles, check skills, or prepare emails.
                  </p>
                </div>
              ) : messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center h-full text-center px-6">
                  <div className="w-14 h-14 rounded-2xl bg-violet-500/10 border border-violet-500/20 flex items-center justify-center mb-4">
                    <Bot className="w-7 h-7 text-violet-400 opacity-70" />
                  </div>
                  <p className="text-sm font-semibold text-foreground mb-2">
                    Ready for <span className="text-violet-400">{selectedJob.title}</span>
                  </p>
                  <p className="text-xs text-muted-foreground mb-4 leading-relaxed">
                    {selectedJob.applicant_count} applicant{selectedJob.applicant_count !== 1 ? "s" : ""} · Try asking:
                  </p>
                  <div className="space-y-1.5 w-full">
                    {[
                      "Who are the top 5 candidates?",
                      "Find candidates with Python experience",
                      "Compare the top 3 candidates",
                    ].map(q => (
                      <button
                        key={q}
                        onClick={() => { setInput(q); inputRef.current?.focus(); }}
                        className="w-full text-left px-3 py-2 rounded-lg bg-muted/50 border border-border text-xs text-muted-foreground hover:text-foreground hover:bg-muted transition"
                      >
                        {q}
                      </button>
                    ))}
                  </div>
                </div>
              ) : (
                messages.map((msg, i) => {
                  if (msg.role === "tool_call") {
                    return (
                      <div key={i} className="flex items-center gap-2 text-xs text-muted-foreground py-1">
                        <Loader2 className="w-3.5 h-3.5 animate-spin text-violet-400 shrink-0" />
                        <span>{msg.content}</span>
                      </div>
                    );
                  }

                  if (msg.role === "email_preview" && msg.preview) {
                    const p = msg.preview;
                    return (
                      <div key={i} className="rounded-xl border border-violet-500/30 bg-violet-500/5 overflow-hidden">
                        {/* Preview header */}
                        <div className="flex items-center gap-2 px-3 py-2 bg-violet-500/10 border-b border-violet-500/20">
                          <Mail className="w-4 h-4 text-violet-400 shrink-0" />
                          <span className="text-xs font-semibold text-violet-300">
                            Email Preview — {EMAIL_TYPE_LABELS[p.email_type] ?? p.email_type}
                          </span>
                        </div>

                        <div className="p-3 space-y-2">
                          {/* Warnings */}
                          {p.warnings.map((w, wi) => (
                            <div key={wi} className="flex items-start gap-1.5 text-xs text-yellow-400">
                              <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                              <span>{w}</span>
                            </div>
                          ))}

                          {/* To */}
                          <div className="text-xs text-muted-foreground">
                            <span className="font-medium text-foreground">To: </span>
                            {p.to_name} &lt;{p.to_email}&gt;
                          </div>

                          {/* Subject */}
                          <div className="text-xs text-muted-foreground">
                            <span className="font-medium text-foreground">Subject: </span>
                            {p.subject}
                          </div>

                          {/* Body */}
                          <div className="mt-1 p-2.5 rounded-lg bg-background border border-border text-xs text-foreground leading-relaxed max-h-40 overflow-y-auto whitespace-pre-wrap">
                            {p.body}
                          </div>

                          {/* Actions */}
                          {!emailSent ? (
                            <div className="flex gap-2 mt-2">
                              <button
                                onClick={() => confirmSendEmail(p)}
                                disabled={confirmingEmail || p.already_sent}
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-green-500/10 border border-green-500/30 text-green-400 hover:bg-green-500/20 transition disabled:opacity-40 disabled:cursor-not-allowed"
                              >
                                {confirmingEmail
                                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                  : <Check className="w-3.5 h-3.5" />
                                }
                                {p.already_sent ? "Already Sent" : "Confirm & Send"}
                              </button>
                              <button
                                onClick={cancelEmail}
                                disabled={confirmingEmail}
                                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-muted border border-border text-muted-foreground hover:text-foreground hover:bg-muted/80 transition disabled:opacity-40"
                              >
                                <Ban className="w-3.5 h-3.5" /> Cancel
                              </button>
                            </div>
                          ) : (
                            <div className="flex items-center gap-1.5 text-xs text-green-400 mt-1">
                              <Check className="w-3.5 h-3.5" /> Email sent successfully.
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  }

                  // user / assistant
                  return (
                    <div key={i} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"}`}>
                      <div
                        className={`max-w-[88%] px-3.5 py-2.5 rounded-2xl text-sm leading-relaxed whitespace-pre-wrap ${
                          msg.role === "user"
                            ? "bg-primary text-primary-foreground rounded-br-sm"
                            : "bg-muted text-foreground rounded-bl-sm border border-border"
                        }`}
                      >
                        {msg.content || (
                          // Empty assistant bubble = still streaming
                          <span className="flex items-center gap-1">
                            <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "0ms" }} />
                            <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "150ms" }} />
                            <span className="w-1.5 h-1.5 rounded-full bg-muted-foreground animate-bounce" style={{ animationDelay: "300ms" }} />
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* ── Input ────────────────────────────────────────────────────── */}
            <div className="p-4 border-t border-border shrink-0">
              <div className="flex gap-2">
                <input
                  ref={inputRef}
                  value={input}
                  onChange={e => setInput(e.target.value)}
                  onKeyDown={e => e.key === "Enter" && !e.shiftKey && sendMessage()}
                  placeholder={
                    !selectedJob
                      ? "Select a job first…"
                      : "Ask about candidates, compare, or prepare emails…"
                  }
                  disabled={sending || !selectedJob}
                  className="flex-1 px-3 py-2 rounded-lg bg-input border border-border text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 disabled:opacity-50 transition"
                />
                <button
                  onClick={sendMessage}
                  disabled={sending || !input.trim() || !selectedJob}
                  className="p-2.5 rounded-lg bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition shrink-0"
                  title="Send"
                >
                  {sending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Send className="w-4 h-4" />}
                </button>
              </div>
              <p className="text-xs text-muted-foreground mt-1.5 flex items-center gap-1">
                <Info className="w-3 h-3 shrink-0" />
                AI works only with verified applicant data. Answers are scoped to the selected job.
              </p>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
