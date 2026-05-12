import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { LogIn, Loader2, CheckCircle, Eye, EyeOff } from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import GlowButton from "@/components/GlowButton";
import NonBig4Dashboard from "./NonBig4Dashboard";

const API = import.meta.env.VITE_API_URL;

type Tab = "login" | "signup" | "forgot";
type Step = "form" | "otp" | "done";

const cls = "w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-yellow-500/50 transition text-sm";

interface DashboardState {
  token:       string;
  companyName: string;
  officerName: string;
}

export default function CompanyPortal() {
  const [tab,         setTab]         = useState<Tab>("login");
  const [dashboard,   setDashboard]   = useState<DashboardState | null>(null);
  const [forgotEmail, setForgotEmail] = useState("");

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
    <div className="min-h-screen flex items-center justify-center px-4 py-8">
      <AnimatedBackground />

      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y:  0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-md"
      >
        <div className="glass-card rounded-2xl p-8">
          {/* Header */}
          <div className="flex flex-col items-center gap-3 mb-7">
            <img src="/logo.png" alt="NextGen Naukri" className="h-14 w-auto" />
            <div className="text-center">
              <h1 className="text-xl font-bold text-foreground">
                {tab === "signup" ? "Create Recruiter Account" : tab === "forgot" ? "Reset Password" : "Welcome back"}
              </h1>
              <p className="text-sm text-muted-foreground mt-0.5">Company / Recruiter Portal</p>
            </div>
          </div>

          <AnimatePresence mode="wait">
            {tab === "signup" && (
              <SignupFlow key="signup" onSwitchToLogin={() => setTab("login")} />
            )}
            {tab === "login" && (
              <LoginForm
                key="login"
                onDashboard={setDashboard}
                onSwitchToSignup={() => setTab("signup")}
                onForgotPassword={(email) => {
                  setForgotEmail(email);
                  setTab("forgot");
                }}
              />
            )}
            {tab === "forgot" && (
              <ForgotFlow
                key="forgot"
                initialEmail={forgotEmail}
                onBack={() => setTab("login")}
              />
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  );
}


// ── Signup flow (form → OTP → done) ──────────────────────────────────────────

function SignupFlow({ onSwitchToLogin }: { onSwitchToLogin: () => void }) {
  const [step,         setStep]         = useState<Step>("form");
  const [companyName,  setCompanyName]  = useState("");
  const [officerName,  setOfficerName]  = useState("");
  const [email,        setEmail]        = useState("");
  const [phone,        setPhone]        = useState("");
  const [otp,          setOtp]          = useState("");
  const [password,     setPassword]     = useState("");
  const [showPass,     setShowPass]     = useState(false);
  const [loading,      setLoading]      = useState(false);
  const [error,        setError]        = useState("");
  const [resending,    setResending]    = useState(false);

  const handleSignup = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!companyName.trim()) { setError("Please enter your company name."); return; }
    if (password.length < 6) { setError("Password must be at least 6 characters."); return; }
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
          password,
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
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-muted-foreground mb-1">Officer Name</label>
              <input value={officerName} onChange={e => setOfficerName(e.target.value)}
                required placeholder="John Smith" className={cls} />
            </div>
            <div>
              <label className="block text-xs text-muted-foreground mb-1">Phone Number</label>
              <input type="tel" value={phone} onChange={e => setPhone(e.target.value)}
                required placeholder="+91 98765 43210" className={cls} />
            </div>
          </div>
          <div>
            <label className="block text-xs text-muted-foreground mb-1">Work Email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              required placeholder="officer@company.com" className={cls} />
          </div>
          <div>
            <label className="block text-xs text-muted-foreground mb-1">Set Password</label>
            <div className="relative">
              <input
                type={showPass ? "text" : "password"}
                value={password}
                onChange={e => setPassword(e.target.value)}
                required
                placeholder="Minimum 6 characters"
                className={`${cls} pr-10`}
              />
              <button
                type="button"
                onClick={() => setShowPass(!showPass)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {error && <ErrorBox msg={error} />}

          <GlowButton type="submit" disabled={loading} className="w-full mt-2"
            style={{ background: "linear-gradient(135deg,#ca8a04,#eab308)" }}>
            {loading
              ? <span className="flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" />Sending OTP…</span>
              : "Send Verification Code"
            }
          </GlowButton>

          <p className="text-center text-sm text-muted-foreground mt-4">
            Already have an account?{" "}
            <button type="button" onClick={onSwitchToLogin}
              className="text-yellow-500 font-semibold hover:underline">
              Log in
            </button>
          </p>
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
          <div className="w-14 h-14 rounded-full flex items-center justify-center mx-auto bg-green-500/20 border border-green-500/40">
            <CheckCircle className="w-7 h-7 text-green-400" />
          </div>
          <h3 className="text-lg font-bold text-foreground">Portal Ready!</h3>
          <p className="text-sm text-muted-foreground">
            Your company portal has been <span className="text-green-400 font-medium">activated</span>.
            You can now log in using your email and the password you just set.
          </p>
          <GlowButton onClick={() => window.location.reload()} className="w-full mt-4"
            style={{ background: "linear-gradient(135deg,#ca8a04,#eab308)" }}>
            Go to Login
          </GlowButton>
        </div>
      )}
    </motion.div>
  );
}


