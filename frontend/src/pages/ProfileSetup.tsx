import { useEffect, useState } from "react";
import { useNavigate }         from "react-router-dom";
import { motion }              from "framer-motion";
import { CheckCircle, Loader2 } from "lucide-react";

import AnimatedBackground from "@/components/AnimatedBackground";
import Navbar             from "@/components/Navbar";
import GlowButton         from "@/components/GlowButton";
import { getMe, logout }                          from "@/lib/auth";
import { getProfileData, updateProfileData }      from "@/lib/mockApi";

const NOTICE_PERIODS = ["Immediate", "15 days", "30 days", "60 days", "90 days"];

type User = { first_name: string; last_name: string; email: string };

const ProfileSetup = () => {
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [saving,  setSaving]  = useState(false);
  const [saved,   setSaved]   = useState(false);
  const [error,   setError]   = useState("");
  const [user,    setUser]    = useState<User | null>(null);

  // form fields
  const [currentCtc,   setCurrentCtc]   = useState("");
  const [expectedCtc,  setExpectedCtc]  = useState("");
  const [location,     setLocation]     = useState("");
  const [jobTitle,     setJobTitle]     = useState("");
  const [noticePeriod, setNoticePeriod] = useState("30 days");
  const [experience,   setExperience]   = useState("");
  const [linkedin,     setLinkedin]     = useState("");
  const [github,       setGithub]       = useState("");

  useEffect(() => {
    (async () => {
      try {
        const me = await getMe();
        setUser({ first_name: me.first_name, last_name: me.last_name, email: me.email });

        // Pre-fill from whatever profile.json already has (back-filled by CV builder)
        try {
          const p = await getProfileData();
          if (p.current_salary)      setCurrentCtc(String(p.current_salary));
          if (p.expected_salary)     setExpectedCtc(String(p.expected_salary));
          if (p.current_city)        setLocation(String(p.current_city));
          if (p.current_job_title)   setJobTitle(String(p.current_job_title));
          if (p.years_of_experience) setExperience(String(p.years_of_experience));
          if (p.linkedin_url)        setLinkedin(String(p.linkedin_url));
          if (p.github_url)          setGithub(String(p.github_url));
          if (p.notice_period) {
            const raw = String(p.notice_period).trim();
            const matched =
              NOTICE_PERIODS.find(n => n === raw) ??
              NOTICE_PERIODS.find(n => n.replace(" days", "") === raw);
            if (matched) setNoticePeriod(matched);
          }
        } catch {
          // profile.json not yet written — user fills manually
        }
      } catch {
        logout();
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const canSave = !!(currentCtc && expectedCtc && location && jobTitle && experience);

  const handleSave = async () => {
    setSaving(true);
    setError("");
    try {
      await updateProfileData({
        current_salary:      currentCtc  || null,
        expected_salary:     expectedCtc || null,
        current_city:        location,
        current_job_title:   jobTitle,
        notice_period:       noticePeriod.replace(" days", ""),
        years_of_experience: experience,
        linkedin_url:        linkedin || null,
        github_url:          github   || null,
      });
      setSaved(true);
      setTimeout(() => navigate("/dashboard"), 1500);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Save failed. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const cls =
    "w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground " +
    "placeholder:text-muted-foreground focus:outline-none focus:ring-2 " +
    "focus:ring-primary/50 transition";

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <AnimatedBackground />
        <Loader2 className="w-10 h-10 text-primary animate-spin" />
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <AnimatedBackground />

      <Navbar currentStep={1} user={user} onLogout={logout} />

      <main className="pt-24 pb-12 px-4 sm:px-6">
        <motion.div
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.4 }}
          className="w-full max-w-xl mx-auto"
        >
          <div className="glass-card p-6 sm:p-8 glow-purple rounded-2xl">
            <h2 className="text-2xl font-bold text-gradient mb-1">Complete Your Profile</h2>
            <p className="text-muted-foreground text-sm mb-6">
              Add your job preferences — these are used when applying on your behalf.
            </p>

            {/* CTC row */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-sm text-muted-foreground mb-1">
                  Current CTC <span className="text-xs opacity-60">(₹/year)</span>
                </label>
                <input
                  type="number"
                  value={currentCtc}
                  onChange={e => setCurrentCtc(e.target.value)}
                  className={cls}
                  placeholder="800000"
                />
              </div>
              <div>
                <label className="block text-sm text-muted-foreground mb-1">
                  Expected CTC <span className="text-xs opacity-60">(₹/year)</span>
                </label>
                <input
                  type="number"
                  value={expectedCtc}
                  onChange={e => setExpectedCtc(e.target.value)}
                  className={cls}
                  placeholder="1200000"
                />
              </div>
            </div>

            {/* Location */}
            <div className="mb-4">
              <label className="block text-sm text-muted-foreground mb-1">Current Location</label>
              <input
                value={location}
                onChange={e => setLocation(e.target.value)}
                className={cls}
                placeholder="Delhi, India"
              />
            </div>

            {/* Job title */}
            <div className="mb-4">
              <label className="block text-sm text-muted-foreground mb-1">
                Current / Target Job Title
                <span className="text-primary text-xs ml-1">(pre-filled from your CV)</span>
              </label>
              <input
                value={jobTitle}
                onChange={e => setJobTitle(e.target.value)}
                className={cls}
                placeholder="e.g. Data Scientist"
              />
            </div>

            {/* Notice + Experience */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-4">
              <div>
                <label className="block text-sm text-muted-foreground mb-1">Notice Period</label>
                <select
                  value={noticePeriod}
                  onChange={e => setNoticePeriod(e.target.value)}
                  className={cls}
                >
                  {NOTICE_PERIODS.map(p => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-sm text-muted-foreground mb-1">Years of Experience</label>
                <input
                  type="number"
                  value={experience}
                  onChange={e => setExperience(e.target.value)}
                  className={cls}
                  placeholder="e.g. 2"
                />
              </div>
            </div>

            {/* LinkedIn */}
            <div className="mb-4">
              <label className="block text-sm text-muted-foreground mb-1">
                LinkedIn URL <span className="text-xs opacity-60">(optional)</span>
              </label>
              <input
                value={linkedin}
                onChange={e => setLinkedin(e.target.value)}
                className={cls}
                placeholder="https://linkedin.com/in/yourname"
              />
            </div>

            {/* GitHub */}
            <div className="mb-6">
              <label className="block text-sm text-muted-foreground mb-1">
                GitHub URL <span className="text-xs opacity-60">(optional)</span>
              </label>
              <input
                value={github}
                onChange={e => setGithub(e.target.value)}
                className={cls}
                placeholder="https://github.com/yourname"
              />
            </div>

            {/* Error */}
            {error && (
              <motion.p
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="text-sm text-red-400 bg-red-500/10 border border-red-500/20
                           rounded-lg px-3 py-2 mb-4"
              >
                {error}
              </motion.p>
            )}

            {/* Success / Save button */}
            {saved ? (
              <motion.div
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                className="flex items-center gap-2 justify-center text-green-400
                           bg-green-500/10 border border-green-500/20 rounded-lg px-4 py-3"
              >
                <CheckCircle className="w-4 h-4 flex-shrink-0" />
                Profile saved! Taking you to your dashboard…
              </motion.div>
            ) : (
              <GlowButton
                onClick={handleSave}
                disabled={!canSave || saving}
                className="w-full"
              >
                {saving
                  ? <span className="flex items-center justify-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" /> Saving…
                    </span>
                  : "Save & Go to Dashboard →"
                }
              </GlowButton>
            )}
          </div>
        </motion.div>
      </main>
    </div>
  );
};

export default ProfileSetup;
