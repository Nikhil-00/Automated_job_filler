import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Loader2 } from "lucide-react";

import Navbar             from "@/components/Navbar";
import AnimatedBackground from "@/components/AnimatedBackground";
import ConfirmDialog      from "@/components/ConfirmDialog";
import StepOnboarding     from "@/components/StepOnboarding";
import StepProfile        from "@/components/StepProfile";
import StepPlatform       from "@/components/StepPlatform";

import { getMe, logout }             from "@/lib/auth";
import { CvExtractedData, ProfileData, deleteProfileData, getProfileData, updateProfileData } from "@/lib/mockApi";

// ─── Build a ProfileData object from the saved profile.json ──────────────────

function buildProfileData(
  user:    { first_name: string; last_name: string; email: string },
  profile: Record<string, unknown>,
): ProfileData {
  // Normalise notice_period stored as "30" / "30 days" / "Immediate" etc.
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
  // null = still loading; 0/1/2 = step index
  const [step,          setStep]          = useState<number | null>(null);
  const [currentUser,   setCurrentUser]   = useState<DashboardUser | null>(null);
  const [extractedData, setExtracted]     = useState<CvExtractedData | null>(null);
  const [isExtracting,  setExtracting]    = useState(false);
  const [onboardingData, setOnboarding]   = useState<DashboardUser & { phone: string } | null>(null);
  const [profileData,   setProfileData]   = useState<ProfileData | null>(null);

  // Reset-profile dialog
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [resetting,        setResetting]        = useState(false);
  const [resetError,       setResetError]       = useState("");

  // ── On mount: determine new vs returning user ─────────────────────────────
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

        if (me.has_profile) {
          // Returning user — load saved data, skip straight to Apply
          const saved = await getProfileData();
          setProfileData(buildProfileData(user, saved));
          setStep(2);
        } else {
          // New user — start from the beginning
          setStep(0);
        }
      } catch {
        // Expired / invalid token
        logout();
      }
    })();
  }, []);

  // ── Reset handler ─────────────────────────────────────────────────────────
  const handleReset = async () => {
    setResetting(true);
    setResetError("");
    try {
      await deleteProfileData();
      // Wipe all local state and send user back to step 0
      setProfileData(null);
      setExtracted(null);
      setOnboarding(null);
      setShowResetConfirm(false);
      setStep(0);
    } catch (err: unknown) {
      setResetError(err instanceof Error ? err.message : "Reset failed. Please try again.");
    } finally {
      setResetting(false);
    }
  };

  // ── Loading screen ────────────────────────────────────────────────────────
  if (step === null) {
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

  // ── Main dashboard ────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen">
      <AnimatedBackground />

      <Navbar
        currentStep={step}
        user={currentUser}
        showReset={step === 2 && !!profileData}
        onResetClick={() => { setResetError(""); setShowResetConfirm(true); }}
        onLogout={logout}
      />

      {/* ── Confirm reset dialog ── */}
      {showResetConfirm && (
        <ConfirmDialog
          title="Reset Profile?"
          message={
            `This will permanently delete your saved CV and all profile data for ${currentUser?.email ?? "your account"}.` +
            " You'll need to re-upload your CV and fill in your details again. Your account will not be deleted."
          }
          confirmLabel="Yes, Reset Everything"
          cancelLabel="Keep My Data"
          onConfirm={handleReset}
          onCancel={() => setShowResetConfirm(false)}
          loading={resetting}
          destructive
        />
      )}

      {/* Reset error toast */}
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

      {/* ── Steps ── */}
      <main className="pt-20 pb-12 px-4 sm:px-6">
        <AnimatePresence mode="wait">

          {/* Step 0 — CV upload + basic info */}
          {step === 0 && (
            <StepOnboarding
              key="step0"
              onNext={(data) => {
                setOnboarding({
                  first_name: data.firstName,
                  last_name:  data.lastName,
                  phone:      data.phone,
                  email:      data.email,
                });
                setExtracting(true);
                data.extractionPromise
                  .then(setExtracted)
                  .catch(console.error)
                  .finally(() => setExtracting(false));
                setStep(1);
              }}
            />
          )}

          {/* Step 1 — Complete profile */}
          {step === 1 && (
            <StepProfile
              key="step1"
              extractedData={extractedData}
              isExtracting={isExtracting}
              onNext={(p) => {
                const user = currentUser!;
                setProfileData({
                  firstName:    onboardingData?.first_name ?? user.first_name,
                  lastName:     onboardingData?.last_name  ?? user.last_name,
                  phone:        onboardingData?.phone      ?? "",
                  email:        onboardingData?.email      ?? user.email,
                  currentCtc:   p.currentCtc,
                  expectedCtc:  p.expectedCtc,
                  location:     p.location,
                  jobTitle:     p.jobTitle,
                  noticePeriod: p.noticePeriod,
                  experience:   p.experience,
                  linkedin:     p.linkedin,
                  github:       p.github,
                });
                // Persist the user-entered fields back to profile.json
                updateProfileData({
                  current_salary:    p.currentCtc  || null,
                  expected_salary:   p.expectedCtc || null,
                  linkedin_url:      p.linkedin    || null,
                  github_url:        p.github      || null,
                  current_city:      p.location,
                  current_job_title: p.jobTitle,
                  notice_period:     p.noticePeriod.replace(" days", ""),
                  years_of_experience: p.experience,
                }).catch(console.error);
                setStep(2);
              }}
            />
          )}

          {/* Step 2 — Choose platform & apply */}
          {step === 2 && profileData && (
            <StepPlatform key="step2" profileData={profileData} />
          )}

        </AnimatePresence>
      </main>
    </div>
  );
};

export default Dashboard;
