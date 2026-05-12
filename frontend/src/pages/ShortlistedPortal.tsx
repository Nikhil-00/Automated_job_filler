import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { Star, MapPin, Briefcase, Loader2, IndianRupee } from "lucide-react";
import { getShortlistedJobs, ShortlistedJob } from "@/lib/mockApi";
import Navbar             from "@/components/Navbar";
import AnimatedBackground from "@/components/AnimatedBackground";
import { getMe, logout }  from "@/lib/auth";

type DashUser = { first_name: string; last_name: string; email: string };

function fmtDate(iso: string) {
  return new Date(iso).toLocaleString("en-IN", {
    day: "2-digit", month: "short", year: "numeric",
  });
}

function fmtSalary(min: number | null, max: number | null, currency: string | null) {
  if (!min && !max) return null;
  const sym = currency === "INR" ? "₹" : (currency ?? "");
  const fmt = (n: number) => n >= 100000 ? `${(n / 100000).toFixed(1)}L` : `${n.toLocaleString()}`;
  if (min && max) return `${sym}${fmt(min)} – ${sym}${fmt(max)}`;
  if (max) return `Up to ${sym}${fmt(max)}`;
  return `${sym}${fmt(min!)}+`;
}

const ShortlistedPortal = () => {
  const [jobs,    setJobs]    = useState<ShortlistedJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [error,   setError]   = useState("");
  const [user,    setUser]    = useState<DashUser | null>(null);

  useEffect(() => {
    getShortlistedJobs()
      .then(setJobs)
      .catch(() => setError("Could not load shortlisted jobs."))
      .finally(() => setLoading(false));
    getMe().then(setUser).catch(() => {});
  }, []);

  if (loading) {
    return (
      <div className="min-h-screen">
        <AnimatedBackground />
        <Navbar currentStep={2} user={user} onLogout={logout} showAppNav />
        <div className="flex items-center justify-center pt-40">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen">
      <AnimatedBackground />
      <Navbar currentStep={2} user={user} onLogout={logout} showAppNav />

      <main className="pt-[120px] sm:pt-[80px] lg:pt-[88px] pb-12 px-4 sm:px-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.35 }}
          className="w-full max-w-4xl mx-auto"
        >
          <div className="flex items-center gap-3 mb-2">
            <div className="w-9 h-9 rounded-lg bg-emerald-50 border border-emerald-200 flex items-center justify-center">
              <Star className="w-4 h-4 text-emerald-700" />
            </div>
            <div>
              <h2 className="text-2xl font-bold text-gradient">Shortlisted</h2>
              <p className="text-muted-foreground text-sm">Jobs where companies have shortlisted your application.</p>
            </div>
          </div>

          {/* Stats */}
          <div className="mt-5 mb-6 glass-card p-4 flex items-center gap-6">
            <div className="text-center">
              <p className="text-2xl font-bold text-emerald-700">{jobs.length}</p>
              <p className="text-xs text-muted-foreground mt-0.5">Shortlisted</p>
            </div>
            <div className="w-px h-10 bg-border" />
            <p className="text-sm text-muted-foreground">
              {jobs.length === 0
                ? "No shortlists yet — keep applying through the World Wide Jobs board."
                : "Congratulations! Companies have expressed interest in your profile."}
            </p>
          </div>

          {/* Error */}
          {error && <p className="text-red-400 text-sm text-center py-8">{error}</p>}

          {/* Empty state */}
          {!error && jobs.length === 0 && (
            <div className="glass-card p-12 text-center">
              <Star className="w-10 h-10 text-muted-foreground mx-auto mb-3" />
              <p className="text-muted-foreground text-sm">
                No shortlisted jobs yet. Apply to postings on the dashboard to get started.
              </p>
            </div>
          )}

          {/* Jobs grid */}
          <div className="space-y-3">
            {jobs.map((job, i) => {
              const salary = fmtSalary(job.salary_min, job.salary_max, job.salary_currency);
              return (
                <motion.div
                  key={job.application_id}
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: i < 15 ? i * 0.04 : 0 }}
                  className="glass-card p-5 space-y-3"
                >
                  {/* Header */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <h3 className="text-base font-semibold text-foreground truncate">{job.title}</h3>
                      <p className="text-sm text-muted-foreground">{job.company}</p>
                    </div>
                    <div className="shrink-0 text-right">
                      <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-medium border bg-green-500/15 text-emerald-700 border-green-500/30">
                        <Star className="w-3 h-3" />
                        Shortlisted
                      </span>
                      <p className="text-xs text-muted-foreground mt-1">{fmtDate(job.applied_at)}</p>
                    </div>
                  </div>

                  {/* Meta */}
                  <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
                    {job.location && (
                      <span className="flex items-center gap-1">
                        <MapPin className="w-3 h-3" />{job.location}
                      </span>
                    )}
                    {job.work_mode && (
                      <span className="flex items-center gap-1">
                        <Briefcase className="w-3 h-3" />{job.work_mode}
                      </span>
                    )}
                    {salary && (
                      <span className="flex items-center gap-1">
                        <IndianRupee className="w-3 h-3" />{salary}
                      </span>
                    )}
                    {job.ai_match_score != null && (
                      <span className="text-primary font-medium">
                        {job.ai_match_score}% match
                      </span>
                    )}
                  </div>

                  {/* Skills */}
                  {job.skills.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {job.skills.slice(0, 8).map((s) => (
                        <span
                          key={s}
                          className="px-2 py-0.5 rounded-full text-xs bg-primary/10 border border-primary/20 text-primary"
                        >
                          {s}
                        </span>
                      ))}
                      {job.skills.length > 8 && (
                        <span className="px-2 py-0.5 rounded-full text-xs text-muted-foreground">
                          +{job.skills.length - 8} more
                        </span>
                      )}
                    </div>
                  )}
                </motion.div>
              );
            })}
          </div>
        </motion.div>
      </main>
    </div>
  );
};

export default ShortlistedPortal;
