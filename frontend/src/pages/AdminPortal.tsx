import { useEffect, useState } from "react";

const API = import.meta.env.VITE_API_URL ?? "";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Job {
  job_id:    string;
  title:     string;
  is_active: boolean;
  openings:  number;
  created_at: string | null;
}

interface Recruiter {
  id:           number;
  company_name: string;
  officer_name: string;
  email:        string;
  company_type: string;
  status:       string;
  created_at:   string | null;
  total_jobs:   number;
  active_jobs:  number;
  jobs:         Job[];
}

interface RecruiterStats {
  total_recruiters: number;
  recruiters:       Recruiter[];
}

interface JobseekerStats {
  total_candidates: number;
  with_profile:     number;
  autopilot_on:     number;
  autopilot_off:    number;
}

// ── Token helpers (sessionStorage — gone on tab close) ────────────────────────

const TOKEN_KEY = "admin_token";
const getAdminToken  = () => sessionStorage.getItem(TOKEN_KEY);
const setAdminToken  = (t: string) => sessionStorage.setItem(TOKEN_KEY, t);
const clearAdminToken = () => sessionStorage.removeItem(TOKEN_KEY);
const authHeader = () => ({ Authorization: `Bearer ${getAdminToken()}` });

// ── API calls ─────────────────────────────────────────────────────────────────

async function apiLogin(email: string, password: string): Promise<string> {
  const res = await fetch(`${API}/api/admin/login`, {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({ email, password }),
  });
  if (!res.ok) throw new Error("Invalid credentials.");
  const data = await res.json();
  return data.token as string;
}

async function fetchRecruiters(): Promise<RecruiterStats> {
  const res = await fetch(`${API}/api/admin/recruiters`, { headers: authHeader() });
  if (!res.ok) throw new Error("Failed to load recruiter data.");
  return res.json();
}

async function fetchJobseekers(): Promise<JobseekerStats> {
  const res = await fetch(`${API}/api/admin/jobseekers`, { headers: authHeader() });
  if (!res.ok) throw new Error("Failed to load jobseeker data.");
  return res.json();
}

// ── Login screen ──────────────────────────────────────────────────────────────

