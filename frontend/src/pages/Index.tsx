import { useEffect, useState } from "react";
import { useNavigate }         from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import { Loader2 } from "lucide-react";

import Navbar             from "@/components/Navbar";
import AnimatedBackground from "@/components/AnimatedBackground";
import ConfirmDialog      from "@/components/ConfirmDialog";
import StepPlatform       from "@/components/StepPlatform";
import WorldWideJobs      from "@/components/WorldWideJobs";

import { getMe, logout }                                   from "@/lib/auth";
import { ProfileData, deleteProfileData, getProfileData }  from "@/lib/mockApi";

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

  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [resetting,        setResetting]        = useState(false);
  const [resetError,       setResetError]       = useState("");

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

        try {
          const saved = await getProfileData();
          setProfileData(buildProfileData(user, saved));
        } catch {
          // profile.json missing — CV builder data exists but profile not yet back-filled
          // Show dashboard without pre-filled profile data
        }
      } catch {
        logout();
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleReset = async () => {
    setResetting(true);
    setResetError("");
    try {
      await deleteProfileData();
      navigate("/cv-builder");
    } catch (err: unknown) {
      setResetError(err instanceof Error ? err.message : "Reset failed. Please try again.");
      setResetting(false);
    }
  };

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
        showReset={!!profileData}
        onResetClick={() => { setResetError(""); setShowResetConfirm(true); }}
        onLogout={logout}
      />

      {showResetConfirm && (
        <ConfirmDialog
          title="Reset Profile?"
          message={
            `This will permanently delete your saved CV and all profile data for ${currentUser?.email ?? "your account"}.` +
            " You'll be taken to the CV Builder to start fresh. Your account will not be deleted."
          }
          confirmLabel="Yes, Reset Everything"
          cancelLabel="Keep My Data"
          onConfirm={handleReset}
          onCancel={() => setShowResetConfirm(false)}
          loading={resetting}
          destructive
        />
      )}

      <AnimatePresence>
        {resetError && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className="fixed top-20 left-1/2 -translate-x-1/2 z-50 px-4 py-2 rounded-lg
                       bg-red-500/20 border border-red-500/40 text-red-400 text-sm"
          >
            {resetError}
          </motion.div>
        )}
      </AnimatePresence>

      <main className="pt-20 pb-12 px-4 sm:px-6">
        {profileData && <StepPlatform profileData={profileData} />}
        <WorldWideJobs />
      </main>
    </div>
  );
};

export default Dashboard;
