import { useCallback, useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { useNavigate } from "react-router-dom";
import {
  Award,
  BookOpen,
  Briefcase,
  CheckCircle,
  ChevronDown,
  ChevronUp,
  Code,
  Download,
  ExternalLink,
  FolderOpen,
  GraduationCap,
  Loader2,
  Plus,
  Trash2,
  Trophy,
  Upload,
  User,
  X,
  Zap,
} from "lucide-react";

import AnimatedBackground from "@/components/AnimatedBackground";
import ConfirmDialog      from "@/components/ConfirmDialog";
import GlowButton         from "@/components/GlowButton";
import { clearToken, getAuthHeaders, getMe, logout } from "@/lib/auth";
import {
  CVData,
  WorkExperience,
  Education,
  Project,
  Certification,
  Achievement,
  downloadCVPDF,
  emptyCVData,
  getCVBuilder,
  parseCVFile,
  saveCVBuilder,
} from "@/lib/cvBuilderApi";

// ── Shared style strings ───────────────────────────────────────────────────────
const INP =
  "w-full px-3 py-2.5 rounded-lg bg-input border border-border text-foreground " +
  "placeholder:text-muted-foreground focus:outline-none focus:ring-2 " +
  "focus:ring-primary/50 transition text-sm";
const LABEL = "block text-xs font-medium text-muted-foreground mb-1";

// ── ID generator ──────────────────────────────────────────────────────────────
const genId = (prefix: string) =>
  `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2, 6)}`;

// ── Section wrapper ───────────────────────────────────────────────────────────
interface SectionCardProps {
  icon:       React.ReactNode;
  title:      string;
  subtitle?:  string;
  badge?:     string;
  children:   React.ReactNode;
  collapsible?: boolean;
  defaultOpen?: boolean;
}

const SectionCard = ({
  icon, title, subtitle, badge, children, collapsible, defaultOpen = true,
}: SectionCardProps) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      className="glass-card rounded-2xl overflow-hidden"
    >
      <button
        type="button"
        className="w-full flex items-center gap-3 p-5 text-left"
        onClick={() => collapsible && setOpen(o => !o)}
      >
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-blue-600/20 to-violet-600/20 border border-primary/20 flex items-center justify-center flex-shrink-0">
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-foreground">{title}</h2>
            {badge && (
              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-primary/20 text-primary">
                {badge}
              </span>
            )}
          </div>
          {subtitle && <p className="text-xs text-muted-foreground">{subtitle}</p>}
        </div>
        {collapsible && (
          <div className="text-muted-foreground">
            {open ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </div>
        )}
      </button>

      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="body"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="px-5 pb-5 space-y-4">{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};

// ── Tag input (skills) ────────────────────────────────────────────────────────
interface TagInputProps {
  tags:       string[];
  onAdd:      (tag: string) => void;
  onRemove:   (tag: string) => void;
  placeholder: string;
  color?:     string;
}

const TagInput = ({ tags, onAdd, onRemove, placeholder, color = "primary" }: TagInputProps) => {
  const [val, setVal] = useState("");
  const submit = () => {
    const t = val.trim().replace(/,$/, "");
    if (t && !tags.includes(t)) onAdd(t);
    setVal("");
  };
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-2">
        {tags.map(tag => (
          <span
            key={tag}
            className="flex items-center gap-1 px-2.5 py-1 rounded-md bg-primary/15 text-primary text-xs font-medium border border-primary/20"
          >
            {tag}
            <button
              type="button"
              onClick={() => onRemove(tag)}
              className="hover:text-red-400 transition"
            >
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          value={val}
          onChange={e => setVal(e.target.value)}
          onKeyDown={e => {
            if (e.key === "Enter" || e.key === ",") { e.preventDefault(); submit(); }
          }}
          placeholder={placeholder}
          className={INP + " flex-1"}
        />
        <button
          type="button"
          onClick={submit}
          className="px-3 py-2 rounded-lg bg-primary/20 hover:bg-primary/30 text-primary text-xs font-medium transition border border-primary/20"
        >
          Add
        </button>
      </div>
    </div>
  );
};

// ── Main page ─────────────────────────────────────────────────────────────────
const CVBuilder = () => {
  const navigate    = useNavigate();
  const fileRef     = useRef<HTMLInputElement>(null);

  const [cv,         setCv]        = useState<CVData>(emptyCVData());
  const [uploading,    setUploading]   = useState(false);
  const [saving,       setSaving]      = useState(false);
  const [saved,        setSaved]       = useState(false);
  const [downloading,  setDownload]    = useState(false);
  const [dragOver,     setDragOver]    = useState(false);
  const [uploadErr,    setUploadErr]   = useState("");
  const [saveErr,      setSaveErr]     = useState("");
  const [user,         setUser]        = useState<{ first_name: string; last_name: string; email: string } | null>(null);
  const [showDeleteDlg,setDeleteDlg]   = useState(false);
  const [deleting,     setDeleting]    = useState(false);
  const [deleteErr,    setDeleteErr]   = useState("");

  // Per work-experience bullet input
  const [bulletInputs, setBulletInputs] = useState<Record<string, string>>({});

  // Load existing CV data on mount (editing case)
  useEffect(() => {
    getMe().then(setUser).catch(() => {});
    getCVBuilder()
      .then(data => {
        setCv(data);
        const bi: Record<string, string> = {};
        (data.work_experience || []).forEach(e => { bi[e.id] = ""; });
        setBulletInputs(bi);
      })
      .catch(() => {/* 404 = new user, keep empty form */});
  }, []);

  // ── Contact helpers ──────────────────────────────────────────────────────────
  const setContact = (key: keyof CVData["contact"], val: string) =>
    setCv(p => ({ ...p, contact: { ...p.contact, [key]: val } }));

  // ── Work experience helpers ──────────────────────────────────────────────────
  const addExp = () => {
    const id = genId("exp");
    setCv(p => ({
      ...p,
      work_experience: [...p.work_experience, {
        id, title: "", company: "", location: "",
        start_date: "", end_date: "", currently_working: false, bullets: [],
      }],
    }));
    setBulletInputs(b => ({ ...b, [id]: "" }));
  };

  const removeExp = (id: string) => {
    setCv(p => ({ ...p, work_experience: p.work_experience.filter(e => e.id !== id) }));
    setBulletInputs(b => { const n = { ...b }; delete n[id]; return n; });
  };

  const updateExp = <K extends keyof WorkExperience>(id: string, key: K, val: WorkExperience[K]) =>
    setCv(p => ({
      ...p,
      work_experience: p.work_experience.map(e => e.id === id ? { ...e, [key]: val } : e),
    }));

  const addBullet = (expId: string) => {
    const text = (bulletInputs[expId] || "").trim();
    if (!text) return;
    updateExp(expId, "bullets", [
      ...(cv.work_experience.find(e => e.id === expId)?.bullets || []),
      text,
    ]);
    setBulletInputs(b => ({ ...b, [expId]: "" }));
  };

  const removeBullet = (expId: string, idx: number) =>
    updateExp(
      expId,
      "bullets",
      (cv.work_experience.find(e => e.id === expId)?.bullets || []).filter((_, i) => i !== idx),
    );

  // ── Education helpers ────────────────────────────────────────────────────────
  const addEdu = () =>
    setCv(p => ({
      ...p,
      education: [...p.education, {
        id: genId("edu"), degree: "", institution: "",
        start_year: "", end_year: "", gpa: "", relevant_coursework: "",
      }],
    }));

  const removeEdu = (id: string) =>
    setCv(p => ({ ...p, education: p.education.filter(e => e.id !== id) }));

  const updateEdu = <K extends keyof Education>(id: string, key: K, val: Education[K]) =>
    setCv(p => ({
      ...p,
      education: p.education.map(e => e.id === id ? { ...e, [key]: val } : e),
    }));

  // ── Project helpers ──────────────────────────────────────────────────────────
  const addProject = () =>
    setCv(p => ({
      ...p,
      projects: [...p.projects, {
        id: genId("proj"), name: "", description: "", tech_stack: "", outcome: "", link: "",
      }],
    }));

  const removeProject = (id: string) =>
    setCv(p => ({ ...p, projects: p.projects.filter(pr => pr.id !== id) }));

  const updateProject = <K extends keyof Project>(id: string, key: K, val: Project[K]) =>
    setCv(p => ({
      ...p,
      projects: p.projects.map(pr => pr.id === id ? { ...pr, [key]: val } : pr),
    }));

  // ── Certification helpers ────────────────────────────────────────────────────
  const addCert = () =>
    setCv(p => ({
      ...p,
      certifications: [...p.certifications, { id: genId("cert"), name: "", issuer: "", year: "" }],
    }));

  const removeCert = (id: string) =>
    setCv(p => ({ ...p, certifications: p.certifications.filter(c => c.id !== id) }));

  const updateCert = <K extends keyof Certification>(id: string, key: K, val: Certification[K]) =>
    setCv(p => ({
      ...p,
      certifications: p.certifications.map(c => c.id === id ? { ...c, [key]: val } : c),
    }));

  // ── Achievement helpers ──────────────────────────────────────────────────────
  const addAch = () =>
    setCv(p => ({
      ...p,
      achievements: [...p.achievements, { id: genId("ach"), description: "" }],
    }));

  const removeAch = (id: string) =>
    setCv(p => ({ ...p, achievements: p.achievements.filter(a => a.id !== id) }));

  const updateAch = (id: string, val: string) =>
    setCv(p => ({
      ...p,
      achievements: p.achievements.map(a => a.id === id ? { ...a, description: val } : a),
    }));

  // ── Skills helpers ───────────────────────────────────────────────────────────
  const addSkill = (type: "technical" | "soft", tag: string) =>
    setCv(p => ({ ...p, skills: { ...p.skills, [type]: [...p.skills[type], tag] } }));

  const removeSkill = (type: "technical" | "soft", tag: string) =>
    setCv(p => ({ ...p, skills: { ...p.skills, [type]: p.skills[type].filter(s => s !== tag) } }));

  // ── File upload ──────────────────────────────────────────────────────────────
  const handleFile = useCallback(async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setUploadErr("Only PDF files are supported.");
      return;
    }
    setUploading(true);
    setUploadErr("");
    try {
      const parsed = await parseCVFile(file);
      setCv(parsed);
      const bi: Record<string, string> = {};
      (parsed.work_experience || []).forEach(e => { bi[e.id] = ""; });
      setBulletInputs(bi);
    } catch (err: unknown) {
      setUploadErr(
        err instanceof Error
          ? err.message
          : "Failed to parse CV. Please fill the form manually.",
      );
    } finally {
      setUploading(false);
    }
  }, []);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  // ── Save ─────────────────────────────────────────────────────────────────────
  const handleSave = async () => {
    setSaveErr("");

    if (!cv.contact.name.trim()) {
      setSaveErr("Please enter your full name in the Contact section.");
      document.getElementById("contact-section")?.scrollIntoView({ behavior: "smooth" });
      return;
    }
    if (!cv.education.length || !cv.education[0].degree.trim()) {
      setSaveErr("Please add at least one education entry.");
      document.getElementById("edu-section")?.scrollIntoView({ behavior: "smooth" });
      return;
    }
    if (!cv.is_fresher && !cv.work_experience.length) {
      setSaveErr(
        "Please add at least one work experience, or toggle 'I'm a fresher' if you have none.",
      );
      document.getElementById("exp-section")?.scrollIntoView({ behavior: "smooth" });
      return;
    }

    setSaving(true);
    try {
      await saveCVBuilder(cv);
      setSaved(true);
      setTimeout(() => navigate("/profile-setup"), 2000);
    } catch (err: unknown) {
      setSaveErr(err instanceof Error ? err.message : "Save failed. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  const handleDownload = async () => {
    setDownload(true);
    try {
      await downloadCVPDF();
    } catch (err: unknown) {
      setSaveErr(err instanceof Error ? err.message : "Download failed.");
    } finally {
      setDownload(false);
    }
  };

  const handleDeleteAccount = async () => {
    setDeleting(true);
    setDeleteErr("");
    try {
      const API = import.meta.env.VITE_API_URL;
      const res  = await fetch(`${API}/api/auth/account`, {
        method:  "DELETE",
        headers: getAuthHeaders(),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail ?? "Delete failed.");
      }
      clearToken();
      navigate("/");
    } catch (err: unknown) {
      setDeleteErr(err instanceof Error ? err.message : "Delete failed. Please try again.");
      setDeleting(false);
      setDeleteDlg(false);
    }
  };

  // ── UI ───────────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen">
      <AnimatedBackground />

      {/* ── Navbar ── */}
      <motion.nav
        initial={{ y: -60, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="fixed top-0 left-0 right-0 z-50 glass-card border-b border-glass-border px-4 sm:px-6 py-3"
      >
        <div className="max-w-5xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Zap className="w-5 h-5 text-primary" />
            <span className="text-base font-bold text-gradient">AutoApply AI</span>
          </div>
          {user && (
            <span className="text-sm text-muted-foreground hidden sm:block">
              Welcome, <span className="text-foreground font-medium">{user.first_name}</span>
            </span>
          )}
          <button
            onClick={() => { logout(); navigate("/"); }}
            className="text-xs text-muted-foreground hover:text-foreground border border-border px-3 py-1.5 rounded-lg transition"
          >
            Logout
          </button>
        </div>
      </motion.nav>

      {/* ── Page body ── */}
      <div className="pt-24 pb-20 px-4">
        <div className="max-w-3xl mx-auto space-y-5">

          {/* ── Header ── */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="text-center space-y-1 mb-2"
          >
            <h1 className="text-2xl sm:text-3xl font-bold text-gradient">Build Your Professional CV</h1>
            <p className="text-muted-foreground text-sm">
              Fill in your details below — we generate an ATS-optimised PDF ready for companies.
            </p>
          </motion.div>

          {/* ── Upload strip ── */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
          >
            <div
              className={`relative rounded-2xl border-2 border-dashed p-6 text-center cursor-pointer transition-all ${
                dragOver
                  ? "border-primary bg-primary/10"
                  : "border-border hover:border-primary/50 hover:bg-muted/20"
              }`}
              onDragOver={e => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={handleDrop}
              onClick={() => !uploading && fileRef.current?.click()}
            >
              <input
                ref={fileRef}
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={e => { const f = e.target.files?.[0]; if (f) handleFile(f); e.target.value = ""; }}
              />

              {uploading ? (
                <div className="flex flex-col items-center gap-2">
                  <Loader2 className="w-8 h-8 text-primary animate-spin" />
                  <p className="text-sm font-medium text-foreground">Groq is reading your CV…</p>
                  <p className="text-xs text-muted-foreground">Extracting all sections automatically</p>
                </div>
              ) : (
                <div className="flex flex-col items-center gap-2">
                  <Upload className="w-7 h-7 text-muted-foreground" />
                  <p className="text-sm font-medium text-foreground">
                    Upload your existing CV for AI auto-fill
                  </p>
                  <p className="text-xs text-muted-foreground">
                    Drag &amp; drop or click to browse · PDF only · Max 10 MB
                  </p>
                </div>
              )}
            </div>

            <AnimatePresence>
              {uploadErr && (
                <motion.p
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="mt-2 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2"
                >
                  {uploadErr}
                </motion.p>
              )}
            </AnimatePresence>
          </motion.div>

          {/* ── Fresher toggle ── */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.08 }}
            className="glass-card rounded-2xl px-5 py-4 flex items-center justify-between gap-4"
          >
            <div>
              <p className="text-sm font-medium text-foreground">I'm a fresher / no work experience</p>
              <p className="text-xs text-muted-foreground mt-0.5">
                Turns off the Work Experience section and emphasises Projects.
              </p>
            </div>
            <button
              type="button"
              onClick={() => setCv(p => ({ ...p, is_fresher: !p.is_fresher }))}
              className={`relative w-12 h-6 rounded-full transition-colors flex-shrink-0 ${
                cv.is_fresher ? "bg-primary" : "bg-muted"
              }`}
            >
              <div
                className={`absolute top-1 left-1 w-4 h-4 rounded-full bg-white shadow transition-transform ${
                  cv.is_fresher ? "translate-x-6" : "translate-x-0"
                }`}
              />
            </button>
          </motion.div>

          {/* ── 1. Contact Information ── */}
          <div id="contact-section">
            <SectionCard
              icon={<User className="w-4 h-4 text-primary" />}
              title="Contact Information"
              subtitle="Name, phone, email, and links"
            >
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {(
                  [
                    { key: "name",      label: "Full Name *",       placeholder: "Rahul Sharma", type: "text" },
                    { key: "phone",     label: "Phone Number",      placeholder: "+91 98765 43210", type: "tel" },
                    { key: "email",     label: "Email Address",     placeholder: "rahul@email.com", type: "email" },
                    { key: "location",  label: "City, Country",     placeholder: "Bengaluru, India", type: "text" },
                    { key: "linkedin",  label: "LinkedIn URL",      placeholder: "https://linkedin.com/in/...", type: "url" },
                    { key: "github",    label: "GitHub URL",        placeholder: "https://github.com/...", type: "url" },
                    { key: "portfolio", label: "Portfolio / Website", placeholder: "https://mysite.com", type: "url" },
                  ] as { key: keyof CVData["contact"]; label: string; placeholder: string; type: string }[]
                ).map(({ key, label, placeholder, type }) => (
                  <div key={key} className={key === "name" ? "sm:col-span-2" : ""}>
                    <label className={LABEL}>{label}</label>
                    <input
                      type={type}
                      value={cv.contact[key] || ""}
                      onChange={e => setContact(key, e.target.value)}
                      placeholder={placeholder}
                      className={INP}
                    />
                  </div>
                ))}
              </div>
            </SectionCard>
          </div>

          {/* ── 2. Professional Summary ── */}
          <SectionCard
            icon={<BookOpen className="w-4 h-4 text-primary" />}
            title="Professional Summary"
            subtitle="2–4 lines about who you are and what you bring"
          >
            <textarea
              value={cv.summary}
              onChange={e => setCv(p => ({ ...p, summary: e.target.value }))}
              rows={4}
              placeholder="Results-driven Data Analyst with 3+ years of experience transforming raw data into actionable insights…"
              className={INP + " resize-none"}
            />
            <p className="text-xs text-muted-foreground text-right">{cv.summary.length} chars</p>
          </SectionCard>

          {/* ── 3. Work Experience ── */}
          <AnimatePresence>
            {!cv.is_fresher && (
              <motion.div
                id="exp-section"
                key="work-exp"
                initial={{ opacity: 0, height: 0 }}
                animate={{ opacity: 1, height: "auto" }}
                exit={{ opacity: 0, height: 0 }}
                transition={{ duration: 0.25 }}
              >
                <SectionCard
                  icon={<Briefcase className="w-4 h-4 text-primary" />}
                  title="Work Experience"
                  subtitle="Most recent first — include all jobs, internships, and contracts"
                >
                  <div className="space-y-5">
                    {cv.work_experience.map((exp, i) => (
                      <div key={exp.id} className="bg-muted/20 rounded-xl p-4 space-y-3 border border-border">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                            Experience {i + 1}
                          </span>
                          <button
                            type="button"
                            onClick={() => removeExp(exp.id)}
                            className="text-muted-foreground hover:text-red-400 transition"
                          >
                            <X className="w-4 h-4" />
                          </button>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                          <div>
                            <label className={LABEL}>Job Title *</label>
                            <input value={exp.title} onChange={e => updateExp(exp.id, "title", e.target.value)}
                              placeholder="Data Analyst" className={INP} />
                          </div>
                          <div>
                            <label className={LABEL}>Company *</label>
                            <input value={exp.company} onChange={e => updateExp(exp.id, "company", e.target.value)}
                              placeholder="Infosys Limited" className={INP} />
                          </div>
                          <div>
                            <label className={LABEL}>Location</label>
                            <input value={exp.location} onChange={e => updateExp(exp.id, "location", e.target.value)}
                              placeholder="Bengaluru, India" className={INP} />
                          </div>
                          <div className="flex items-end gap-2">
                            <div className="flex-1">
                              <label className={LABEL}>Start Date</label>
                              <input value={exp.start_date} onChange={e => updateExp(exp.id, "start_date", e.target.value)}
                                placeholder="Jul 2022" className={INP} />
                            </div>
                            <div className="flex-1">
                              <label className={LABEL}>End Date</label>
                              <input
                                value={exp.currently_working ? "Present" : exp.end_date}
                                onChange={e => updateExp(exp.id, "end_date", e.target.value)}
                                disabled={exp.currently_working}
                                placeholder="Dec 2023"
                                className={INP + (exp.currently_working ? " opacity-50 cursor-not-allowed" : "")}
                              />
                            </div>
                          </div>
                          <div className="sm:col-span-2 flex items-center gap-2">
                            <input
                              type="checkbox"
                              id={`current-${exp.id}`}
                              checked={exp.currently_working}
                              onChange={e => updateExp(exp.id, "currently_working", e.target.checked)}
                              className="w-4 h-4 accent-primary"
                            />
                            <label htmlFor={`current-${exp.id}`} className="text-xs text-muted-foreground cursor-pointer">
                              I currently work here
                            </label>
                          </div>
                        </div>

                        {/* Bullets */}
                        <div>
                          <label className={LABEL}>Achievement Bullets (use numbers: "increased X by 30%")</label>
                          <div className="space-y-1.5 mb-2">
                            {exp.bullets.map((b, bi) => (
                              <div key={bi} className="flex items-start gap-2 group">
                                <span className="text-primary mt-2.5 text-xs">•</span>
                                <span className="flex-1 text-sm text-foreground bg-muted/30 rounded-lg px-3 py-2">{b}</span>
                                <button
                                  type="button"
                                  onClick={() => removeBullet(exp.id, bi)}
                                  className="mt-2 text-muted-foreground hover:text-red-400 opacity-0 group-hover:opacity-100 transition"
                                >
                                  <X className="w-3 h-3" />
                                </button>
                              </div>
                            ))}
                          </div>
                          <div className="flex gap-2">
                            <input
                              value={bulletInputs[exp.id] || ""}
                              onChange={e => setBulletInputs(b => ({ ...b, [exp.id]: e.target.value }))}
                              onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); addBullet(exp.id); } }}
                              placeholder="Optimised SQL queries, reducing report time by 35%…"
                              className={INP + " flex-1"}
                            />
                            <button
                              type="button"
                              onClick={() => addBullet(exp.id)}
                              className="px-3 py-2 rounded-lg bg-primary/20 hover:bg-primary/30 text-primary text-xs font-medium transition border border-primary/20"
                            >
                              Add
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}

                    <button
                      type="button"
                      onClick={addExp}
                      className="w-full py-2.5 rounded-xl border border-dashed border-primary/30 text-primary text-sm font-medium hover:bg-primary/5 transition flex items-center justify-center gap-2"
                    >
                      <Plus className="w-4 h-4" /> Add Work Experience
                    </button>
                  </div>
                </SectionCard>
              </motion.div>
            )}
          </AnimatePresence>

          {/* ── 4. Education ── */}
          <div id="edu-section">
            <SectionCard
              icon={<GraduationCap className="w-4 h-4 text-primary" />}
              title="Education"
              subtitle="Degrees, diplomas — most recent first"
            >
              <div className="space-y-5">
                {cv.education.map((edu, i) => (
                  <div key={edu.id} className="bg-muted/20 rounded-xl p-4 space-y-3 border border-border">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                        Education {i + 1}
                      </span>
                      {cv.education.length > 1 && (
                        <button type="button" onClick={() => removeEdu(edu.id)}
                          className="text-muted-foreground hover:text-red-400 transition">
                          <X className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div className="sm:col-span-2">
                        <label className={LABEL}>Degree / Qualification *</label>
                        <input value={edu.degree} onChange={e => updateEdu(edu.id, "degree", e.target.value)}
                          placeholder="B.Tech in Computer Science Engineering" className={INP} />
                      </div>
                      <div className="sm:col-span-2">
                        <label className={LABEL}>Institution *</label>
                        <input value={edu.institution} onChange={e => updateEdu(edu.id, "institution", e.target.value)}
                          placeholder="NIT Warangal" className={INP} />
                      </div>
                      <div>
                        <label className={LABEL}>Start Year</label>
                        <input value={edu.start_year} onChange={e => updateEdu(edu.id, "start_year", e.target.value)}
                          placeholder="2018" className={INP} />
                      </div>
                      <div>
                        <label className={LABEL}>End Year (or expected)</label>
                        <input value={edu.end_year} onChange={e => updateEdu(edu.id, "end_year", e.target.value)}
                          placeholder="2022" className={INP} />
                      </div>
                      <div>
                        <label className={LABEL}>GPA / CGPA (if strong)</label>
                        <input value={edu.gpa} onChange={e => updateEdu(edu.id, "gpa", e.target.value)}
                          placeholder="8.4 / 10" className={INP} />
                      </div>
                      <div>
                        <label className={LABEL}>Relevant Coursework</label>
                        <input value={edu.relevant_coursework}
                          onChange={e => updateEdu(edu.id, "relevant_coursework", e.target.value)}
                          placeholder="Data Structures, DBMS, ML" className={INP} />
                      </div>
                    </div>
                  </div>
                ))}
                <button type="button" onClick={addEdu}
                  className="w-full py-2.5 rounded-xl border border-dashed border-primary/30 text-primary text-sm font-medium hover:bg-primary/5 transition flex items-center justify-center gap-2">
                  <Plus className="w-4 h-4" /> Add Education
                </button>
              </div>
            </SectionCard>
          </div>

          {/* ── 5. Skills ── */}
          <SectionCard
            icon={<Code className="w-4 h-4 text-primary" />}
            title="Skills"
            subtitle="Press Enter or comma to add each skill"
          >
            <div className="space-y-4">
              <div>
                <label className={LABEL + " mb-2"}>Technical Skills</label>
                <TagInput
                  tags={cv.skills.technical}
                  onAdd={t => addSkill("technical", t)}
                  onRemove={t => removeSkill("technical", t)}
                  placeholder="Python, SQL, Power BI… (Enter to add)"
                />
              </div>
              <div>
                <label className={LABEL + " mb-2"}>Soft Skills</label>
                <TagInput
                  tags={cv.skills.soft}
                  onAdd={t => addSkill("soft", t)}
                  onRemove={t => removeSkill("soft", t)}
                  placeholder="Communication, Leadership… (Enter to add)"
                />
              </div>
            </div>
          </SectionCard>

          {/* ── 6. Projects ── */}
          <SectionCard
            icon={<FolderOpen className="w-4 h-4 text-primary" />}
            title="Projects"
            subtitle="Important for students and tech roles"
            badge={cv.is_fresher ? "Required for freshers" : undefined}
          >
            <div className="space-y-4">
              {cv.projects.map((proj, i) => (
                <div key={proj.id} className="bg-muted/20 rounded-xl p-4 space-y-3 border border-border">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      Project {i + 1}
                    </span>
                    <button type="button" onClick={() => removeProject(proj.id)}
                      className="text-muted-foreground hover:text-red-400 transition">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className={LABEL}>Project Name</label>
                      <input value={proj.name} onChange={e => updateProject(proj.id, "name", e.target.value)}
                        placeholder="Customer Churn Predictor" className={INP} />
                    </div>
                    <div>
                      <label className={LABEL}>Tech Stack</label>
                      <input value={proj.tech_stack} onChange={e => updateProject(proj.id, "tech_stack", e.target.value)}
                        placeholder="Python, scikit-learn, Streamlit" className={INP} />
                    </div>
                    <div className="sm:col-span-2">
                      <label className={LABEL}>One-line Description</label>
                      <input value={proj.description} onChange={e => updateProject(proj.id, "description", e.target.value)}
                        placeholder="Predicts telecom customer churn using Random Forest" className={INP} />
                    </div>
                    <div className="sm:col-span-2">
                      <label className={LABEL}>Impact / Outcome</label>
                      <input value={proj.outcome} onChange={e => updateProject(proj.id, "outcome", e.target.value)}
                        placeholder="87% accuracy, deployed to 1,000+ users" className={INP} />
                    </div>
                    <div className="sm:col-span-2">
                      <label className={LABEL}>GitHub / Live Link (optional)</label>
                      <input value={proj.link} onChange={e => updateProject(proj.id, "link", e.target.value)}
                        placeholder="https://github.com/..." type="url" className={INP} />
                    </div>
                  </div>
                </div>
              ))}
              <button type="button" onClick={addProject}
                className="w-full py-2.5 rounded-xl border border-dashed border-primary/30 text-primary text-sm font-medium hover:bg-primary/5 transition flex items-center justify-center gap-2">
                <Plus className="w-4 h-4" /> Add Project
              </button>
            </div>
          </SectionCard>

          {/* ── 7. Certifications ── */}
          <SectionCard
            icon={<Award className="w-4 h-4 text-primary" />}
            title="Certifications & Courses"
            subtitle="Google, AWS, Coursera, etc."
            collapsible
          >
            <div className="space-y-3">
              {cv.certifications.map((cert, i) => (
                <div key={cert.id} className="bg-muted/20 rounded-xl p-3 border border-border">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                      Cert {i + 1}
                    </span>
                    <button type="button" onClick={() => removeCert(cert.id)}
                      className="text-muted-foreground hover:text-red-400 transition">
                      <X className="w-4 h-4" />
                    </button>
                  </div>
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                    <div className="sm:col-span-1">
                      <label className={LABEL}>Certification Name</label>
                      <input value={cert.name} onChange={e => updateCert(cert.id, "name", e.target.value)}
                        placeholder="Google Data Analytics" className={INP} />
                    </div>
                    <div>
                      <label className={LABEL}>Issuing Body</label>
                      <input value={cert.issuer} onChange={e => updateCert(cert.id, "issuer", e.target.value)}
                        placeholder="Google / Coursera" className={INP} />
                    </div>
                    <div>
                      <label className={LABEL}>Year</label>
                      <input value={cert.year} onChange={e => updateCert(cert.id, "year", e.target.value)}
                        placeholder="2023" className={INP} />
                    </div>
                  </div>
                </div>
              ))}
              <button type="button" onClick={addCert}
                className="w-full py-2.5 rounded-xl border border-dashed border-primary/30 text-primary text-sm font-medium hover:bg-primary/5 transition flex items-center justify-center gap-2">
                <Plus className="w-4 h-4" /> Add Certification
              </button>
            </div>
          </SectionCard>

          {/* ── 8. Achievements ── */}
          <SectionCard
            icon={<Trophy className="w-4 h-4 text-primary" />}
            title="Achievements & Awards"
            subtitle="Hackathons, scholarships, recognitions — optional but impactful"
            collapsible
          >
            <div className="space-y-2">
              {cv.achievements.map((ach, i) => (
                <div key={ach.id} className="flex gap-2">
                  <input
                    value={ach.description}
                    onChange={e => updateAch(ach.id, e.target.value)}
                    placeholder={`Achievement ${i + 1} — e.g. Winner, NIT Hackathon 2023`}
                    className={INP + " flex-1"}
                  />
                  <button type="button" onClick={() => removeAch(ach.id)}
                    className="text-muted-foreground hover:text-red-400 transition flex-shrink-0">
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ))}
              <button type="button" onClick={addAch}
                className="w-full py-2.5 rounded-xl border border-dashed border-primary/30 text-primary text-sm font-medium hover:bg-primary/5 transition flex items-center justify-center gap-2">
                <Plus className="w-4 h-4" /> Add Achievement
              </button>
            </div>
          </SectionCard>

          {/* ── Save / Download bar ── */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.1 }}
            className="glass-card rounded-2xl px-5 py-4 space-y-3"
          >
            <AnimatePresence>
              {saveErr && (
                <motion.p
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="text-sm text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2"
                >
                  {saveErr}
                </motion.p>
              )}
              {saved && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="flex items-center gap-2 text-sm text-green-400 bg-green-500/10 border border-green-500/20 rounded-lg px-3 py-2"
                >
                  <CheckCircle className="w-4 h-4 flex-shrink-0" />
                  CV saved! Your ATS PDF is ready. Heading to profile setup…
                </motion.div>
              )}
            </AnimatePresence>

            <div className="flex flex-col sm:flex-row gap-3">
              {saved && (
                <GlowButton
                  variant="orange"
                  onClick={handleDownload}
                  loading={downloading}
                  className="flex items-center gap-2"
                >
                  <Download className="w-4 h-4" />
                  Download ATS CV
                </GlowButton>
              )}
              {saved && (
                <button
                  type="button"
                  onClick={() => navigate("/profile-setup")}
                  className="flex items-center gap-2 px-4 py-2.5 rounded-lg border border-border text-muted-foreground hover:text-foreground transition text-sm"
                >
                  <ExternalLink className="w-4 h-4" />
                  Continue to Profile Setup
                </button>
              )}
              {!saved && (
                <GlowButton
                  onClick={handleSave}
                  loading={saving}
                  className="sm:ml-auto"
                >
                  {saving ? "Building your CV…" : "Build My CV →"}
                </GlowButton>
              )}
            </div>
          </motion.div>

          {/* ── Danger Zone ── */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ delay: 0.15 }}
            className="rounded-2xl border border-red-500/20 bg-red-500/5 px-5 py-4"
          >
            <div className="flex items-center justify-between gap-4 flex-wrap">
              <div>
                <p className="text-sm font-semibold text-red-400">Danger Zone</p>
                <p className="text-xs text-muted-foreground mt-0.5">
                  Permanently deletes your account, CV, all job history, and every file we hold.
                  This cannot be undone.
                </p>
              </div>
              <button
                type="button"
                onClick={() => { setDeleteErr(""); setDeleteDlg(true); }}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium
                           text-red-400 border border-red-500/30 hover:bg-red-500/10
                           transition flex-shrink-0"
              >
                <Trash2 className="w-4 h-4" />
                Delete Account
              </button>
            </div>

            <AnimatePresence>
              {deleteErr && (
                <motion.p
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0 }}
                  className="mt-3 text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2"
                >
                  {deleteErr}
                </motion.p>
              )}
            </AnimatePresence>
          </motion.div>

        </div>
      </div>

      {/* ── Delete Account confirmation dialog ── */}
      {showDeleteDlg && (
        <ConfirmDialog
          title="Delete Account"
          message="This will permanently erase your account, CV, all uploaded files, and your entire job application history. There is no way to recover this data."
          confirmLabel="Yes, delete everything"
          cancelLabel="Cancel"
          destructive
          loading={deleting}
          onConfirm={handleDeleteAccount}
          onCancel={() => { if (!deleting) setDeleteDlg(false); }}
        />
      )}
    </div>
  );
};

export default CVBuilder;
