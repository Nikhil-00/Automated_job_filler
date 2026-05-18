import { useEffect, useState } from "react";
import { useNavigate }         from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle, Loader2, Plus, Sparkles, ToggleLeft, ToggleRight, X } from "lucide-react";

import Navbar             from "@/components/Navbar";
import AnimatedBackground from "@/components/AnimatedBackground";
import WorldWideJobs      from "@/components/WorldWideJobs";
import { getToken }       from "@/lib/auth";

import { getMe, logout }                from "@/lib/auth";
import { ProfileData, getProfileData }  from "@/lib/mockApi";
import { CVData, emptyCVData, getCVBuilder }               from "@/lib/cvBuilderApi";

// ─── Profile completion (mirrors Profile.tsx calcCompletion) ─────────────────

function computeCompletion(cv: CVData, profile: ProfileData | null): number {
  let s = 0;
  if (cv.contact?.name)                          s += 10;
  if (cv.contact?.phone)                         s += 5;
  if (cv.contact?.email)                         s += 5;
  if (cv.contact?.location)                      s += 5;
  if (profile?.currentCtc)                       s += 10;
  if (profile?.expectedCtc)                      s += 10;
  if (cv.summary)                                s += 10;
  if ((cv.work_experience?.length ?? 0) > 0)     s += 20;
  if ((cv.education?.length ?? 0) > 0)           s += 10;
  if ((cv.skills?.technical?.length ?? 0) > 0)   s += 10;
  if (cv.contact?.linkedin || cv.contact?.github) s += 5;
  return Math.min(s, 100);
}

// ─── Build a ProfileData object from the saved profile.json ──────────────────

function buildProfileData(
  user:    { first_name: string; last_name: string; email: string },
  profile: Record<string, unknown>,
): ProfileData {
  const normaliseNotice = (raw: unknown): string => {
    const s = String(raw ?? "30").replace(" days", "").trim();
    if (s === "0" || s.toLowerCase() === "immediate") return "Immediate";
    const n = parseInt(s, 10);
    if (n === 15) return "15 days";
    if (n === 60) return "60 days";
    if (n === 90) return "90 days";
    return "30 days";
  };

  return {
    firstName:    user.first_name,
    lastName:     user.last_name,
    phone:        String(profile.phone              ?? ""),
    email:        String(profile.email              ?? user.email),
    currentCtc:   String(profile.current_salary     ?? ""),
    expectedCtc:  String(profile.expected_salary    ?? ""),
    location:     String(profile.current_city       ?? ""),
    jobTitle:     String(profile.current_job_title  ?? ""),
    noticePeriod: normaliseNotice(profile.notice_period),
    experience:   String(profile.years_of_experience ?? "1"),
    linkedin:     String(profile.linkedin_url        ?? ""),
    github:       String(profile.github_url          ?? ""),
  };
}

// ─── Dashboard ────────────────────────────────────────────────────────────────

type DashboardUser = { first_name: string; last_name: string; email: string };

