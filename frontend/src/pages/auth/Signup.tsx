import { useState } from "react";
import { motion } from "framer-motion";
import { Link, useNavigate } from "react-router-dom";
import { Eye, EyeOff, Loader2, UserPlus } from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import GlowButton from "@/components/GlowButton";
import { signup } from "@/lib/auth";

const Signup = () => {
  const navigate = useNavigate();

  const [form, setForm] = useState({
    first_name: "",
    last_name:  "",
    email:      "",
    phone:      "",
    password:   "",
    confirm:    "",
  });
  const [showPass,  setShowPass]  = useState(false);
  const [loading,   setLoading]   = useState(false);
  const [error,     setError]     = useState("");

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    if (form.password !== form.confirm) {
      setError("Passwords do not match.");
      return;
    }
    if (form.password.length < 6) {
      setError("Password must be at least 6 characters.");
      return;
    }

    setLoading(true);
    try {
      await signup({
        first_name: form.first_name,
        last_name:  form.last_name,
        email:      form.email,
        phone:      form.phone,
        password:   form.password,
      });
      // Pass email to verify page
      localStorage.setItem("pending_verify_email", form.email);
      navigate("/auth/verify");
    } catch (err: any) {
      setError(err.message ?? "Signup failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const cls = "w-full px-4 py-2.5 rounded-lg bg-input border border-border text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary/50 transition";

  return (
    <div className="min-h-screen flex items-center justify-center px-4 py-10">
      <AnimatedBackground />

      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y:  0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-md"
      >
        <div className="glass-card p-8 glow-blue rounded-2xl">
          {/* Header */}
          <div className="flex items-center gap-3 mb-6">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600 to-violet-600 flex items-center justify-center">
              <UserPlus className="w-5 h-5 text-white" />
            </div>
            <div>
              <h1 className="text-xl font-bold text-foreground">Create Account</h1>
              <p className="text-xs text-muted-foreground">Job Seeker Portal</p>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Name row */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs text-muted-foreground mb-1">First Name</label>
                <input value={form.first_name} onChange={set("first_name")} required
                  className={cls} placeholder="John" />
              </div>
              <div>
                <label className="block text-xs text-muted-foreground mb-1">Last Name</label>
                <input value={form.last_name} onChange={set("last_name")} required
                  className={cls} placeholder="Doe" />
              </div>
            </div>

            <div>
              <label className="block text-xs text-muted-foreground mb-1">Email</label>
              <input type="email" value={form.email} onChange={set("email")} required
                className={cls} placeholder="john@example.com" />
            </div>

            <div>
              <label className="block text-xs text-muted-foreground mb-1">Phone Number</label>
              <input type="tel" value={form.phone} onChange={set("phone")} required
                className={cls} placeholder="+91 98765 43210" />
            </div>

            <div>
              <label className="block text-xs text-muted-foreground mb-1">Password</label>
              <div className="relative">
                <input
                  type={showPass ? "text" : "password"}
                  value={form.password}
                  onChange={set("password")}
                  required
                  className={`${cls} pr-10`}
                  placeholder="Min 6 characters"
                />
                <button type="button" onClick={() => setShowPass(!showPass)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                  {showPass ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <div>
              <label className="block text-xs text-muted-foreground mb-1">Confirm Password</label>
              <input
                type="password"
                value={form.confirm}
                onChange={set("confirm")}
                required
                className={cls}
                placeholder="Repeat password"
              />
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
                ? <span className="flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Creating account...</span>
                : "Sign Up"}
            </GlowButton>
          </form>

          <p className="text-center text-sm text-muted-foreground mt-5">
            Already have an account?{" "}
            <Link to="/auth/login" className="text-primary hover:underline font-medium">
              Log in
            </Link>
          </p>
        </div>
      </motion.div>
    </div>
  );
};

export default Signup;
