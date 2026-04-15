import { useState } from "react";
import { motion } from "framer-motion";
import { Loader2, CheckCircle, Lock } from "lucide-react";
import GlowButton from "./GlowButton";
import LiveLog from "./LiveLog";
import { startAutomation, LogEntry, ProfileData, CompanyEntry, CostSummary } from "@/lib/mockApi";

interface PlatformSectionProps {
  platform:    "linkedin" | "naukri";
  profileData: ProfileData;
}

const experienceLevels = ["Internship", "Entry Level", "Associate", "Mid-Senior", "Director"];
const jobTypes = ["Full-time", "Part-time", "Contract", "Remote"];
const countOptions = [5, 10, 20, 30, 50];

const PlatformSection = ({ platform, profileData }: PlatformSectionProps) => {
  const isLinkedin = platform === "linkedin";
  const accentColor = isLinkedin ? "primary" : "orange";

  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginStatus, setLoginStatus] = useState<"idle" | "opening" | "logging" | "connected" | "error">("idle");
  const [loginError, setLoginError] = useState<string>("");

  const [role, setRole] = useState("Data Scientist");
  const [selectedLevels, setSelectedLevels] = useState<string[]>(["Mid-Senior"]);
  const [locationFilter, setLocationFilter] = useState("India");
  const [selectedJobTypes, setSelectedJobTypes] = useState<string[]>(["Full-time"]);
  const [applyType, setApplyType] = useState<"easy_apply" | "external">("easy_apply");  // external locked for now
  const [count, setCount] = useState(10);

  const [logs, setLogs]           = useState<LogEntry[]>([]);
  const [progress, setProgress]   = useState({ current: 0, total: 0 });
  const [isRunning, setIsRunning] = useState(false);
  const [screenshot, setScreenshot] = useState<string | null>(null);
  const [companies, setCompanies]   = useState<CompanyEntry[]>([]);
  const [costSummary, setCostSummary] = useState<CostSummary | null>(null);

  const toggleChip = (arr: string[], val: string, setter: (v: string[]) => void) => {
    setter(arr.includes(val) ? arr.filter((x) => x !== val) : [...arr, val]);
  };

  const handleLogin = async () => {
    if (!loginEmail || !loginPassword) {
      setLoginError("Please enter both email and password.");
      setLoginStatus("error");
      return;
    }

    setLoginError("");
    setLoginStatus("opening");

    try {
      setLoginStatus("logging");
      const token = localStorage.getItem("auth_token");
      const res = await fetch(`${import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"}/api/verify-credentials`, {
        method: "POST",
        headers: {
          "Content-Type":  "application/json",
          ...(token ? { "Authorization": `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          email: loginEmail,
          password: loginPassword,
          platform: platform,
        }),
      });

      if (res.ok) {
        setLoginStatus("connected");
      } else {
        const data = await res.json().catch(() => ({ detail: "Unknown error" }));
        const msg: string = data.detail ?? "Login failed.";
        setLoginError(msg);
        setLoginStatus("error");
      }
    } catch {
      setLoginError("Cannot reach the server. Make sure the backend is running.");
      setLoginStatus("error");
    }
  };

  const handleStart = async () => {
    setIsRunning(true);
    setLogs([]);
    setCompanies([]);
    setScreenshot(null);
    setCostSummary(null);
    setProgress({ current: 0, total: count });
    await startAutomation(
      {
        platform,
        credentials: { email: loginEmail, password: loginPassword },
        filters: {
          role:            role || "Data Scientist",
          experienceLevel: selectedLevels,
          location:        locationFilter || "India",
          jobType:         selectedJobTypes,
          applyType:       isLinkedin ? applyType : "external",
        },
        count,
        profile: profileData,
      },
      (log)           => setLogs((prev) => [...prev, log]),
      (current, total)=> setProgress({ current, total }),
      (b64)           => setScreenshot(b64),
      (c)             => setCompanies((prev) => [...prev, c]),
      (cost)          => setCostSummary(cost)
    );
    setIsRunning(false);
  };

  const inputCls = "w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition text-sm";

  const chipBase = "px-3 py-1.5 rounded-full text-xs font-medium border cursor-pointer transition-all duration-200 select-none";

  return (
    <motion.div
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: "auto", opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      transition={{ duration: 0.4 }}
      className="overflow-hidden"
    >
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
        {/* Left Panel */}
        <div className="space-y-5">
          {/* Login Box */}
          <div className="glass-card p-5">
            <h3 className="text-sm font-semibold text-foreground mb-3">
              {isLinkedin ? "LinkedIn" : "Naukri"} Login
            </h3>
            <input
              value={loginEmail}
              onChange={(e) => setLoginEmail(e.target.value)}
              className={`${inputCls} mb-3`}
              placeholder="Email"
            />
            <input
              type="password"
              value={loginPassword}
              onChange={(e) => setLoginPassword(e.target.value)}
              className={`${inputCls} mb-3`}
              placeholder="Password"
            />
            <GlowButton
              variant={isLinkedin ? "primary" : "orange"}
              onClick={loginStatus === "error" || loginStatus === "idle" ? handleLogin : undefined}
              disabled={loginStatus === "connected" || loginStatus === "opening" || loginStatus === "logging"}
              className="w-full text-sm py-2"
            >
              {(loginStatus === "idle" || loginStatus === "error") && "Connect"}
              {loginStatus === "opening" && (
                <span className="flex items-center gap-2"><Loader2 className="w-3 h-3 animate-spin" /> Opening browser...</span>
              )}
              {loginStatus === "logging" && (
                <span className="flex items-center gap-2"><Loader2 className="w-3 h-3 animate-spin" /> Verifying credentials...</span>
              )}
              {loginStatus === "connected" && (
                <span className="flex items-center gap-2"><CheckCircle className="w-3 h-3" /> Connected ✓</span>
              )}
            </GlowButton>

            {loginStatus === "error" && loginError && (
              <p className="mt-2 text-xs text-red-400 flex items-start gap-1">
                <span className="mt-0.5">⚠</span>
                <span>{loginError}</span>
              </p>
            )}
          </div>

          {/* Filters */}
          <div className="glass-card p-5">
            <h3 className="text-sm font-semibold text-foreground mb-3">Job Filters</h3>
            <div className="mb-3">
              <label className="block text-xs text-muted-foreground mb-1">Role / Job Title</label>
              <input value={role} onChange={(e) => setRole(e.target.value)} className={inputCls} placeholder="Data Scientist" />
            </div>
            <div className="mb-3">
              <label className="block text-xs text-muted-foreground mb-1">Experience Level</label>
              <div className="flex flex-wrap gap-2">
                {experienceLevels.map((l) => (
                  <span
                    key={l}
                    onClick={() => toggleChip(selectedLevels, l, setSelectedLevels)}
                    className={`${chipBase} ${
                      selectedLevels.includes(l)
                        ? isLinkedin ? "border-primary bg-primary/20 text-primary" : "border-neon-orange bg-neon-orange/20 text-neon-orange"
                        : "border-border text-muted-foreground hover:border-muted-foreground"
                    }`}
                  >
                    {l}
                  </span>
                ))}
              </div>
            </div>
            <div className="mb-3">
              <label className="block text-xs text-muted-foreground mb-1">Location</label>
              <input value={locationFilter} onChange={(e) => setLocationFilter(e.target.value)} className={inputCls} placeholder="India" />
            </div>
            <div>
              <label className="block text-xs text-muted-foreground mb-1">Job Type</label>
              <div className="flex flex-wrap gap-2">
                {jobTypes.map((t) => (
                  <span
                    key={t}
                    onClick={() => toggleChip(selectedJobTypes, t, setSelectedJobTypes)}
                    className={`${chipBase} ${
                      selectedJobTypes.includes(t)
                        ? isLinkedin ? "border-primary bg-primary/20 text-primary" : "border-neon-orange bg-neon-orange/20 text-neon-orange"
                        : "border-border text-muted-foreground hover:border-muted-foreground"
                    }`}
                  >
                    {t}
                  </span>
                ))}
              </div>
            </div>

            {isLinkedin && (
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Apply Type</label>
                <div className="flex gap-2">
                  {/* Easy Apply — fully enabled */}
                  <span
                    onClick={() => setApplyType("easy_apply")}
                    className={`${chipBase} ${
                      applyType === "easy_apply"
                        ? "border-primary bg-primary/20 text-primary"
                        : "border-border text-muted-foreground hover:border-muted-foreground"
                    }`}
                  >
                    Easy Apply
                  </span>

                  {/* External Website — locked / coming soon */}
                  <span
                    className={`${chipBase} border-border text-muted-foreground/40 cursor-not-allowed opacity-50 flex items-center gap-1.5`}
                    title="External Website apply is coming soon"
                  >
                    <Lock className="w-3 h-3" />
                    External Website
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1">
                  Only LinkedIn Easy Apply jobs are supported right now.
                </p>
              </div>
            )}
          </div>

          {/* Count */}
          <div className="glass-card p-5">
            <h3 className="text-sm font-semibold text-foreground mb-3">How many companies to apply?</h3>
            <div className="flex flex-wrap gap-3">
              {countOptions.map((n) => {
                const locked = n === 30 || n === 50;
                if (locked) {
                  return (
                    <div
                      key={n}
                      title="Coming soon"
                      className="relative w-12 h-12 rounded-xl flex items-center justify-center font-bold text-sm cursor-not-allowed opacity-40 bg-muted text-muted-foreground select-none"
                    >
                      {n}
                      <Lock className="absolute -top-1.5 -right-1.5 w-3 h-3 text-muted-foreground" />
                    </div>
                  );
                }
                return (
                  <motion.span
                    key={n}
                    whileHover={{ scale: 1.1 }}
                    whileTap={{ scale: 0.95 }}
                    onClick={() => setCount(n)}
                    className={`w-12 h-12 rounded-xl flex items-center justify-center font-bold text-sm cursor-pointer transition-all duration-200 ${
                      count === n
                        ? isLinkedin ? "gradient-blue-purple text-foreground glow-blue" : "bg-neon-orange text-foreground glow-orange"
                        : "bg-muted text-muted-foreground hover:bg-muted/80"
                    }`}
                  >
                    {n}
                  </motion.span>
                );
              })}
            </div>
          </div>

          {/* Start Button */}
          <GlowButton
            variant={isLinkedin ? "primary" : "orange"}
            onClick={handleStart}
            disabled={loginStatus !== "connected" || isRunning}
            loading={isRunning}
            pulse
            className="w-full text-base py-4"
          >
            🚀 Start Applying
          </GlowButton>
        </div>

        {/* Right Panel */}
        <LiveLog
          logs={logs}
          progress={progress}
          accent={isLinkedin ? "primary" : "orange"}
          screenshot={screenshot}
          companies={companies}
          costSummary={costSummary}
        />
      </div>
    </motion.div>
  );
};

export default PlatformSection;
