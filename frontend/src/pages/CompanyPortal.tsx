import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Building2, LogIn, UserPlus, Loader2, CheckCircle, Eye, EyeOff, Mail } from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import GlowButton from "@/components/GlowButton";
import NonBig4Dashboard from "./NonBig4Dashboard";

const API = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");

type Tab = "login" | "signup";
type Step = "form" | "otp" | "done";

const cls = "w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-yellow-500/50 transition text-sm";

interface DashboardState {
  token:       string;
  companyName: string;
  officerName: string;
}

export default function CompanyPortal() {
  const [tab,       setTab]       = useState<Tab>("signup");
  const [dashboard, setDashboard] = useState<DashboardState | null>(null);

  if (dashboard) {
    return (
      <NonBig4Dashboard
        token={dashboard.token}
        companyName={dashboard.companyName}
        officerName={dashboard.officerName}
        onLogout={() => setDashboard(null)}
      />
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <AnimatedBackground />

      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y:  0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-md"
      >
        {/* Header */}
        <div className="text-center mb-6">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-yellow-600 to-yellow-400 flex items-center justify-center mx-auto mb-3">
            <Building2 className="w-7 h-7 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-foreground">Company Portal</h1>
          <p className="text-sm text-muted-foreground mt-1">AutoApply AI — Partner Access</p>
        </div>

        <div className="glass-card rounded-2xl overflow-hidden">
          {/* Tab switcher */}
          <div className="flex border-b border-border">
            {(["signup", "login"] as Tab[]).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`flex-1 py-3 text-sm font-semibold transition-colors
                  ${tab === t
                    ? "text-yellow-400 border-b-2 border-yellow-400 bg-yellow-500/5"
                    : "text-muted-foreground hover:text-foreground"
                  }`}
              >
                {t === "signup"
                  ? <span className="flex items-center justify-center gap-1.5"><UserPlus className="w-4 h-4" />Register</span>
                  : <span className="flex items-center justify-center gap-1.5"><LogIn className="w-4 h-4" />Login</span>
                }
              </button>
            ))}
          </div>

          <div className="p-7">
            <AnimatePresence mode="wait">
              {tab === "signup"
                ? <SignupFlow key="signup" />
                : <LoginForm key="login" onDashboard={setDashboard} />
              }
            </AnimatePresence>
          </div>
        </div>
      </motion.div>
    </div>
  );
}


// ── Signup flow (form → OTP → done) ──────────────────────────────────────────

