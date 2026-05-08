import { useState, useEffect } from "react";
import { motion } from "framer-motion";
import {
  ShieldCheck, LogIn, Loader2, Eye, EyeOff,
  Building2, Mail, Phone, User, Clock, CheckCircle, XCircle, AlertCircle, LogOut, KeyRound,
} from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import GlowButton from "@/components/GlowButton";

const API = import.meta.env.VITE_API_URL;

interface Company {
  id:                number;
  company_name:      string;
  officer_name:      string;
  email:             string;
  phone:             string;
  is_otp_verified:   number;
  status:            "pending" | "approved" | "rejected";
  assigned_email:    string | null;
  assigned_password: string | null;
  created_at:        string;
}

const cls = "w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-violet-500/50 transition text-sm";

export default function AdminPortal() {
  // Never auto-login from storage — always require fresh login on page visit
  const [token, setToken] = useState<string | null>(null);

  // Clear any stale token left in storage from older code
  useEffect(() => { sessionStorage.removeItem("admin_token"); }, []);

  const handleLogin = (t: string) => {
    setToken(t);
  };

  const handleLogout = () => {
    setToken(null);
  };

  return (
    <div className="min-h-screen px-4 py-8">
      <AnimatedBackground />
      {token
        ? <AdminDashboard token={token} onLogout={handleLogout} />
        : <AdminLogin onLogin={handleLogin} />
      }
    </div>
  );
}


// ── Login ─────────────────────────────────────────────────────────────────────