function LoginScreen({ onLogin }: { onLogin: () => void }) {
  const [email, setEmail]       = useState("");
  const [password, setPassword] = useState("");
  const [error, setError]       = useState("");
  const [loading, setLoading]   = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const token = await apiLogin(email, password);
      setAdminToken(token);
      onLogin();
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#0a0a14] flex items-center justify-center">
      <div className="w-full max-w-sm bg-[#13131f] border border-[#2a2a40] rounded-2xl p-8">
        <h1 className="text-xl font-bold text-white mb-1">Admin Portal</h1>
        <p className="text-sm text-slate-500 mb-6">NewAgeNaukri internal dashboard</p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              className="w-full bg-[#0f0f1a] border border-[#2a2a40] rounded-lg px-3 py-2
                         text-sm text-white placeholder-slate-600 focus:outline-none
                         focus:border-violet-500"
              placeholder="admin@example.com"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              className="w-full bg-[#0f0f1a] border border-[#2a2a40] rounded-lg px-3 py-2
                         text-sm text-white placeholder-slate-600 focus:outline-none
                         focus:border-violet-500"
              placeholder="••••••••"
            />
          </div>

          {error && (
            <p className="text-xs text-red-400">{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-violet-600 hover:bg-violet-700 disabled:opacity-50
                       text-white text-sm font-medium rounded-lg py-2.5 transition-colors"
          >
            {loading ? "Signing in…" : "Sign In"}
          </button>
        </form>
      </div>
    </div>
  );
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({ label, value, color = "text-white" }: { label: string; value: number | string; color?: string }) {
  return (
    <div className="bg-[#13131f] border border-[#2a2a40] rounded-xl p-5">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className={`text-3xl font-bold ${color}`}>{value}</p>
    </div>
  );
}

// ── Recruiters tab ────────────────────────────────────────────────────────────

function RecruitersTab() {
  const [data, setData]       = useState<RecruiterStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");
  const [expanded, setExpanded] = useState<number | null>(null);

  useEffect(() => {
    fetchRecruiters()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-slate-400 text-sm">Loading…</p>;
  if (error)   return <p className="text-red-400 text-sm">{error}</p>;
  if (!data)   return null;

  const totalJobs   = data.recruiters.reduce((s, r) => s + r.total_jobs, 0);
  const activeJobs  = data.recruiters.reduce((s, r) => s + r.active_jobs, 0);

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <StatCard label="Total Recruiters" value={data.total_recruiters} color="text-violet-400" />
        <StatCard label="Total Job Posts"  value={totalJobs} />
        <StatCard label="Active Jobs"      value={activeJobs} color="text-green-400" />
      </div>

      {/* Table */}
      <div className="bg-[#13131f] border border-[#2a2a40] rounded-xl overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-[#2a2a40] text-xs text-slate-500">
              <th className="text-left px-4 py-3">Company</th>
              <th className="text-left px-4 py-3">Officer</th>
              <th className="text-left px-4 py-3">Type</th>
              <th className="text-left px-4 py-3">Jobs</th>
              <th className="text-left px-4 py-3">Active</th>
              <th className="text-left px-4 py-3">Joined</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody>
            {data.recruiters.map(r => (
              <>
                <tr
                  key={r.id}
                  className="border-b border-[#1e1e30] hover:bg-[#1a1a2e] transition-colors cursor-pointer"
                  onClick={() => setExpanded(expanded === r.id ? null : r.id)}
                >
                  <td className="px-4 py-3 text-white font-medium">{r.company_name}</td>
                  <td className="px-4 py-3 text-slate-300">{r.officer_name}</td>
                  <td className="px-4 py-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      r.company_type === "big4"
                        ? "bg-amber-900/40 text-amber-300"
                        : "bg-blue-900/40 text-blue-300"
                    }`}>
                      {r.company_type}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-slate-300">{r.total_jobs}</td>
                  <td className="px-4 py-3 text-green-400">{r.active_jobs}</td>
                  <td className="px-4 py-3 text-slate-500 text-xs">
                    {r.created_at ? new Date(r.created_at).toLocaleDateString() : "—"}
                  </td>
                  <td className="px-4 py-3 text-slate-500 text-xs">
                    {r.total_jobs > 0 ? (expanded === r.id ? "▲" : "▼") : ""}
                  </td>
                </tr>

                {expanded === r.id && r.jobs.length > 0 && (
                  <tr key={`${r.id}-jobs`} className="bg-[#0f0f1a]">
                    <td colSpan={7} className="px-6 py-3">
                      <div className="space-y-1">
                        {r.jobs.map(j => (
                          <div key={j.job_id} className="flex items-center gap-3 text-xs text-slate-400">
                            <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${j.is_active ? "bg-green-400" : "bg-slate-600"}`} />
                            <span className="text-slate-300">{j.title}</span>
                            <span className="text-slate-600">·</span>
                            <span>{j.openings} opening{j.openings !== 1 ? "s" : ""}</span>
                            {j.created_at && (
                              <>
                                <span className="text-slate-600">·</span>
                                <span>{new Date(j.created_at).toLocaleDateString()}</span>
                              </>
                            )}
                          </div>
                        ))}
                      </div>
                    </td>
                  </tr>
                )}
              </>
            ))}
          </tbody>
        </table>

        {data.recruiters.length === 0 && (
          <p className="text-slate-500 text-sm text-center py-8">No recruiters yet.</p>
        )}
      </div>
    </div>
  );
}

// ── Job Seekers tab ───────────────────────────────────────────────────────────

