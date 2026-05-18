import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import {
  Users, Briefcase, Shield, Brain,
  CheckCircle, UserSearch, Cpu,
} from "lucide-react";

// ── Floating info cards (overlaid on hero photo) ──────────────────────────────

const INFO_CARDS = [
  {
    icon:    UserSearch,
    title:   "For Recruiters",
    desc:    "AI helps recruiters find the most relevant candidates quickly.",
    pos:     "top-6 left-[8%]",
    iconBg:  "bg-violet-100",
    iconCls: "text-violet-600",
    delay:   0.5,
  },
  {
    icon:    Users,
    title:   "For Job Seekers",
    desc:    "AI helps job seekers discover the best opportunities.",
    pos:     "top-6 right-[4%]",
    iconBg:  "bg-blue-100",
    iconCls: "text-blue-600",
    delay:   0.65,
  },
  {
    icon:    CheckCircle,
    title:   "Better Matches",
    desc:    "Higher quality matches, better conversations, better outcomes.",
    pos:     "bottom-[14%] left-[32%]",
    iconBg:  "bg-emerald-100",
    iconCls: "text-emerald-600",
    delay:   0.8,
  },
];

// ── Bottom feature strip ───────────────────────────────────────────────────────

const FEATURES = [
  {
    icon:  Users,
    title: "AI for Job Seekers",
    desc:  "Discover jobs that match your skills and goals.",
  },
  {
    icon:  UserSearch,
    title: "AI for Recruiters",
    desc:  "Find the best candidates faster and smarter.",
  },
  {
    icon:  Brain,
    title: "AI Matching",
    desc:  "Smart algorithms connect the right people with the right opportunities.",
  },
  {
    icon:  Shield,
    title: "Trusted Platform",
    desc:  "Secure. Reliable. Effective.",
  },
];

// ── Component ─────────────────────────────────────────────────────────────────