function AdminLogin({ onLogin }: { onLogin: (t: string) => void }) {
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      const res = await fetch(`${API}/api/admin/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Login failed.");
      onLogin(data.token);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex items-center justify-center min-h-screen">
      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-sm"
      >
        <div className="glass-card p-8 rounded-2xl">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-violet-600 to-purple-600 flex items-center justify-center">
              <ShieldCheck className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-foreground">Admin Portal</h1>
              <p className="text-xs text-muted-foreground">AutoApply AI — Admin Access</p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs text-muted-foreground mb-1">Email</label>
              <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                required placeholder="admin@autoapply.ai" className={cls} autoComplete="email" />
            </div>
            <div>
              <label className="block text-xs text-muted-foreground mb-1">Password</label>
              <div className="relative">
                <input type={showPass ? "text" : "password"} value={password}
                  onChange={e => setPassword(e.target.value)}
                  required placeholder="Admin password"
                  className={`${cls} pr-10`} autoComplete="current-password" />
                <button type="button" onClick={() => setShowPass(!showPass)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                  {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {error && (
              <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <GlowButton type="submit" disabled={loading} className="w-full mt-2">
              {loading
                ? <span className="flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" />Logging in…</span>
                : <span className="flex items-center justify-center gap-2"><LogIn className="w-4 h-4" />Log In</span>
              }
            </GlowButton>
          </form>
        </div>
      </motion.div>
    </div>
  );
}


// ── Dashboard ─────────────────────────────────────────────────────────────────

function AdminDashboard({ token, onLogout }: { token: string; onLogout: () => void }) {
  const [companies,    setCompanies]    = useState<Company[]>([]);
  const [loading,      setLoading]      = useState(true);
  const [filter,       setFilter]       = useState<"all" | "pending" | "approved" | "rejected">("all");
  const [actionError,  setActionError]  = useState<string | null>(null);
  const [actioning,    setActioning]    = useState<number | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/admin/companies?status=${filter}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.status === 401) { onLogout(); return; }
      const data = await res.json();
      setCompanies(data.companies ?? []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filter]);

  const updateStatus = async (id: number, status: "approved" | "rejected") => {
    setActionError(null);
    setActioning(id);
    try {
      const res = await fetch(`${API}/api/admin/companies/${id}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ status }),
      });
      if (!res.ok) {
        const d = await res.json().catch(() => ({}));
        throw new Error(d.detail ?? `Failed to ${status} company.`);
      }
      await load();
    } catch (err: any) {
      setActionError(err.message);
    } finally {
      setActioning(null);
    }
  };

  const pending  = companies.filter(c => c.status === "pending").length;
  const approved = companies.filter(c => c.status === "approved").length;

  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-violet-600 to-purple-600 flex items-center justify-center">
            <ShieldCheck className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-foreground">Admin Dashboard</h1>
            <p className="text-xs text-muted-foreground">Company signup requests</p>
          </div>
        </div>
        <button onClick={onLogout}
          className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground transition">
          <LogOut className="w-4 h-4" /> Logout
        </button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3 mb-6">
        {[
          { label: "Total",    value: companies.length, color: "text-foreground" },
          { label: "Pending",  value: pending,          color: "text-yellow-400" },
          { label: "Approved", value: approved,         color: "text-green-400"  },
        ].map(s => (
          <div key={s.label} className="glass-card p-4 text-center">
            <p className={`text-2xl font-bold ${s.color}`}>{s.value}</p>
            <p className="text-xs text-muted-foreground mt-0.5">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Filter tabs */}
      <div className="flex gap-2 mb-4">
        {(["all", "pending", "approved", "rejected"] as const).map(f => (
          <button key={f} onClick={() => setFilter(f)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold capitalize transition
              ${filter === f
                ? "bg-primary/20 border border-primary/40 text-primary"
                : "bg-muted border border-border text-muted-foreground hover:text-foreground"
              }`}>
            {f}
          </button>
        ))}
      </div>

      {/* Action error */}
      {actionError && (
        <div className="mb-4 px-4 py-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-sm text-red-400 flex items-center justify-between">
          <span>{actionError}</span>
          <button onClick={() => setActionError(null)} className="ml-3 text-red-400/60 hover:text-red-400">✕</button>
        </div>
      )}

      {/* Table */}
      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
        </div>
      ) : companies.length === 0 ? (
        <div className="glass-card p-10 text-center text-muted-foreground text-sm">
          No {filter !== "all" ? filter : ""} company requests yet.
        </div>
      ) : (
        <div className="space-y-3">
          {companies.map((c, i) => (
            <motion.div
              key={c.id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.04 }}
              className="glass-card p-4"
            >
              <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                {/* Info */}
                <div className="flex-1 space-y-1.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Building2 className="w-4 h-4 text-yellow-400 shrink-0" />
                    <span className="font-semibold text-foreground">{c.company_name}</span>
                    <StatusBadge status={c.status} />
                    {!c.is_otp_verified && (
                      <span className="text-xs px-2 py-0.5 rounded-full bg-orange-500/10 border border-orange-500/30 text-orange-400">
                        Unverified
                      </span>
                    )}
                  </div>
                  <div className="flex flex-wrap gap-x-4 gap-y-1">
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <User className="w-3 h-3" />{c.officer_name}
                    </span>
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Mail className="w-3 h-3" />{c.email}
                    </span>
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Phone className="w-3 h-3" />{c.phone}
                    </span>
                    <span className="flex items-center gap-1 text-xs text-muted-foreground">
                      <Clock className="w-3 h-3" />
                      {new Date(c.created_at).toLocaleDateString("en-IN", {
                        day: "numeric", month: "short", year: "numeric",
                        hour: "2-digit", minute: "2-digit",
                      })}
                    </span>
                  </div>
                </div>

                {/* Actions */}
                {c.status === "pending" && (
                  <div className="flex gap-2 shrink-0">
                    <button
                      onClick={() => updateStatus(c.id, "approved")}
                      disabled={actioning === c.id}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-green-500/20 border border-green-500/40 text-green-400 hover:bg-green-500/30 disabled:opacity-50 transition">
                      {actioning === c.id
                        ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                        : <CheckCircle className="w-3.5 h-3.5" />
                      } Approve
                    </button>
                    <button
                      onClick={() => updateStatus(c.id, "rejected")}
                      disabled={actioning === c.id}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-red-500/20 border border-red-500/40 text-red-400 hover:bg-red-500/30 disabled:opacity-50 transition">
                      <XCircle className="w-3.5 h-3.5" /> Reject
                    </button>
                  </div>
                )}
              </div>

              {/* Assigned credentials (only shown after approval) */}
              {c.status === "approved" && c.assigned_email && (
                <div className="mt-3 pt-3 border-t border-border flex flex-wrap gap-4">
                  <span className="flex items-center gap-1.5 text-xs">
                    <KeyRound className="w-3.5 h-3.5 text-green-400" />
                    <span className="text-muted-foreground">Login:</span>
                    <span className="font-mono text-green-400 font-semibold">{c.assigned_email}</span>
                  </span>
                  <span className="flex items-center gap-1.5 text-xs">
                    <span className="text-muted-foreground">Password:</span>
                    <span className="font-mono text-green-400 font-semibold">{c.assigned_password}</span>
                  </span>
                </div>
              )}
            </motion.div>
          ))}
        </div>
      )}
    </div>
  );
}


function StatusBadge({ status }: { status: Company["status"] }) {
  const map = {
    pending:  { cls: "bg-yellow-500/10 border-yellow-500/30 text-yellow-400", icon: <AlertCircle className="w-3 h-3" /> },
    approved: { cls: "bg-green-500/10  border-green-500/30  text-green-400",  icon: <CheckCircle  className="w-3 h-3" /> },
    rejected: { cls: "bg-red-500/10    border-red-500/30    text-red-400",    icon: <XCircle      className="w-3 h-3" /> },
  };
  const s = map[status];
  return (
    <span className={`flex items-center gap-1 text-xs px-2 py-0.5 rounded-full border capitalize ${s.cls}`}>
      {s.icon}{status}
    </span>
  );
}
