import { useState } from "react";
import { motion } from "framer-motion";
import { Link, useNavigate } from "react-router-dom";
import { Eye, EyeOff, Loader2, LogIn } from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import GlowButton from "@/components/GlowButton";
import { login, setToken } from "@/lib/auth";

const Login = () => {
  const navigate = useNavigate();

  const [email,    setEmail]    = useState("");
  const [password, setPassword] = useState("");
  const [showPass, setShowPass] = useState(false);
  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState("");

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const user = await login({ email, password });
      setToken(user.token);
      navigate("/dashboard");
    } catch (err: any) {
      setError(err.message ?? "Login failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const cls = "w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition";

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
              <label className="block text-xs text-muted-foreground mb-1">Password</label>
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
        </div>
      </motion.div>
    </div>
  );
};

export default Login;
