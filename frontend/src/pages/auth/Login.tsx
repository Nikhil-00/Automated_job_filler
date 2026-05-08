import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Link, useNavigate } from "react-router-dom";
import { Eye, EyeOff, Loader2, LogIn, CheckCircle } from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import GlowButton from "@/components/GlowButton";
import { login, setToken } from "@/lib/auth";
import { getCVBuilder }  from "@/lib/cvBuilderApi";

const API = import.meta.env.VITE_API_URL;

const Login = () => {
  const navigate = useNavigate();

  const [email,         setEmail]        = useState("");
  const [password,      setPassword]     = useState("");
  const [showPass,      setShowPass]     = useState(false);
  const [loading,       setLoading]      = useState(false);
  const [error,         setError]        = useState("");
  const [isForgotMode,  setIsForgotMode] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const user = await login({ email, password });
      setToken(user.token);
      try {
        await getCVBuilder();
        navigate("/dashboard");
      } catch {
        navigate("/cv-builder");
      }
    } catch (err: any) {
      setError(err.message ?? "Login failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const cls = "w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition text-sm";

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <AnimatedBackground />

      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y:  0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-sm"
      >
        <div className="glass-card p-8 glow-blue rounded-2xl">
          <AnimatePresence mode="wait">
            {!isForgotMode ? (
              <motion.div
                key="login"
                initial={{ opacity: 0, x: -20 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 20 }}
              >
                {/* Header */}
                <div className="flex items-center gap-3 mb-6">
                  <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center">
                    <LogIn className="w-5 h-5 text-white" />
                  </div>
                  <div>
                    <h1 className="text-xl font-bold text-foreground">Welcome back</h1>
                    <p className="text-xs text-muted-foreground">Job Seeker Portal</p>
                  </div>
                </div>

                <form onSubmit={handleSubmit} className="space-y-4">
                  <div>
                    <label className="block text-xs text-muted-foreground mb-1">Email</label>
                    <input
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      required
                      className={cls}
                      placeholder="john@example.com"
                      autoComplete="email"
                    />
                  </div>

                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="text-xs text-muted-foreground">Password</label>
                      <button
                        type="button"
                        onClick={() => setIsForgotMode(true)}
                        className="text-xs text-primary hover:underline"
                      >
                        Forgot Password?
                      </button>
                    </div>
                    <div className="relative">
                      <input
                        type={showPass ? "text" : "password"}
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                        className={`${cls} pr-10`}
                        placeholder="Your password"
                        autoComplete="current-password"
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

                  {error && (
                    <motion.p
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2"
                    >
                      {error}
                    </motion.p>
                  )}

                  <GlowButton type="submit" disabled={loading} className="w-full mt-2">
                    {loading
                      ? <span className="flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Logging in...</span>
                      : "Log In"}
                  </GlowButton>
                </form>

                <p className="text-center text-sm text-muted-foreground mt-5">
                  Don't have an account?{" "}
                  <Link to="/auth/signup" className="text-primary hover:underline font-medium">
                    Sign up
                  </Link>
                </p>

                <p className="text-center mt-3">
                  <Link to="/" className="text-xs text-muted-foreground/60 hover:text-muted-foreground transition">
                    ← Back to portal selection
                  </Link>
                </p>
              </motion.div>
            ) : (
              <CandidateForgotFlow
                key="forgot"
                initialEmail={email}
                onBack={() => setIsForgotMode(false)}
              />
            )}
          </AnimatePresence>
        </div>
      </motion.div>
    </div>
  );
};

// ── Candidate Forgot Flow ───────────────────────────────────────────────────

function CandidateForgotFlow({ initialEmail, onBack }: { initialEmail: string; onBack: () => void }) {
  const [step,         setStep]        = useState<"email" | "otp" | "reset" | "done">("email");
  const [email,        setEmail]       = useState(initialEmail);
  const [otp,          setOtp]         = useState("");
  const [newPass,      setNewPass]     = useState("");
  const [confirmPass,  setConfirmPass] = useState("");
  const [loading,      setLoading]     = useState(false);
  const [error,        setError]       = useState("");
  const [showPass,     setShowPass]    = useState(false);

  const cls = "w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition text-sm";

  const handleSendOtp = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(""); setLoading(true);
    try {
      const res = await fetch(`${API}/api/auth/forgot-password`, {
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
      const res = await fetch(`${API}/api/auth/reset-password`, {
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
      <button onClick={onBack} className="text-xs text-muted-foreground hover:text-foreground mb-2 flex items-center gap-1">
        ← Back to login
      </button>

      {step === "email" && (
        <form onSubmit={handleSendOtp} className="space-y-4">
          <h2 className="text-base font-semibold text-foreground">Reset Password</h2>
          <p className="text-xs text-muted-foreground leading-relaxed">
            Enter your email and we'll send a code to reset your password.
          </p>
          <div>
            <label className="block text-xs text-muted-foreground mb-1">Email</label>
            <input type="email" value={email} onChange={e => setEmail(e.target.value)}
              required placeholder="john@example.com" className={cls} />
          </div>
          {error && <p className="text-xs text-red-400 bg-red-500/10 p-2 rounded border border-red-500/20">{error}</p>}
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
          {error && <p className="text-xs text-red-400 bg-red-500/10 p-2 rounded border border-red-500/20">{error}</p>}
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

export default Login;