const Landing = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen" style={{ background: "linear-gradient(160deg, #EDF2FB 0%, #E8F0FE 40%, #F8FAFF 100%)" }}>

      {/* ── Navbar ── */}
      <nav
        className="bg-white border-b border-blue-100 sticky top-0 z-50"
        style={{ boxShadow: "0 1px 4px 0 rgb(0 0 0 / 0.08)" }}
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8
                        flex items-center justify-between h-[70px] sm:h-[80px] lg:h-[90px]">
          {/* Logo */}
          <div className="flex items-center flex-shrink-0">
            <img
              src="/logo.png"
              alt="NewAgeNaukri"
              className="h-[55px] sm:h-[65px] lg:h-[72px] w-auto object-contain"
            />
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2 sm:gap-3">
            <button
              onClick={() => navigate("/auth/login")}
              className="text-sm font-medium text-slate-600 hover:text-primary
                         px-4 py-2 rounded-lg hover:bg-blue-50 transition"
            >
              Login
            </button>
            <button
              onClick={() => navigate("/auth/signup")}
              className="text-sm font-semibold bg-primary text-white
                         px-4 sm:px-6 py-2.5 rounded-lg hover:bg-primary/90 transition"
              style={{ boxShadow: "0 2px 8px 0 hsl(221 83% 53% / 0.35)" }}
            >
              Sign Up Free
            </button>
          </div>
        </div>
      </nav>

      {/* ── Hero ── */}
      <section className="max-w-7xl mx-auto px-6 pt-14 pb-10
                          grid grid-cols-1 lg:grid-cols-[45%_55%] gap-8 items-center">

        {/* ── LEFT — Text ── */}
        <motion.div
          initial={{ opacity: 0, x: -24 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.55 }}
          className="py-6"
        >
          {/* Headline */}
          <h1 className="text-[3.4rem] sm:text-[4rem] font-extrabold text-foreground
                         leading-[1.08] tracking-tight mb-5">
            Connecting Talent<br />
            with{" "}
            <span className="text-primary">Opportunity</span>
          </h1>

          {/* Subtitle */}
          <p className="text-lg text-slate-600 mb-9 leading-relaxed">
            <span className="font-bold text-primary">AI-Powered</span>{" "}
            matching that connects<br />
            the right talent to the right roles.
          </p>

          {/* CTA Buttons */}
          <div className="flex flex-wrap gap-4 mb-14">
            <motion.button
              whileHover={{ scale: 1.02, y: -1 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => navigate("/auth/login")}
              className="px-9 py-3.5 bg-primary text-white rounded-xl
                         font-semibold text-base hover:bg-primary/90 transition"
              style={{ boxShadow: "0 4px 14px 0 hsl(221 83% 53% / 0.4)" }}
            >
              Find Jobs
            </motion.button>
            <motion.button
              whileHover={{ scale: 1.02, y: -1 }}
              whileTap={{ scale: 0.98 }}
              onClick={() => navigate("/company")}
              className="px-9 py-3.5 border-2 border-slate-300 text-foreground
                         rounded-xl font-semibold text-base
                         hover:border-primary/50 hover:bg-blue-50/50 transition bg-white"
            >
              Post a Job
            </motion.button>
          </div>

          {/* Feature icons — 4 items */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-x-6 gap-y-5">
            {FEATURES.map(({ icon: Icon, title, desc }, i) => (
              <motion.div
                key={title}
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.3 + i * 0.08 }}
              >
                <div className="w-10 h-10 rounded-xl bg-white border border-blue-100
                                flex items-center justify-center mb-2.5"
                     style={{ boxShadow: "0 1px 4px 0 rgb(0 0 0 / 0.06)" }}>
                  <Icon className="w-5 h-5 text-primary" />
                </div>
                <p className="text-sm font-bold text-foreground mb-0.5">{title}</p>
                <p className="text-xs text-slate-500 leading-snug">{desc}</p>
              </motion.div>
            ))}
          </div>
        </motion.div>

        {/* ── RIGHT — Photo + overlaid cards ── */}
        <motion.div
          initial={{ opacity: 0, x: 24 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.55, delay: 0.1 }}
          className="relative h-[560px]"
        >
          {/* Hero photo — save your image as /public/hero.jpg */}
          <div className="absolute inset-0 rounded-3xl overflow-hidden
                          bg-gradient-to-br from-blue-100 via-blue-50 to-slate-100">
            <img
              src="/hero.jpg"
              alt="Professionals connecting"
              className="w-full h-full object-cover object-center"
              onError={(e) => { (e.target as HTMLImageElement).style.display = "none"; }}
            />
          </div>

          {/* ── Dashed connector lines (SVG) ── */}
          <svg className="absolute inset-0 w-full h-full pointer-events-none z-10"
               viewBox="0 0 600 560" fill="none">
            {/* Card 1 → center */}
            <path d="M 160 110 Q 230 200 300 260" stroke="#93C5FD" strokeWidth="1.5"
                  strokeDasharray="5 4" fill="none" opacity="0.7" />
            {/* Card 2 → center */}
            <path d="M 450 120 Q 390 200 335 255" stroke="#93C5FD" strokeWidth="1.5"
                  strokeDasharray="5 4" fill="none" opacity="0.7" />
            {/* center → Card 3 */}
            <path d="M 310 310 Q 320 380 360 420" stroke="#6EE7B7" strokeWidth="1.5"
                  strokeDasharray="5 4" fill="none" opacity="0.7" />
            {/* Arrowhead for line 1 */}
            <polygon points="224,196 234,208 218,205" fill="#93C5FD" opacity="0.7" />
            {/* Arrowhead for line 2 */}
            <polygon points="390,197 378,206 391,212" fill="#93C5FD" opacity="0.7" />
          </svg>

          {/* ── AI-Powered Matching — center circle ── */}
          <motion.div
            initial={{ opacity: 0, scale: 0.8 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ delay: 0.45 }}
            className="absolute z-20 flex flex-col items-center"
            style={{ top: "38%", left: "50%", transform: "translate(-50%, -50%)" }}
          >
            <div className="w-24 h-24 rounded-full bg-white border-2 border-blue-200
                            flex items-center justify-center mb-2"
                 style={{ boxShadow: "0 8px 32px 0 hsl(221 83% 53% / 0.18)" }}>
              <div className="w-16 h-16 rounded-full bg-blue-50 border border-blue-100
                              flex items-center justify-center">
                <Cpu className="w-7 h-7 text-primary" />
              </div>
            </div>
            <div className="bg-white/90 backdrop-blur-sm rounded-lg px-3 py-1.5 text-center"
                 style={{ boxShadow: "0 2px 8px 0 rgb(0 0 0 / 0.08)" }}>
              <p className="text-xs font-bold text-primary leading-snug">AI-Powered<br />Matching</p>
            </div>
          </motion.div>

          {/* ── Floating info cards ── */}
          {INFO_CARDS.map((card) => (
            <motion.div
              key={card.title}
              initial={{ opacity: 0, y: -12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: card.delay }}
              className={`absolute z-20 bg-white rounded-2xl p-3.5 w-48 ${card.pos}`}
              style={{ boxShadow: "0 4px 20px 0 rgb(0 0 0 / 0.1)" }}
            >
              <div className="flex items-start gap-2.5">
                <div className={`w-9 h-9 rounded-lg ${card.iconBg} flex items-center justify-center shrink-0`}>
                  <card.icon className={`w-4.5 h-4.5 ${card.iconCls}`} style={{ width: 18, height: 18 }} />
                </div>
                <div>
                  <p className="text-sm font-bold text-foreground leading-none mb-1">{card.title}</p>
                  <p className="text-[11px] text-slate-500 leading-snug">{card.desc}</p>
                </div>
              </div>
            </motion.div>
          ))}

          {/* Small plus accents */}
          <span className="absolute top-[28%] left-[6%] text-blue-300 text-2xl font-light select-none z-10">+</span>
          <span className="absolute bottom-[30%] right-[52%] text-blue-200 text-xl font-light select-none z-10">+</span>
          <span className="absolute top-[52%] right-[2%] text-blue-200 text-2xl font-light select-none z-10">+</span>
        </motion.div>

      </section>

      <footer className="text-center py-5 text-xs text-slate-400 border-t border-blue-100">
        NewAgeNaukri © {new Date().getFullYear()} · AI-powered job applications, on autopilot
      </footer>
    </div>
  );
};

export default Landing;