// ── Login ─────────────────────────────────────────────────────────────────────

function LoginForm({ onDashboard, onForgotPassword, onSwitchToSignup }: {
  onDashboard: (d: DashboardState) => void;
  onForgotPassword: (email: string) => void;
  onSwitchToSignup: () => void;
}) {
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
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs text-muted-foreground">Password</label>
            <button
              type="button"
              onClick={() => onForgotPassword(email)}
              className="text-xs text-yellow-400 hover:underline"
            >
              Forgot Password?
            </button>
          </div>
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

        <p className="text-center text-sm text-muted-foreground mt-4">
          New recruiter?{" "}
          <button type="button" onClick={onSwitchToSignup}
            className="text-yellow-500 font-semibold hover:underline">
            Sign up
          </button>
        </p>
      </form>
    </motion.div>
  );
}


// ── Forgot Password flow ──────────────────────────────────────────────────────

function ForgotFlow({ initialEmail, onBack }: { initialEmail: string; onBack: () => void }) {
  const [step,         setStep]        = useState<"email" | "otp" | "reset" | "done">("email");
  const [email,        setEmail]       = useState(initialEmail);
  const [otp,          setOtp]         = useState("");
  const [newPass,      setNewPass]     = useState("");
  const [confirmPass,  setConfirmPass] = useState("");
  const [loading,      setLoading]     = useState(false);
  const [error,        setError]       = useState("");
  const [showPass,     setShowPass]    = useState(false);

  const handleSendOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      const res = await fetch(`${API}/api/company/forgot-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Failed to send code.");
      setStep("otp");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleVerify = async (e: React.FormEvent) => {
    e.preventDefault();
    setStep("reset");
  };

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (newPass !== confirmPass) { setError("Passwords do not match."); return; }
    if (newPass.length < 6) { setError("Password must be at least 6 characters."); return; }

    setError(""); setLoading(true);
    try {
      const res = await fetch(`${API}/api/company/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, otp_code: otp, new_password: newPass }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail ?? "Reset failed.");
      setStep("done");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <motion.div
      key={step}
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ duration: 0.25 }}
      className="space-y-4"
    >
      <button onClick={onBack} className="text-xs text-muted-foreground hover:text-foreground mb-2">
        ← Back to login
      </button>

      {step === "email" && (
        <form onSubmit={handleSendOtp} className="space-y-4">
          <h2 className="text-base font-semibold text-foreground">Reset Password</h2>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Enter your email address and we'll send you a 6-digit code to reset your password.
          </p>
          <div>
            <label className="block text-xs text-muted-foreground mb-1">Work Email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              required placeholder="officer@company.com" className={cls} />
          </div>
          {error && <ErrorBox msg={error} />}
          <GlowButton type="submit" disabled={loading} className="w-full">
            {loading ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : "Send Reset Code"}
          </GlowButton>
        </form>
      )}

      {step === "otp" && (
        <form onSubmit={handleVerify} className="space-y-4">
          <h2 className="text-base font-semibold text-foreground text-center">Verify Code</h2>
          <p className="text-xs text-muted-foreground text-center">Code sent to {email}</p>
          <input
            value={otp}
            onChange={e => setOtp(e.target.value.replace(/\D/g, "").slice(0, 6))}
            required maxLength={6}
            placeholder="123456"
            className={`${cls} text-center text-2xl font-bold tracking-widest`}
          />
          <GlowButton type="submit" className="w-full">Continue</GlowButton>
        </form>
      )}

      {step === "reset" && (
        <form onSubmit={handleReset} className="space-y-4">
          <h2 className="text-base font-semibold text-foreground">Set New Password</h2>
          <div>
            <label className="block text-xs text-muted-foreground mb-1">New Password</label>
            <div className="relative">
              <input type={showPass ? "text" : "password"} value={newPass}
                onChange={e => setNewPass(e.target.value)} required className={cls} />
              <button type="button" onClick={() => setShowPass(!showPass)} className="absolute right-3 top-1/2 -translate-y-1/2">
                {showPass ? <EyeOff className="w-4 h-4 text-muted-foreground" /> : <Eye className="w-4 h-4 text-muted-foreground" />}
              </button>
            </div>
          </div>
          <div>
            <label className="block text-xs text-muted-foreground mb-1">Confirm New Password</label>
            <input type="password" value={confirmPass} onChange={e => setConfirmPass(e.target.value)} required className={cls} />
          </div>
          {error && <ErrorBox msg={error} />}
          <GlowButton type="submit" disabled={loading} className="w-full">
            {loading ? <Loader2 className="w-4 h-4 animate-spin mx-auto" /> : "Update Password"}
          </GlowButton>
        </form>
      )}

      {step === "done" && (
        <div className="text-center py-4 space-y-3">
          <div className="w-12 h-12 rounded-full bg-green-500/20 border border-green-500/40 flex items-center justify-center mx-auto">
            <CheckCircle className="w-6 h-6 text-green-400" />
          </div>
          <h3 className="font-bold text-foreground">Password Reset!</h3>
          <p className="text-xs text-muted-foreground">Your password has been updated. You can now log in.</p>
          <GlowButton onClick={onBack} className="w-full mt-2">Back to Login</GlowButton>
        </div>
      )}
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