function SignupFlow() {
  const [step,         setStep]         = useState<Step>("form");
  const [companyName,  setCompanyName]  = useState("");
  const [officerName,  setOfficerName]  = useState("");
  const [email,        setEmail]        = useState("");
  const [phone,        setPhone]        = useState("");
  const [otp,          setOtp]          = useState("");
  const [loading,      setLoading]      = useState(false);
  const [error,        setError]        = useState("");
  const [resending,    setResending]    = useState(false);

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!companyName.trim()) { setError("Please enter your company name."); return; }
    setError(""); setLoading(true);
    try {
      const res = await fetch(`${API}/api/company/signup`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          company_name: companyName.trim(),
          officer_name: officerName,
          email,
          phone,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Signup failed.");
      setStep("otp");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      const res = await fetch(`${API}/api/company/verify-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, otp_code: otp }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Verification failed.");
      setStep("done");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setResending(true); setError("");
    try {
      const res = await fetch(`${API}/api/company/resend-otp`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Failed to resend.");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setResending(false);
    }
  };

  return (
    <motion.div
      key={step}
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.25 }}
    >
      {/* ── Step: form ── */}
      {step === "form" && (
        <form onSubmit={handleSignup} className="space-y-4">
          <h2 className="text-base font-semibold text-foreground mb-1">Register your company</h2>

          <div>
            <label className="block text-xs text-muted-foreground mb-1">Company Name</label>
            <input
              value={companyName}
              onChange={e => setCompanyName(e.target.value)}
              required
              placeholder="e.g. Acme Corp"
              className={cls}
            />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground mb-1">Officer Name</label>
            <input value={officerName} onChange={e => setOfficerName(e.target.value)}
              required placeholder="John Smith" className={cls} />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground mb-1">Work Email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              required placeholder="officer@company.com" className={cls} />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground mb-1">Phone Number</label>
            <input type="tel" value={phone} onChange={e => setPhone(e.target.value)}
              required placeholder="+91 98765 43210" className={cls} />
          </div>

          {error && <ErrorBox msg={error} />}

          <GlowButton type="submit" disabled={loading} className="w-full mt-2"
            style={{ background: "linear-gradient(135deg,#ca8a04,#eab308)" }}>
            {loading
              ? <span className="flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" />Sending OTP…</span>
              : "Send Verification Code"
            }
          </GlowButton>
        </form>
      )}

      {/* ── Step: otp ── */}
      {step === "otp" && (
        <form onSubmit={handleVerify} className="space-y-4">
          <div className="text-center mb-2">
            <p className="text-sm text-muted-foreground">We sent a 6-digit code to</p>
            <p className="text-sm font-semibold text-foreground">{email}</p>
          </div>

          <div>
            <label className="block text-xs text-muted-foreground mb-1">Verification Code</label>
            <input
              value={otp}
              onChange={e => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
              required maxLength={6}
              placeholder="123456"
              className={`${cls} text-center text-2xl font-bold tracking-widest`}
            />
          </div>

          {error && <ErrorBox msg={error} />}

          <GlowButton type="submit" disabled={loading} className="w-full"
            style={{ background: "linear-gradient(135deg,#ca8a04,#eab308)" }}>
            {loading
              ? <span className="flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" />Verifying…</span>
              : "Verify & Submit"
            }
          </GlowButton>

          <p className="text-center text-xs text-muted-foreground">
            Didn't receive it?{" "}
            <button type="button" onClick={handleResend} disabled={resending}
              className="text-yellow-400 hover:underline disabled:opacity-50">
              {resending ? "Sending…" : "Resend code"}
            </button>
          </p>
        </form>
      )}

      {/* ── Step: done ── */}
      {step === "done" && (
        <div className="text-center py-4 space-y-3">
          <div className="w-14 h-14 rounded-full flex items-center justify-center mx-auto bg-blue-500/20 border border-blue-500/40">
            <Mail className="w-7 h-7 text-blue-400" />
          </div>
          <h3 className="text-lg font-bold text-foreground">Portal Ready!</h3>
          <p className="text-sm text-muted-foreground">
            Your company portal has been <span className="text-blue-400 font-medium">approved</span>.
            Check <span className="text-foreground font-medium">{email}</span> for your login credentials.
            You can log in right away!
          </p>
        </div>
      )}
    </motion.div>
  );
}


// ── Login ─────────────────────────────────────────────────────────────────────

function LoginForm({ onDashboard }: { onDashboard: (d: DashboardState) => void }) {
  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      const res = await fetch(`${API}/api/company/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Login failed.");
      onDashboard({
        token:       data.token,
        companyName: data.company_name,
        officerName: data.officer_name,
      });
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.25 }}
    >
      <form className="space-y-4" onSubmit={handleLogin}>
        <h2 className="text-base font-semibold text-foreground mb-1">Company Login</h2>
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Email</label>
          <input type="email" value={email} onChange={e => setEmail(e.target.value)}
            required placeholder="name.company@autofill.com" className={cls} />
        </div>
        <div>
          <label className="block text-xs text-muted-foreground mb-1">Password</label>
          <div className="relative">
            <input type={showPass ? "text" : "password"} value={password}
              onChange={e => setPassword(e.target.value)}
              required placeholder="Your password" className={`${cls} pr-10`} />
            <button type="button" onClick={() => setShowPass(!showPass)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
              {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {error && <ErrorBox msg={error} />}

        <GlowButton type="submit" disabled={loading} className="w-full"
          style={{ background: "linear-gradient(135deg,#ca8a04,#eab308)" }}>
          {loading
            ? <span className="flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" />Logging in…</span>
            : <span className="flex items-center justify-center gap-2"><LogIn className="w-4 h-4" />Log In</span>
          }
        </GlowButton>
      </form>
    </motion.div>
  );
}


// ── Shared ────────────────────────────────────────────────────────────────────

function ErrorBox({ msg }: { msg: string }) {
  return (
    <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }}
      className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
      {msg}
    </motion.p>
  );
}
