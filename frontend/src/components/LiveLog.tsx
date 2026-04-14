import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Monitor, CheckCircle, XCircle, Clock, ExternalLink, X, MapPin, Briefcase, Brain, Coins } from "lucide-react";
import { LogEntry, CompanyEntry, CostSummary } from "@/lib/mockApi";

interface LiveLogProps {
  logs:        LogEntry[];
  progress:    { current: number; total: number };
  accent?:     string;
  screenshot:  string | null;
  companies:   CompanyEntry[];
  costSummary: CostSummary | null;
}

const typeColors: Record<string, string> = {
  info:    "text-muted-foreground",
  found:   "text-blue-400",
  success: "text-green-400",
  error:   "text-red-400",
  warning: "text-yellow-400",
};

const statusIcon = (status: CompanyEntry["status"]) => {
  if (status === "applied")        return <CheckCircle className="w-3.5 h-3.5 text-green-400 shrink-0" />;
  if (status === "already_applied") return <Clock       className="w-3.5 h-3.5 text-blue-400  shrink-0" />;
  return                                   <XCircle     className="w-3.5 h-3.5 text-red-400   shrink-0" />;
};

const statusLabel: Record<CompanyEntry["status"], string> = {
  applied:        "Applied",
  skipped:        "Skipped",
  already_applied: "Done",
};

const statusBadge: Record<CompanyEntry["status"], string> = {
  applied:        "bg-green-500/15 text-green-400 border-green-500/30",
  skipped:        "bg-red-500/15   text-red-400   border-red-500/30",
  already_applied: "bg-blue-500/15  text-blue-400  border-blue-500/30",
};