const Dashboard = () => {
  const navigate = useNavigate();

  const [loading,     setLoading]     = useState(true);
  const [currentUser, setCurrentUser] = useState<DashboardUser | null>(null);
  const [profileData, setProfileData] = useState<ProfileData | null>(null);
  const [cvData,      setCvData]      = useState<CVData>(emptyCVData());


  useEffect(() => {
    (async () => {
      try {
        const me = await getMe();
        const user: DashboardUser = {
          first_name: me.first_name,
          last_name:  me.last_name,
          email:      me.email,
        };
        setCurrentUser(user);

        const [profResult, cvResult] = await Promise.allSettled([
          getProfileData(),
          getCVBuilder(),
        ]);

        let profile: ProfileData | null = null;
        if (profResult.status === "fulfilled") {
          profile = buildProfileData(user, profResult.value);
          setProfileData(profile);
        }
        if (cvResult.status === "fulfilled") {
          setCvData(cvResult.value);
        }
      } catch {
        logout();
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <AnimatedBackground />
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="flex flex-col items-center gap-4"
        >
          <Loader2 className="w-10 h-10 text-primary animate-spin" />
          <p className="text-muted-foreground text-sm">Loading your workspace…</p>
        </motion.div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <AnimatedBackground />

      <Navbar
        currentStep={2}
        user={currentUser}
        onLogout={logout}
        showAppNav
      />

      <main className="pt-[72px] sm:pt-[80px] lg:pt-[88px] pb-12 px-4 sm:px-6">
        <YourJobOnUs expectedCtc={profileData?.expectedCtc ?? ""} />
        <WorldWideJobs
          profileReady={
            computeCompletion(cvData, profileData) >= 70 &&
            !!profileData?.currentCtc &&
            !!profileData?.expectedCtc
          }
        />
      </main>
    </div>
  );
};

// ── Career Autopilot ────────────────────────────────────────────────────────────

const API: string = import.meta.env.VITE_API_URL ?? "";

function YourJobOnUs({ expectedCtc }: { expectedCtc: string }) {
  const [expanded,    setExpanded]    = useState(false);
  const [isActive,    setIsActive]    = useState(false);
  const [roles,       setRoles]       = useState<string[]>(["", "", ""]);
  const [ctcMax,      setCtcMax]      = useState(expectedCtc);
  const [loading,     setLoading]     = useState(true);
  const [saving,      setSaving]      = useState(false);
  const [message,     setMessage]     = useState("");

  const authH = { Authorization: `Bearer ${getToken() ?? ""}` };

  useEffect(() => {
    fetch(`${API}/api/jobseeker/activate`, { headers: authH })
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (!data) return;
        setIsActive(data.is_active);
        if (data.target_roles?.length) {
          const filled = [...data.target_roles, "", "", ""].slice(0, 3);
          setRoles(filled);
        }
        if (data.expected_ctc) setCtcMax(String(data.expected_ctc));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    const trimmed = roles.filter(r => r.trim());
    if (!trimmed.length) return;
    setSaving(true);
    setMessage("");
    try {
      const res = await fetch(`${API}/api/jobseeker/activate`, {
        method:  "POST",
        headers: { "Content-Type": "application/json", ...authH },
        body:    JSON.stringify({
          target_roles:     trimmed,
          expected_ctc_max: ctcMax ? parseInt(ctcMax) : null,
        }),
      });
      const data = await res.json();
      if (!res.ok) { setMessage(data.detail ?? "Failed."); return; }
      setIsActive(true);
      setMessage("Activated! You'll be matched to relevant jobs automatically.");
    } catch {
      setMessage("Something went wrong. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const handleDeactivate = async () => {
    setSaving(true);
    try {
      await fetch(`${API}/api/jobseeker/activate`, { method: "DELETE", headers: authH });
      setIsActive(false);
      setMessage("Deactivated.");
    } finally {
      setSaving(false);
    }
  };

  const setRole = (i: number, v: string) =>
    setRoles(prev => prev.map((r, idx) => idx === i ? v : r));

  if (loading) return null;

  return (
    <div className="max-w-3xl mx-auto mt-6 mb-2">
      <div
        className={`overflow-hidden rounded-2xl border transition-colors shadow-sm ${
          isActive
            ? "border-violet-400/50 bg-gradient-to-br from-violet-50 via-white to-blue-50"
            : "border-primary/20 bg-gradient-to-br from-blue-50 via-white to-violet-50"
        }`}
      >
        {/* Header row */}
        <button
          onClick={() => setExpanded(e => !e)}
          className="w-full flex items-center justify-between p-5 hover:bg-white/40 transition"
        >
          <div className="flex items-start gap-4">
            <div className="w-11 h-11 rounded-xl bg-primary/15 border border-primary/30 flex items-center justify-center shrink-0 shadow-sm">
              <Sparkles className="w-5 h-5 text-primary" />
            </div>
            <div className="text-left">
              <div className="flex items-center gap-2">
                <p className="text-base font-bold text-foreground leading-none">Career Autopilot</p>
                {isActive && (
                  <span className="text-xs px-2 py-0.5 rounded-full bg-green-500/15 border border-green-500/30 text-green-700 font-medium">
                    Active
                  </span>
                )}
              </div>
              <p className="text-sm text-muted-foreground mt-1">
                {isActive
                  ? `Matching your profile to: ${roles.filter(Boolean).join(", ")}`
                  : "AI-powered matching — your profile gets sent to companies hiring for your target role"}
              </p>
              {!isActive && (
                <p className="text-xs text-primary/80 mt-1 font-medium">
                  Set your target roles and let companies come to you — no applications needed.
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0 ml-4">
            {expanded
              ? <X className="w-4 h-4 text-muted-foreground" />
              : <Plus className="w-4 h-4 text-muted-foreground" />
            }
          </div>
        </button>

        {/* Expanded form */}
        <AnimatePresence>
          {expanded && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              className="overflow-hidden border-t border-border"
            >
              <div className="p-5 space-y-4">
                <p className="text-xs text-muted-foreground leading-relaxed">
                  Tell us up to 3 roles you're targeting. We'll use your CV and profile to automatically
                  match you with relevant job postings — no application needed.
                </p>

                {/* Target roles */}
                <div className="space-y-2">
                  <label className="text-xs text-muted-foreground font-medium">Target Job Titles (up to 3)</label>
                  {roles.map((r, i) => (
                    <div key={i} className="flex items-center gap-2">
                      <div className="w-5 h-5 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center shrink-0">
                        <span className="text-xs text-primary font-bold">{i + 1}</span>
                      </div>
                      <input
                        value={r}
                        onChange={e => setRole(i, e.target.value)}
                        placeholder={["e.g. Data Scientist", "e.g. ML Engineer", "e.g. AI Engineer"][i]}
                        className="flex-1 px-3 py-2 rounded-lg bg-input border border-border text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                      />
                    </div>
                  ))}
                </div>

                {/* Expected CTC */}
                <div>
                  <label className="text-xs text-muted-foreground font-medium block mb-1">
                    Expected CTC Max (₹ / year) — optional
                  </label>
                  <input
                    type="number"
                    value={ctcMax}
                    onChange={e => setCtcMax(e.target.value)}
                    placeholder="e.g. 1500000"
                    className="w-full px-3 py-2 rounded-lg bg-input border border-border text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50"
                  />
                  <p className="text-xs text-muted-foreground mt-1">Pre-filled from your profile. Only used to filter out jobs outside your range.</p>
                </div>

                {message && (
                  <p className={`text-xs px-3 py-2 rounded-lg border ${
                    message.includes("Activated") || message.includes("matched")
                      ? "text-green-400 bg-green-500/10 border-green-500/20"
                      : message.includes("Deactivated")
                      ? "text-muted-foreground bg-muted border-border"
                      : "text-red-400 bg-red-500/10 border-red-500/20"
                  }`}>{message}</p>
                )}

                <div className="flex items-center gap-3 pt-1">
                  {isActive ? (
                    <>
                      <button
                        onClick={handleSave}
                        disabled={saving}
                        className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-primary/15 border border-primary/40 text-primary text-sm font-semibold hover:bg-violet-500/30 transition disabled:opacity-50"
                      >
                        {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />}
                        Update Roles
                      </button>
                      <button
                        onClick={handleDeactivate}
                        disabled={saving}
                        className="flex items-center gap-1.5 px-4 py-2 rounded-lg bg-muted border border-border text-muted-foreground text-sm hover:text-foreground transition disabled:opacity-50"
                      >
                        <ToggleLeft className="w-3.5 h-3.5" /> Deactivate
                      </button>
                    </>
                  ) : (
                    <button
                      onClick={handleSave}
                      disabled={saving || !roles.some(r => r.trim())}
                      className="flex items-center gap-1.5 px-5 py-2 rounded-lg bg-primary text-white hover:bg-primary/90 text-sm font-semibold hover:opacity-90 transition disabled:opacity-50"
                    >
                      {saving
                        ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Activating…</>
                        : <><ToggleRight className="w-3.5 h-3.5" /> Activate</>
                      }
                    </button>
                  )}
                </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

export default Dashboard;
