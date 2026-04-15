import { motion } from "framer-motion";
import { useNavigate } from "react-router-dom";
import { Briefcase, ShieldCheck, Building2 } from "lucide-react";
import AnimatedBackground from "@/components/AnimatedBackground";

const portals = [
  {
    id:          "user",
    title:       "Job Seeker",
    subtitle:    "Find & auto-apply to jobs",
    icon:        Briefcase,
    gradient:    "from-[hsl(220,80%,50%)] to-[hsl(260,80%,60%)]",
    glow:        "glow-blue",
    route:       "/auth/login",
    comingSoon:  false,
  },
  {
    id:          "admin",
    title:       "Admin",
    subtitle:    "Platform management",
    icon:        ShieldCheck,
    gradient:    "from-[hsl(280,80%,45%)] to-[hsl(320,80%,55%)]",
    glow:        "glow-purple",
    route:       "/admin/login",
    comingSoon:  true,
  },
  {
    id:          "company",
    title:       "Company",
    subtitle:    "Post jobs & find talent",
    icon:        Building2,
    gradient:    "from-[hsl(160,70%,35%)] to-[hsl(180,70%,45%)]",
    glow:        "glow-green",
    route:       "/company/login",
    comingSoon:  true,
  },
];

const Landing = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen flex flex-col">
      <AnimatedBackground />

      {/* Header */}
      <header className="relative z-10 flex justify-center pt-12 pb-4">
        <motion.div
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y:   0 }}
          transition={{ duration: 0.5 }}
          className="text-center"
        >
          <h1 className="text-4xl sm:text-5xl font-extrabold text-gradient tracking-tight">
            AutoApply AI
          </h1>
          <p className="mt-2 text-muted-foreground text-sm sm:text-base">
            AI-powered job applications, on autopilot
          </p>
        </motion.div>
      </header>

      {/* Portal cards */}
      <main className="relative z-10 flex-1 flex items-center justify-center px-4 py-8">
        <div className="w-full max-w-4xl">
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.2 }}
            className="text-center text-muted-foreground text-sm mb-8"
          >
            Choose your portal to continue
          </motion.p>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
            {portals.map((portal, i) => (
              <motion.div
                key={portal.id}
                initial={{ opacity: 0, y: 40 }}
                animate={{ opacity: 1, y:  0 }}
                transition={{ delay: 0.15 * i, duration: 0.4 }}
                whileHover={!portal.comingSoon ? { scale: 1.04, y: -6 } : {}}
                whileTap={!portal.comingSoon ? { scale: 0.97 } : {}}
                onClick={() => !portal.comingSoon && navigate(portal.route)}
                className={`relative glass-card p-8 flex flex-col items-center text-center
                  rounded-2xl border border-border overflow-hidden
                  ${portal.comingSoon
                    ? "opacity-60 cursor-not-allowed"
                    : `cursor-pointer hover:${portal.glow} transition-all duration-300`
                  }`}
              >
                {/* Icon */}
                <div
                  className={`w-16 h-16 rounded-2xl mb-5 flex items-center justify-center
                    bg-gradient-to-br ${portal.gradient} shadow-lg`}
                >
                  <portal.icon className="w-8 h-8 text-white" />
                </div>

                <h2 className="text-xl font-bold text-foreground mb-1">{portal.title}</h2>
                <p className="text-sm text-muted-foreground">{portal.subtitle}</p>

                {/* Coming Soon overlay */}
                {portal.comingSoon && (
                  <div className="absolute inset-0 flex items-center justify-center
                                  bg-background/50 backdrop-blur-[2px] rounded-2xl">
                    <span className="px-4 py-1.5 rounded-full border border-border
                                     bg-muted text-xs font-semibold text-muted-foreground
                                     tracking-widest uppercase">
                      Coming Soon
                    </span>
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        </div>
      </main>

      <footer className="relative z-10 text-center py-4 text-xs text-muted-foreground/50">
        AutoApply AI © {new Date().getFullYear()}
      </footer>
    </div>
  );
};

export default Landing;
