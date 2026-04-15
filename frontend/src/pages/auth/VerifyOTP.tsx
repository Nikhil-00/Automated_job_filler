import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { Loader2, MailCheck } from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";
import GlowButton from "@/components/GlowButton";
import { resendOtp, setToken, verifyOtp } from "@/lib/auth";

const VerifyOTP = () => {
  const navigate = useNavigate();
  const email    = localStorage.getItem("pending_verify_email") ?? "";

  const [digits,    setDigits]   = useState(["", "", "", "", "", ""]);
  const [loading,   setLoading]  = useState(false);
  const [resending, setResending] = useState(false);
  const [error,     setError]    = useState("");
  const [success,   setSuccess]  = useState("");
  const inputRefs = useRef<(HTMLInputElement | null)[]>([]);

  useEffect(() => {
    if (!email) navigate("/auth/signup");
    inputRefs.current[0]?.focus();
  }, []);

  const handleDigit = (i: number, val: string) => {
    if (!/^\d?$/.test(val)) return;
    const next = [...digits];
    next[i] = val;
    setDigits(next);
    if (val && i < 5) inputRefs.current[i + 1]?.focus();
  };

  const handleKey = (i: number, e: React.KeyboardEvent) => {
    if (e.key === "Backspace" && !digits[i] && i > 0) {
      inputRefs.current[i - 1]?.focus();
    }
  };

  const handlePaste = (e: React.ClipboardEvent) => {
    const pasted = e.clipboardData.getData("text").replace(/\D/g, "").slice(0, 6);
    if (pasted.length === 6) {
      setDigits(pasted.split(""));
      inputRefs.current[5]?.focus();
    }
  };

  const handleVerify = async () => {
    const code = digits.join("");
    if (code.length < 6) { setError("Please enter all 6 digits."); return; }

    setError("");
    setLoading(true);
    try {
      const user = await verifyOtp({ email, otp_code: code });
      setToken(user.token);
      localStorage.removeItem("pending_verify_email");
      navigate("/dashboard");
    } catch (err: any) {
      setError(err.message ?? "Invalid code. Please try again.");
      setDigits(["", "", "", "", "", ""]);
      inputRefs.current[0]?.focus();
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setResending(true);
    setError("");
    try {
      await resendOtp(email);
      setSuccess("New code sent! Check your inbox.");
      setDigits(["", "", "", "", "", ""]);
      inputRefs.current[0]?.focus();
      setTimeout(() => setSuccess(""), 4000);
    } catch (err: any) {
      setError(err.message ?? "Could not resend code.");
    } finally {
      setResending(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <AnimatedBackground />

      <motion.div
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y:  0 }}
        transition={{ duration: 0.4 }}
        className="w-full max-w-sm"
      >
        <div className="glass-card p-8 glow-purple rounded-2xl text-center">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-violet-600 to-blue-600 mx-auto mb-5 flex items-center justify-center">
            <MailCheck className="w-7 h-7 text-white" />
          </div>

          <h1 className="text-xl font-bold text-foreground mb-1">Check your email</h1>
          <p className="text-sm text-muted-foreground mb-1">
            We sent a 6-digit code to
          </p>
          <p className="text-sm font-medium text-primary mb-6 break-all">{email}</p>

          {/* OTP input boxes */}
          <div className="flex gap-2 justify-center mb-6" onPaste={handlePaste}>
            {digits.map((d, i) => (
              <input
                key={i}
                ref={(el) => (inputRefs.current[i] = el)}
                type="text"
                inputMode="numeric"
                maxLength={1}
                value={d}
                onChange={(e) => handleDigit(i, e.target.value)}
                onKeyDown={(e) => handleKey(i, e)}
                className="w-11 h-12 text-center text-xl font-bold rounded-lg
                           bg-input border border-border text-foreground
                           focus:outline-none focus:ring-2 focus:ring-primary/60
                           transition caret-primary"
              />
            ))}
          </div>

          {error && (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-sm text-red-400 bg-red-500/10 border border-red-500/20
                         rounded-lg px-3 py-2 mb-4"
            >
              {error}
            </motion.p>
          )}
          {success && (
            <motion.p
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="text-sm text-green-400 bg-green-500/10 border border-green-500/20
                         rounded-lg px-3 py-2 mb-4"
            >
              {success}
            </motion.p>
          )}

          <GlowButton
            onClick={handleVerify}
            disabled={loading || digits.join("").length < 6}
            className="w-full mb-3"
          >
            {loading
              ? <span className="flex items-center justify-center gap-2"><Loader2 className="w-4 h-4 animate-spin" /> Verifying...</span>
              : "Verify Email"}
          </GlowButton>

          <button
            onClick={handleResend}
            disabled={resending}
            className="text-sm text-muted-foreground hover:text-foreground transition flex items-center gap-1 justify-center w-full"
          >
            {resending && <Loader2 className="w-3 h-3 animate-spin" />}
            Didn't receive a code? <span className="text-primary font-medium ml-1">Resend</span>
          </button>
        </div>
      </motion.div>
    </div>
  );
};

export default VerifyOTP;