function JobSeekersTab() {
  const [data, setData]       = useState<JobseekerStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState("");

  useEffect(() => {
    fetchJobseekers()
      .then(setData)
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <p className="text-slate-400 text-sm">Loading…</p>;
  if (error)   return <p className="text-red-400 text-sm">{error}</p>;
  if (!data)   return null;

  const autopilotPct = data.with_profile > 0
    ? Math.round((data.autopilot_on / data.with_profile) * 100)
    : 0;

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-2 gap-4">
        <StatCard label="Total Candidates"  value={data.total_candidates} color="text-blue-400" />
        <StatCard label="Have Profile"      value={data.with_profile} />
      </div>

      {/* Career Autopilot card */}
      <div className="bg-[#13131f] border border-[#2a2a40] rounded-xl p-6">
        <p className="text-sm text-slate-400 mb-4">Career Autopilot — "Your Job On Us"</p>

        <div className="flex items-end gap-6 mb-4">
          <div>
            <p className="text-4xl font-bold text-green-400">{data.autopilot_on}</p>
            <p className="text-xs text-slate-500 mt-1">Feature ON</p>
          </div>
          <div>
            <p className="text-4xl font-bold text-slate-500">{data.autopilot_off}</p>
            <p className="text-xs text-slate-500 mt-1">Feature OFF</p>
          </div>
          <div className="ml-auto text-right">
            <p className="text-3xl font-bold text-violet-400">{autopilotPct}%</p>
            <p className="text-xs text-slate-500 mt-1">adoption rate</p>
          </div>
        </div>

        {/* Progress bar */}
        <div className="h-2 bg-[#1e1e30] rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-violet-600 to-green-500 rounded-full transition-all duration-700"
            style={{ width: `${autopilotPct}%` }}
          />
        </div>
      </div>

      {/* Summary */}
      <div className="bg-[#13131f] border border-[#2a2a40] rounded-xl p-5 text-sm text-slate-400 space-y-2">
        <div className="flex justify-between">
          <span>Signed up but no profile</span>
          <span className="text-white">{data.total_candidates - data.with_profile}</span>
        </div>
        <div className="flex justify-between">
          <span>Profile created</span>
          <span className="text-white">{data.with_profile}</span>
        </div>
        <div className="flex justify-between">
          <span>Autopilot active</span>
          <span className="text-green-400">{data.autopilot_on}</span>
        </div>
      </div>
    </div>
  );
}

// ── Main dashboard ────────────────────────────────────────────────────────────

type Tab = "recruiters" | "jobseekers";

function AdminDashboard({ onLogout }: { onLogout: () => void }) {
  const [tab, setTab] = useState<Tab>("recruiters");

  return (
    <div className="min-h-screen bg-[#0a0a14] text-white">
      {/* Header */}
      <div className="border-b border-[#1e1e30] px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-lg font-bold">Admin Portal</h1>
          <p className="text-xs text-slate-500">NewAgeNaukri internal dashboard</p>
        </div>
        <button
          onClick={onLogout}
          className="text-xs text-slate-500 hover:text-red-400 transition-colors"
        >
          Sign out
        </button>
      </div>

      <div className="max-w-5xl mx-auto px-6 py-8">
        {/* Tabs */}
        <div className="flex gap-2 mb-8">
          {(["recruiters", "jobseekers"] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-5 py-2 rounded-lg text-sm font-medium transition-colors ${
                tab === t
                  ? "bg-violet-600 text-white"
                  : "bg-[#13131f] text-slate-400 hover:text-white border border-[#2a2a40]"
              }`}
            >
              {t === "recruiters" ? "Recruiters" : "Job Seekers"}
            </button>
          ))}
        </div>

        {tab === "recruiters" && <RecruitersTab />}
        {tab === "jobseekers" && <JobSeekersTab />}
      </div>
    </div>
  );
}

// ── Page root ─────────────────────────────────────────────────────────────────

export default function AdminPortal() {
  const [authed, setAuthed] = useState(!!getAdminToken());

  const handleLogout = () => {
    clearAdminToken();
    setAuthed(false);
  };

  if (!authed) {
    return <LoginScreen onLogin={() => setAuthed(true)} />;
  }

  return <AdminDashboard onLogout={handleLogout} />;
}