/* ── Job detail modal ─────────────────────────────────────────────────────── */
const JobModal = ({ entry, onClose }: { entry: CompanyEntry; onClose: () => void }) => {
  // Parse skills from description — lines with bullet / comma lists
  const skillKeywords = [
    "python","sql","machine learning","deep learning","nlp","llm","pytorch","tensorflow",
    "scikit","pandas","numpy","spark","aws","gcp","azure","docker","kubernetes","git",
    "react","fastapi","flask","rag","langchain","transformers","huggingface","openai",
    "power bi","tableau","excel","mongodb","postgresql","mysql","redis","kafka",
  ];
  const descLower   = entry.description.toLowerCase();
  const foundSkills = skillKeywords.filter(s => descLower.includes(s));

  return (
    <motion.div
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />

      {/* Panel */}
      <motion.div
        className="relative z-10 w-full max-w-2xl max-h-[90vh] flex flex-col glass-card overflow-hidden"
        initial={{ scale: 0.92, y: 24 }}
        animate={{ scale: 1,    y: 0  }}
        exit={{ scale: 0.92,    y: 24 }}
        transition={{ type: "spring", stiffness: 300, damping: 28 }}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 p-5 border-b border-border">
          <div className="flex-1 min-w-0">
            <h2 className="text-base font-bold text-foreground leading-tight">{entry.title}</h2>
            <p className="text-sm text-muted-foreground mt-0.5 font-medium">{entry.company}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full border text-xs font-medium ${statusBadge[entry.status]}`}>
              {statusIcon(entry.status)}
              {statusLabel[entry.status]}
            </span>
            {entry.url && (
              <a href={entry.url} target="_blank" rel="noopener noreferrer"
                className="p-1.5 rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground">
                <ExternalLink className="w-4 h-4" />
              </a>
            )}
            <button onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-muted transition-colors text-muted-foreground hover:text-foreground">
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Meta row */}
        <div className="flex flex-wrap gap-4 px-5 py-3 border-b border-border text-xs text-muted-foreground">
          {entry.location && (
            <span className="flex items-center gap-1.5">
              <MapPin className="w-3.5 h-3.5" /> {entry.location}
            </span>
          )}
          <span className="flex items-center gap-1.5">
            <Briefcase className="w-3.5 h-3.5" /> {entry.company}
          </span>
        </div>

        {/* AI reason */}
        <div className="flex items-start gap-2.5 mx-5 mt-4 p-3 rounded-lg bg-primary/8 border border-primary/20">
          <Brain className="w-4 h-4 text-primary shrink-0 mt-0.5" />
          <div>
            <p className="text-xs font-semibold text-primary mb-0.5">AI Decision</p>
            <p className="text-xs text-muted-foreground leading-relaxed">{entry.reason}</p>
          </div>
        </div>

        {/* Skills detected */}
        {foundSkills.length > 0 && (
          <div className="px-5 mt-4">
            <p className="text-xs font-semibold text-foreground mb-2">Skills Detected</p>
            <div className="flex flex-wrap gap-1.5">
              {foundSkills.map(s => (
                <span key={s} className="px-2 py-0.5 rounded-md bg-primary/10 border border-primary/20 text-primary text-[11px] font-medium capitalize">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Full description */}
        <div className="flex-1 overflow-y-auto px-5 mt-4 pb-5">
          <p className="text-xs font-semibold text-foreground mb-2">Job Description</p>
          {entry.description ? (
            <div className="text-xs text-muted-foreground leading-relaxed whitespace-pre-wrap bg-background/50 rounded-lg p-3 border border-border">
              {entry.description}
            </div>
          ) : (
            <p className="text-xs text-muted-foreground italic">No description available.</p>
          )}
        </div>
      </motion.div>
    </motion.div>
  );
};

/* ── Main component ───────────────────────────────────────────────────────── */
const LiveLog = ({ logs, progress, accent = "primary", screenshot, companies, costSummary }: LiveLogProps) => {
  const logRef  = useRef<HTMLDivElement>(null);
  const imgRef  = useRef<HTMLImageElement>(null);
  const [selected,  setSelected]  = useState<CompanyEntry | null>(null);
  // Tracks whether the first frame has ever arrived so we can swap out the
  // placeholder.  This is a one-time state transition and never reverts.
  const [hasFrame, setHasFrame] = useState(false);

  useEffect(() => {
    if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight;
  }, [logs]);

  // Update the <img> src directly via the DOM ref instead of relying on React
  // reconciliation.  At ~10 fps the CDP screencaster fires this effect ten
  // times per second; bypassing React's virtual-DOM diff keeps the main thread
  // free for the log list and other UI updates.
  //
  // Why not AnimatePresence + changing key?
  //   AnimatePresence mode="wait" waits for the exit animation (200 ms) to
  //   complete before mounting the next element.  At 100 ms / frame the queue
  //   grows without bound, producing an increasingly delayed slideshow.
  useEffect(() => {
    if (!screenshot) return;
    if (!hasFrame) setHasFrame(true);            // single state flip, fires once
    if (imgRef.current) {
      imgRef.current.src = `data:image/jpeg;base64,${screenshot}`;
    }
  }, [screenshot]);  // eslint-disable-line react-hooks/exhaustive-deps
  // (hasFrame intentionally omitted — we only need the transition once)

  const progressPct = progress.total > 0 ? (progress.current / progress.total) * 100 : 0;

  return (
    <>
    <div className="glass-card p-4 sm:p-5 flex flex-col gap-4">

      {/* ── Header + progress ─────────────────────────────────────── */}
      <div>
        <h3 className="text-sm font-semibold text-foreground mb-3">Live Application Log</h3>
        <div className="flex justify-between text-xs text-muted-foreground mb-1">
          <span>{progress.current} / {progress.total} submitted</span>
          <span>{Math.round(progressPct)}%</span>
        </div>
        <div className="h-1.5 rounded-full bg-muted overflow-hidden">
          <motion.div
            className={`h-full rounded-full ${accent === "orange" ? "bg-orange-500" : "gradient-blue-purple"}`}
            initial={{ width: 0 }}
            animate={{ width: `${progressPct}%` }}
            transition={{ duration: 0.5 }}
          />
        </div>
      </div>

      {/* ── Browser preview ───────────────────────────────────────── */}
      <div className="rounded-xl overflow-hidden border border-border bg-background/60">
        {/* Fake browser chrome bar */}
        <div className="flex items-center gap-2 px-3 py-2 bg-muted/60 border-b border-border">
          <div className="flex gap-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500/70"    />
            <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/70" />
            <span className="w-2.5 h-2.5 rounded-full bg-green-500/70"  />
          </div>
          <Monitor className="w-3.5 h-3.5 text-muted-foreground ml-1" />
          <span className="text-xs text-muted-foreground">Live Browser Preview</span>
        </div>

        {/*
          Frame rendering strategy
          ────────────────────────
          The CDP screencaster delivers frames at ~10 fps.  We keep a single
          <img> element mounted at all times and update its src attribute
          directly via a ref (see the useEffect above).  This avoids React
          reconciliation on every frame and, crucially, sidesteps the
          AnimatePresence "mode=wait" trap where a 200 ms exit animation
          longer than the 100 ms frame interval would produce an ever-growing
          render queue.

          The placeholder fades in once via Framer Motion, then transitions
          to the live feed the moment the first frame arrives (hasFrame flip).
          Subsequent frames bypass React entirely.
        */}
        <div className="relative w-full" style={{ minHeight: "180px" }}>
          {/* Live feed — always mounted; invisible until the first frame */}
          <img
            ref={imgRef}
            alt="Live browser preview"
            className={`w-full block transition-opacity duration-300 ${
              hasFrame ? "opacity-100" : "pointer-events-none opacity-0 absolute inset-0"
            }`}
          />

          {/* Placeholder — rendered only before the first frame arrives */}
          <AnimatePresence>
            {!hasFrame && (
              <motion.div
                key="placeholder"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.3 }}
                className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-muted-foreground/40"
              >
                <Monitor className="w-10 h-10" />
                <p className="text-xs">Browser will appear here once automation starts</p>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {/* ── Log terminal ──────────────────────────────────────────── */}
      <div
        ref={logRef}
        className="bg-background/50 rounded-lg p-3 font-mono text-xs leading-relaxed overflow-y-auto"
        style={{ maxHeight: "220px", minHeight: "80px" }}
      >
        {logs.length === 0 ? (
          <p className="text-muted-foreground/40 italic">Waiting to start...</p>
        ) : (
          <AnimatePresence initial={false}>
            {logs.map((log) => (
              <motion.div
                key={log.id}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25 }}
                className={`mb-0.5 ${typeColors[log.type] ?? "text-foreground"}`}
              >
                <span className="text-muted-foreground/35 mr-2">
                  {log.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}
                </span>
                {log.message}
              </motion.div>
            ))}
          </AnimatePresence>
        )}
      </div>

      {/* ── Companies table ───────────────────────────────────────── */}
      <AnimatePresence>
        {companies.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35 }}
          >
            <h4 className="text-xs font-semibold text-foreground mb-2">
              Company Results ({companies.length})
            </h4>
            <div className="rounded-lg border border-border overflow-hidden">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-muted/50 border-b border-border">
                    <th className="px-3 py-2 text-left text-muted-foreground font-medium w-6">#</th>
                    <th className="px-3 py-2 text-left text-muted-foreground font-medium">Role & Company</th>
                    <th className="px-3 py-2 text-left text-muted-foreground font-medium w-20">Status</th>
                    <th className="px-3 py-2 text-left text-muted-foreground font-medium">AI Reason</th>
                  </tr>
                </thead>
                <tbody>
                  <AnimatePresence initial={false}>
                    {companies.map((c) => (
                      <motion.tr
                        key={c.index}
                        initial={{ opacity: 0, backgroundColor: "rgba(99,102,241,0.12)" }}
                        animate={{ opacity: 1, backgroundColor: "rgba(0,0,0,0)" }}
                        transition={{ duration: 0.5 }}
                        className="border-b border-border/50 last:border-0 hover:bg-muted/20 transition-colors align-top cursor-pointer"
                        onClick={() => setSelected(c)}
                      >
                        <td className="px-3 py-2.5 text-muted-foreground">{c.index}</td>
                        <td className="px-3 py-2.5">
                          <div className="font-medium text-foreground">{c.title}</div>
                          <div className="text-muted-foreground">{c.company}</div>
                          {c.location && (
                            <div className="text-muted-foreground/60 text-[10px] mt-0.5">{c.location}</div>
                          )}
                        </td>
                        <td className="px-3 py-2.5">
                          <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full border text-[10px] font-medium whitespace-nowrap ${statusBadge[c.status]}`}>
                            {statusIcon(c.status)}
                            {statusLabel[c.status]}
                          </span>
                        </td>
                        <td className="px-3 py-2.5 text-muted-foreground leading-relaxed">
                          {c.reason}
                        </td>
                      </motion.tr>
                    ))}
                  </AnimatePresence>
                </tbody>
              </table>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── GPT Cost Summary ──────────────────────────────────── */}
      <AnimatePresence>
        {costSummary && (
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4 }}
            className="rounded-xl border border-green-500/30 bg-green-500/8 p-4"
          >
            <div className="flex items-center gap-2 mb-3">
              <Coins className="w-4 h-4 text-green-400" />
              <h4 className="text-xs font-semibold text-green-400">GPT Usage &amp; Cost</h4>
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              {[
                { label: "Input tokens",  value: costSummary.input_tokens.toLocaleString() },
                { label: "Output tokens", value: costSummary.output_tokens.toLocaleString() },
                { label: "Total tokens",  value: costSummary.total_tokens.toLocaleString() },
                { label: "Total cost",    value: `$${costSummary.cost_usd.toFixed(4)}` },
              ].map(({ label, value }) => (
                <div key={label} className="rounded-lg bg-background/50 border border-border px-3 py-2 text-center">
                  <p className="text-[10px] text-muted-foreground mb-0.5">{label}</p>
                  <p className="text-sm font-bold text-foreground">{value}</p>
                </div>
              ))}
            </div>
            <p className="text-[10px] text-muted-foreground/60 mt-2 text-right">
              Pricing: gpt-4o-mini — $0.15 / 1M input · $0.60 / 1M output
            </p>
          </motion.div>
        )}
      </AnimatePresence>

    </div>

    {/* ── Job detail modal ────────────────────────────────────── */}
    <AnimatePresence>
      {selected && <JobModal entry={selected} onClose={() => setSelected(null)} />}
    </AnimatePresence>
    </>
  );
};

export default LiveLog;
