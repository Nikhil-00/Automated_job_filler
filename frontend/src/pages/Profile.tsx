/**
 * Profile.tsx
 * ────────────
 * Full-featured candidate profile editor.
 *
 * Data sources:
 *   - /api/cv/builder      → structured CVData (experience, education, skills …)
 *   - /api/cv/profile      → flat profile.json (CTC, notice period, phone …)
 *
 * Actions:
 *   - Resume upload  → parseCVFile → saveCVBuilder (auto-fills all sections)
 *   - Inline edit    → saveCVBuilder + updateProfileData (per section)
 *   - Download CV    → downloadCVPDF (streams the ATS PDF)
 */

import {
  useCallback, useEffect, useRef, useState,
} from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  AlertCircle, BookOpen, Briefcase, CheckCircle, Code2,
  Download, FilePlus2, GraduationCap, Loader2, Pencil,
  Plus, Save, Trash2, Upload, User, X, Zap,
} from "lucide-react";
import { useNavigate, useLocation } from "react-router-dom";

import AnimatedBackground from "@/components/AnimatedBackground";
import Navbar             from "@/components/Navbar";
import { getMe, logout }  from "@/lib/auth";
import {
  CVData, Education, Project, WorkExperience,
  downloadCVPDF, emptyCVData, getCVBuilder,
  parseCVFile, saveCVBuilder,
} from "@/lib/cvBuilderApi";
import { getProfileData, updateProfileData } from "@/lib/mockApi";

// ── Types ─────────────────────────────────────────────────────────────────────

interface Compensation {
  current_salary:  string;
  expected_salary: string;
  notice_period:   string;
}

type DashUser = { first_name: string; last_name: string; email: string };
type EditSection = "personal" | "compensation" | "summary" | "skills" | null;

const NOTICE_OPTIONS = [
  "Immediate", "15 days", "30 days", "60 days", "90 days",
];

// ── Completion score ──────────────────────────────────────────────────────────

function calcCompletion(cv: CVData, comp: Compensation): number {
  let score = 0;
  if (cv.contact?.name)                            score += 10;
  if (cv.contact?.phone)                           score += 5;
  if (cv.contact?.email)                           score += 5;
  if (cv.contact?.location)                        score += 5;
  if (comp.current_salary)                         score += 10;
  if (comp.expected_salary)                        score += 10;
  if (cv.summary)                                  score += 10;
  if ((cv.work_experience?.length ?? 0) > 0)       score += 20;
  if ((cv.education?.length ?? 0) > 0)             score += 10;
  if ((cv.skills?.technical?.length ?? 0) > 0)     score += 10;
  if (cv.contact?.linkedin || cv.contact?.github)  score += 5;
  return Math.min(score, 100);
}

// ── UUID helper (fallback for older browsers / non-secure contexts) ───────────

const genId = (): string =>
  typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
    ? crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;

// ── Shared UI helpers ────────────────────────────────────────────────────────

const INPUT_CLS =
  "w-full px-3 py-2 rounded-lg border border-border bg-white text-sm " +
  "text-foreground placeholder:text-muted-foreground focus:outline-none " +
  "focus:ring-2 focus:ring-primary/40 transition";

const LABEL_CLS = "block text-xs font-semibold text-muted-foreground mb-1";

function SectionCard({
  icon: Icon, title, editing, onEdit, onSave, onCancel, saving, children,
}: {
  icon: React.ElementType;
  title: string;
  editing: boolean;
  onEdit: () => void;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="glass-card overflow-hidden">
      <div className="flex items-center justify-between px-5 py-4 border-b border-border">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
            <Icon className="w-4 h-4 text-primary" />
          </div>
          <h3 className="text-sm font-bold text-foreground">{title}</h3>
        </div>
        <div className="flex items-center gap-2">
          {editing ? (
            <>
              <button
                onClick={onCancel}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs
                           text-muted-foreground border border-border hover:bg-muted transition"
              >
                <X className="w-3.5 h-3.5" /> Cancel
              </button>
              <button
                onClick={onSave}
                disabled={saving}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold
                           bg-primary text-white hover:bg-primary/90 disabled:opacity-60 transition"
              >
                {saving
                  ? <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  : <Save className="w-3.5 h-3.5" />
                }
                Save
              </button>
            </>
          ) : (
            <button
              onClick={onEdit}
              className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs
                         text-muted-foreground border border-border hover:bg-muted
                         hover:text-foreground transition"
            >
              <Pencil className="w-3.5 h-3.5" /> Edit
            </button>
          )}
        </div>
      </div>
      <div className="p-5">{children}</div>
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <p className="text-sm text-muted-foreground italic py-2">{message}</p>
  );
}

// ── Work Experience form ──────────────────────────────────────────────────────

const EMPTY_EXP = (): WorkExperience => ({
  id: genId(), title: "", company: "", location: "",
  start_date: "", end_date: "", currently_working: false, bullets: [""],
});

function ExperienceForm({
  value, onChange, onRemoveBullet, onAddBullet,
}: {
  value: WorkExperience;
  onChange: (v: WorkExperience) => void;
  onRemoveBullet: (i: number) => void;
  onAddBullet: () => void;
}) {
  return (
    <div className="space-y-3 border border-border rounded-xl p-4 bg-muted/30">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={LABEL_CLS}>Job Title *</label>
          <input className={INPUT_CLS} value={value.title}
            onChange={e => onChange({ ...value, title: e.target.value })}
            placeholder="e.g. Software Engineer" />
        </div>
        <div>
          <label className={LABEL_CLS}>Company *</label>
          <input className={INPUT_CLS} value={value.company}
            onChange={e => onChange({ ...value, company: e.target.value })}
            placeholder="e.g. Acme Corp" />
        </div>
        <div>
          <label className={LABEL_CLS}>Location</label>
          <input className={INPUT_CLS} value={value.location}
            onChange={e => onChange({ ...value, location: e.target.value })}
            placeholder="e.g. Bangalore, India" />
        </div>
        <div>
          <label className={LABEL_CLS}>Start Date</label>
          <input className={INPUT_CLS} value={value.start_date}
            onChange={e => onChange({ ...value, start_date: e.target.value })}
            placeholder="e.g. Jun 2022" />
        </div>
        <div className="flex flex-col gap-1">
          <label className={LABEL_CLS}>End Date</label>
          <input className={INPUT_CLS} value={value.end_date}
            disabled={value.currently_working}
            onChange={e => onChange({ ...value, end_date: e.target.value })}
            placeholder="e.g. Mar 2024" />
        </div>
        <div className="flex items-end pb-2">
          <label className="flex items-center gap-2 text-sm text-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={value.currently_working}
              onChange={e => onChange({ ...value, currently_working: e.target.checked, end_date: "" })}
              className="w-4 h-4 accent-primary"
            />
            Currently working here
          </label>
        </div>
      </div>
      <div>
        <label className={LABEL_CLS}>Key Responsibilities / Achievements</label>
        <div className="space-y-2">
          {value.bullets.map((b, i) => (
            <div key={i} className="flex gap-2">
              <input className={INPUT_CLS} value={b}
                onChange={e => {
                  const next = [...value.bullets];
                  next[i] = e.target.value;
                  onChange({ ...value, bullets: next });
                }}
                placeholder={`Bullet ${i + 1}`} />
              {value.bullets.length > 1 && (
                <button onClick={() => onRemoveBullet(i)}
                  className="p-2 text-muted-foreground hover:text-red-500 transition">
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
          ))}
          <button onClick={onAddBullet}
            className="flex items-center gap-1 text-xs text-primary hover:underline mt-1">
            <Plus className="w-3.5 h-3.5" /> Add bullet
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Education form ────────────────────────────────────────────────────────────

const EMPTY_EDU = (): Education => ({
  id: genId(), degree: "", institution: "",
  start_year: "", end_year: "", gpa: "", relevant_coursework: "",
});

function EducationForm({
  value, onChange,
}: {
  value: Education;
  onChange: (v: Education) => void;
}) {
  return (
    <div className="space-y-3 border border-border rounded-xl p-4 bg-muted/30">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={LABEL_CLS}>Degree / Qualification *</label>
          <input className={INPUT_CLS} value={value.degree}
            onChange={e => onChange({ ...value, degree: e.target.value })}
            placeholder="e.g. B.Tech Computer Science" />
        </div>
        <div>
          <label className={LABEL_CLS}>Institution *</label>
          <input className={INPUT_CLS} value={value.institution}
            onChange={e => onChange({ ...value, institution: e.target.value })}
            placeholder="e.g. VIT University" />
        </div>
        <div>
          <label className={LABEL_CLS}>Start Year</label>
          <input className={INPUT_CLS} value={value.start_year}
            onChange={e => onChange({ ...value, start_year: e.target.value })}
            placeholder="2019" />
        </div>
        <div>
          <label className={LABEL_CLS}>End Year</label>
          <input className={INPUT_CLS} value={value.end_year}
            onChange={e => onChange({ ...value, end_year: e.target.value })}
            placeholder="2023" />
        </div>
        <div>
          <label className={LABEL_CLS}>GPA / Percentage</label>
          <input className={INPUT_CLS} value={value.gpa}
            onChange={e => onChange({ ...value, gpa: e.target.value })}
            placeholder="e.g. 8.5 / 10" />
        </div>
        <div>
          <label className={LABEL_CLS}>Relevant Coursework</label>
          <input className={INPUT_CLS} value={value.relevant_coursework}
            onChange={e => onChange({ ...value, relevant_coursework: e.target.value })}
            placeholder="e.g. ML, Algorithms, DBMS" />
        </div>
      </div>
    </div>
  );
}

// ── Project form ─────────────────────────────────────────────────────────────

const EMPTY_PROJ = (): Project => ({
  id: genId(), name: "", description: "", tech_stack: "", outcome: "", link: "", bullets: [""],
});

function ProjectForm({
  value, onChange, onRemoveBullet, onAddBullet,
}: {
  value: Project;
  onChange: (v: Project) => void;
  onRemoveBullet: (i: number) => void;
  onAddBullet: () => void;
}) {
  return (
    <div className="space-y-3 border border-border rounded-xl p-4 bg-muted/30">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={LABEL_CLS}>Project Name *</label>
          <input className={INPUT_CLS} value={value.name}
            onChange={e => onChange({ ...value, name: e.target.value })}
            placeholder="e.g. Interview King" />
        </div>
        <div>
          <label className={LABEL_CLS}>Tech Stack</label>
          <input className={INPUT_CLS} value={value.tech_stack}
            onChange={e => onChange({ ...value, tech_stack: e.target.value })}
            placeholder="e.g. React, FastAPI, PostgreSQL" />
        </div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className={LABEL_CLS}>Outcome / Impact</label>
          <input className={INPUT_CLS} value={value.outcome}
            onChange={e => onChange({ ...value, outcome: e.target.value })}
            placeholder="e.g. Reduced screening time by 60%" />
        </div>
        <div>
          <label className={LABEL_CLS}>Link (GitHub / Live)</label>
          <input className={INPUT_CLS} value={value.link}
            onChange={e => onChange({ ...value, link: e.target.value })}
            placeholder="https://github.com/..." />
        </div>
      </div>
      <div>
        <label className={LABEL_CLS}>Key Points / Bullets</label>
        <div className="space-y-2">
          {value.bullets.map((b, i) => (
            <div key={i} className="flex gap-2">
              <input className={INPUT_CLS} value={b}
                onChange={e => {
                  const next = [...value.bullets];
                  next[i] = e.target.value;
                  onChange({ ...value, bullets: next });
                }}
                placeholder={`e.g. Integrated OCR pipeline reducing processing time by 40%`} />
              {value.bullets.length > 1 && (
                <button onClick={() => onRemoveBullet(i)}
                  className="p-2 text-muted-foreground hover:text-red-500 transition">
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
          ))}
          <button onClick={onAddBullet}
            className="flex items-center gap-1 text-xs text-primary hover:underline mt-1">
            <Plus className="w-3.5 h-3.5" /> Add bullet
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Skill tag input ───────────────────────────────────────────────────────────

function SkillTagInput({
  tags, onChange, placeholder,
}: {
  tags: string[];
  onChange: (t: string[]) => void;
  placeholder: string;
}) {
  const [input, setInput] = useState("");

  const add = () => {
    const val = input.trim();
    if (val && !tags.includes(val)) onChange([...tags, val]);
    setInput("");
  };

  return (
    <div>
      <div className="flex flex-wrap gap-2 mb-2">
        {tags.map(t => (
          <span key={t}
            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full
                       text-xs font-medium bg-primary/10 text-primary border border-primary/25">
            {t}
            <button onClick={() => onChange(tags.filter(s => s !== t))}
              className="hover:text-red-500 transition">
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
      </div>
      <div className="flex gap-2">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
          placeholder={placeholder}
          className={INPUT_CLS}
        />
        <button onClick={add}
          className="px-3 py-2 rounded-lg bg-primary/10 border border-primary/25
                     text-primary text-xs font-semibold hover:bg-primary/20 transition">
          Add
        </button>
      </div>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function Profile() {
  const navigate = useNavigate();
  const location = useLocation();

  // Capture once from navigation state — useState so re-renders don't lose it
  // (the useEffect below clears the nav state immediately, which would reset a
  // plain const to false on the follow-up re-render)
  const [showApplyBanner] = useState(
    () => !!(location.state as { applyBlocked?: boolean } | null)?.applyBlocked,
  );

  // Clear the navigation state so back-navigation doesn't re-show the banner
  useEffect(() => {
    if (showApplyBanner) {
      navigate(location.pathname, { replace: true, state: {} });
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ── State ──────────────────────────────────────────────────────────────────
  const [user,        setUser]        = useState<DashUser | null>(null);
  const [cv,          setCv]          = useState<CVData>(emptyCVData());
  const [comp,        setComp]        = useState<Compensation>({
    current_salary: "", expected_salary: "", notice_period: "30 days",
  });
  const [loading,     setLoading]     = useState(true);
  const [uploadState, setUploadState] = useState<"idle" | "uploading" | "done" | "error">("idle");
  const [uploadMsg,   setUploadMsg]   = useState("");
  const [dlLoading,   setDlLoading]   = useState(false);
  const [dlError,     setDlError]     = useState("");
  const [editSection, setEditSection] = useState<EditSection>(null);
  const [saving,      setSaving]      = useState(false);
  const [saveError,   setSaveError]   = useState("");

  // Draft copies for each section
  const [draftPersonal,     setDraftPersonal]     = useState<CVData["contact"] | null>(null);
  const [draftComp,         setDraftComp]         = useState<Compensation | null>(null);
  const [draftSummary,      setDraftSummary]      = useState<string | null>(null);
  const [draftTechSkills,   setDraftTechSkills]   = useState<string[] | null>(null);
  const [draftSoftSkills,   setDraftSoftSkills]   = useState<string[] | null>(null);

  // Experience / Education in-place editing
  const [expEditing,    setExpEditing]    = useState<number | "new" | null>(null);
  const [expDraft,      setExpDraft]      = useState<WorkExperience>(EMPTY_EXP());
  const [expSaving,     setExpSaving]     = useState(false);
  const [eduEditing,    setEduEditing]    = useState<number | "new" | null>(null);
  const [eduDraft,      setEduDraft]      = useState<Education>(EMPTY_EDU());
  const [eduSaving,     setEduSaving]     = useState(false);
  const [projEditing,   setProjEditing]   = useState<number | "new" | null>(null);
  const [projDraft,     setProjDraft]     = useState<Project>(EMPTY_PROJ());
  const [projSaving,    setProjSaving]    = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const dropZoneRef  = useRef<HTMLDivElement>(null);

  // ── Load data ──────────────────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const [me, cvData, profData] = await Promise.allSettled([
          getMe(),
          getCVBuilder(),
          getProfileData(),
        ]);

        if (cancelled) return;

        if (me.status === "fulfilled") setUser(me.value as DashUser);
        else logout();

        if (cvData.status === "fulfilled") {
          setCv(cvData.value);
        }

        if (profData.status === "fulfilled") {
          const p = profData.value as Record<string, unknown>;
          setComp({
            current_salary:  String(p.current_salary  ?? p.currentCtc    ?? ""),
            expected_salary: String(p.expected_salary ?? p.expectedCtc   ?? ""),
            notice_period:   String(p.notice_period   ?? "30 days"),
          });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    load();
    return () => { cancelled = true; };
  }, []);

  const completion = calcCompletion(cv, comp);

  // ── Resume upload ──────────────────────────────────────────────────────────
  const handleFile = useCallback(async (file: File) => {
    if (!file.name.toLowerCase().endsWith(".pdf")) {
      setUploadMsg("Only PDF files are accepted.");
      setUploadState("error");
      return;
    }
    setUploadState("uploading");
    setUploadMsg("");
    try {
      const parsed = await parseCVFile(file);
      setCv(parsed);
      await saveCVBuilder(parsed);
      setUploadState("done");
      setUploadMsg(`"${file.name}" uploaded and profile updated.`);
    } catch (err: unknown) {
      setUploadState("error");
      setUploadMsg(err instanceof Error ? err.message : "Upload failed. Please try again.");
    }
  }, []);

  const onFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (f) handleFile(f);
    e.target.value = "";
  };

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f) handleFile(f);
  }, [handleFile]);

  // ── Download CV ────────────────────────────────────────────────────────────
  const handleDownload = async () => {
    setDlError("");

    const ctcMissing = !comp.current_salary || !comp.expected_salary;
    if (completion < 70 || ctcMissing) {
      setDlError(
        `Your profile is ${completion}% complete. Reach 70% and fill in` +
        ` Current CTC & Expected CTC to download your CV.`,
      );
      return;
    }

    setDlLoading(true);
    try {
      await saveCVBuilder(cv);
      await downloadCVPDF();
    } catch (err: unknown) {
      setDlError(err instanceof Error ? err.message : "Download failed.");
    } finally {
      setDlLoading(false);
    }
  };

  // ── Generic section save helper ────────────────────────────────────────────
  const saveSection = async (updatedCv: CVData, updatedComp?: Compensation) => {
    setSaving(true);
    setSaveError("");
    try {
      await saveCVBuilder(updatedCv);
      if (updatedComp) {
        await updateProfileData({
          current_salary:  updatedComp.current_salary,
          expected_salary: updatedComp.expected_salary,
          notice_period:   updatedComp.notice_period,
        });
      }
      // Batch state updates after both network calls confirm success
      setCv(updatedCv);
      if (updatedComp) setComp(updatedComp);
      setEditSection(null);
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Save failed. Please try again.");
    } finally {
      setSaving(false);
    }
  };

  // ── Personal section ───────────────────────────────────────────────────────
  const startEditPersonal = () => {
    setDraftPersonal({ ...cv.contact });
    setEditSection("personal");
  };
  const savePersonal = () => {
    if (!draftPersonal) return;
    saveSection({ ...cv, contact: draftPersonal });
  };

  // ── Compensation section ───────────────────────────────────────────────────
  const startEditComp = () => {
    setDraftComp({ ...comp });
    setEditSection("compensation");
  };
  const saveComp = () => {
    if (!draftComp) return;
    saveSection(cv, draftComp);
  };

  // ── Summary section ────────────────────────────────────────────────────────
  const startEditSummary = () => {
    setDraftSummary(cv.summary);
    setEditSection("summary");
  };
  const saveSummary = () => {
    if (draftSummary === null) return;
    saveSection({ ...cv, summary: draftSummary });
  };

  // ── Skills section ─────────────────────────────────────────────────────────
  const startEditSkills = () => {
    setDraftTechSkills([...cv.skills.technical]);
    setDraftSoftSkills([...cv.skills.soft]);
    setEditSection("skills");
  };
  const saveSkills = () => {
    if (!draftTechSkills || !draftSoftSkills) return;
    saveSection({ ...cv, skills: { technical: draftTechSkills, soft: draftSoftSkills } });
  };

  // ── Experience section ─────────────────────────────────────────────────────
  const saveExperience = async (list: WorkExperience[]) => {
    setExpSaving(true);
    setSaveError("");
    try {
      const updated = { ...cv, work_experience: list };
      await saveCVBuilder(updated);
      setCv(updated);
      setExpEditing(null);
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setExpSaving(false);
    }
  };

  const commitExp = () => {
    if (!expDraft.title || !expDraft.company) {
      setSaveError("Job title and company are required.");
      return;
    }
    setSaveError("");
    let list = [...cv.work_experience];
    if (expEditing === "new") list = [expDraft, ...list];
    else if (typeof expEditing === "number") list[expEditing] = expDraft;
    saveExperience(list);
  };

  const deleteExp = (i: number) => {
    setExpEditing(null);
    const list = cv.work_experience.filter((_, idx) => idx !== i);
    saveExperience(list);
  };

  // ── Education section ──────────────────────────────────────────────────────
  const saveEducation = async (list: Education[]) => {
    setEduSaving(true);
    setSaveError("");
    try {
      const updated = { ...cv, education: list };
      await saveCVBuilder(updated);
      setCv(updated);
      setEduEditing(null);
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setEduSaving(false);
    }
  };

  const commitEdu = () => {
    if (!eduDraft.degree || !eduDraft.institution) {
      setSaveError("Degree and institution are required.");
      return;
    }
    setSaveError("");
    let list = [...cv.education];
    if (eduEditing === "new") list = [eduDraft, ...list];
    else if (typeof eduEditing === "number") list[eduEditing] = eduDraft;
    saveEducation(list);
  };

  const deleteEdu = (i: number) => {
    setEduEditing(null);
    const list = cv.education.filter((_, idx) => idx !== i);
    saveEducation(list);
  };

  // ── Projects section ────────────────────────────────────────────────────────
  const saveProjects = async (list: Project[]) => {
    setProjSaving(true);
    setSaveError("");
    try {
      const updated = { ...cv, projects: list };
      await saveCVBuilder(updated);
      setCv(updated);
      setProjEditing(null);
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : "Save failed.");
    } finally {
      setProjSaving(false);
    }
  };

  const commitProj = () => {
    if (!projDraft.name) { setSaveError("Project name is required."); return; }
    setSaveError("");
    let list = [...cv.projects];
    if (projEditing === "new") list = [projDraft, ...list];
    else if (typeof projEditing === "number") list[projEditing] = projDraft;
    saveProjects(list);
  };

  const deleteProj = (i: number) => {
    setProjEditing(null);
    const list = cv.projects.filter((_, idx) => idx !== i);
    saveProjects(list);
  };

  // ── Render ─────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="min-h-screen">
        <AnimatedBackground />
        <Navbar currentStep={2} user={user} onLogout={logout} showAppNav />
        <div className="flex items-center justify-center pt-48">
          <Loader2 className="w-8 h-8 text-primary animate-spin" />
        </div>
      </div>
    );
  }

  const initials = user
    ? `${(user.first_name ?? "").charAt(0)}${(user.last_name ?? "").charAt(0)}`.toUpperCase()
    : "?";

  return (
    <div className="min-h-screen">
      <AnimatedBackground />
      <Navbar currentStep={2} user={user} onLogout={logout} showAppNav />

      <main className="pt-[120px] sm:pt-[88px] lg:pt-[96px] pb-16 px-4 sm:px-6 max-w-4xl mx-auto">

        {/* ── Apply-blocked banner ── */}
        {showApplyBanner && (
          <motion.div
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-6 flex items-start gap-3 px-5 py-4 rounded-xl
                       bg-amber-50 border border-amber-300 text-amber-800"
          >
            <AlertCircle className="w-5 h-5 shrink-0 mt-0.5 text-amber-500" aria-hidden="true" />
            <div>
              <p className="text-sm font-bold">Complete your profile to apply for jobs</p>
              <p className="text-xs mt-0.5 text-amber-700">
                Your profile must be at least 70% complete and include your current CTC and
                expected CTC before you can apply. Fill in the sections below to get started.
              </p>
            </div>
          </motion.div>
        )}

        {/* ── Page header ── */}
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8"
        >
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-primary to-secondary
                            flex items-center justify-center text-white text-xl font-extrabold shadow-sm">
              {initials}
            </div>
            <div>
              <h1 className="text-2xl font-extrabold text-foreground">
                {user
                  ? (`${user.first_name ?? ""} ${user.last_name ?? ""}`.trim() || "My Profile")
                  : "My Profile"}
              </h1>
              <p className="text-sm text-muted-foreground">{user?.email}</p>
            </div>
          </div>

          <div className="flex items-center gap-3 flex-wrap">
            {/* Completion badge */}
            <div className="flex items-center gap-2 px-3 py-2 glass-card">
              <div className="w-20 h-1.5 bg-muted rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary rounded-full transition-all duration-500"
                  style={{ width: `${completion}%` }}
                />
              </div>
              <span className="text-xs font-semibold text-foreground">{completion}%</span>
              <span className="text-xs text-muted-foreground hidden sm:inline">complete</span>
            </div>

            {/* Download CV */}
            <button
              onClick={handleDownload}
              disabled={dlLoading}
              className="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-white
                         text-sm font-semibold hover:bg-primary/90 disabled:opacity-60
                         transition shadow-sm"
            >
              {dlLoading
                ? <Loader2 className="w-4 h-4 animate-spin" />
                : <Download className="w-4 h-4" />
              }
              Download CV
            </button>
          </div>
        </motion.div>

        {dlError && (
          <div role="alert" className="mb-4 flex items-center gap-2 px-4 py-3 rounded-xl
                          bg-red-50 border border-red-200 text-red-600 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />
            {dlError}
          </div>
        )}

        {saveError && (
          <div role="alert" className="mb-4 flex items-center gap-2 px-4 py-3 rounded-xl
                          bg-red-50 border border-red-200 text-red-600 text-sm">
            <AlertCircle className="w-4 h-4 shrink-0" aria-hidden="true" />
            {saveError}
            <button onClick={() => setSaveError("")} className="ml-auto" aria-label="Dismiss error">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        <div className="space-y-5">

          {/* ── Resume upload card ── */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 }}
            className="glass-card overflow-hidden"
          >
            <div className="flex items-center gap-2.5 px-5 py-4 border-b border-border">
              <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                <FilePlus2 className="w-4 h-4 text-primary" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-foreground">Resume</h3>
                <p className="text-xs text-muted-foreground">
                  Upload a PDF — AI fills your entire profile automatically
                </p>
              </div>
            </div>

            <div className="p-5">
              <div
                ref={dropZoneRef}
                onDrop={onDrop}
                onDragOver={e => e.preventDefault()}
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-border rounded-xl p-8
                           flex flex-col items-center gap-3 cursor-pointer
                           hover:border-primary/50 hover:bg-primary/5 transition-colors"
              >
                {uploadState === "uploading" ? (
                  <>
                    <Loader2 className="w-8 h-8 text-primary animate-spin" />
                    <p className="text-sm font-medium text-foreground">Parsing resume…</p>
                    <p className="text-xs text-muted-foreground">AI is extracting your details</p>
                  </>
                ) : uploadState === "done" ? (
                  <>
                    <CheckCircle className="w-8 h-8 text-emerald-600" />
                    <p className="text-sm font-medium text-emerald-700">{uploadMsg}</p>
                    <p className="text-xs text-muted-foreground">Click to upload a different resume</p>
                  </>
                ) : uploadState === "error" ? (
                  <>
                    <AlertCircle className="w-8 h-8 text-red-500" />
                    <p className="text-sm font-medium text-red-600">{uploadMsg}</p>
                    <p className="text-xs text-muted-foreground">Click to try again</p>
                  </>
                ) : (
                  <>
                    <Upload className="w-8 h-8 text-muted-foreground" />
                    <p className="text-sm font-medium text-foreground">
                      Drag & drop your resume, or <span className="text-primary">browse</span>
                    </p>
                    <p className="text-xs text-muted-foreground">PDF only · max 10 MB</p>
                  </>
                )}
              </div>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf"
                className="hidden"
                onChange={onFileInput}
              />
            </div>
          </motion.div>

          {/* ── Personal Information ── */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            <SectionCard
              icon={User}
              title="Personal Information"
              editing={editSection === "personal"}
              onEdit={startEditPersonal}
              onSave={savePersonal}
              onCancel={() => setEditSection(null)}
              saving={saving}
            >
              {editSection === "personal" && draftPersonal ? (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  {(
                    [
                      { key: "name",      label: "Full Name",        ph: "Nikhil Sharma" },
                      { key: "email",     label: "Email",            ph: "you@email.com" },
                      { key: "phone",     label: "Phone",            ph: "+91 98765 43210" },
                      { key: "location",  label: "Current City",     ph: "Bangalore, India" },
                      { key: "linkedin",  label: "LinkedIn URL",     ph: "https://linkedin.com/in/…" },
                      { key: "github",    label: "GitHub URL",       ph: "https://github.com/…" },
                      { key: "portfolio", label: "Portfolio / Website", ph: "https://yoursite.com" },
                    ] as { key: keyof typeof draftPersonal; label: string; ph: string }[]
                  ).map(({ key, label, ph }) => (
                    <div key={key}>
                      <label className={LABEL_CLS}>{label}</label>
                      <input
                        className={INPUT_CLS}
                        value={String(draftPersonal[key] ?? "")}
                        onChange={e => setDraftPersonal({ ...draftPersonal, [key]: e.target.value })}
                        placeholder={ph}
                      />
                    </div>
                  ))}
                </div>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3">
                  {[
                    { label: "Full Name",    value: cv.contact.name },
                    { label: "Email",        value: cv.contact.email },
                    { label: "Phone",        value: cv.contact.phone },
                    { label: "Location",     value: cv.contact.location },
                    { label: "LinkedIn",     value: cv.contact.linkedin },
                    { label: "GitHub",       value: cv.contact.github },
                    { label: "Portfolio",    value: cv.contact.portfolio },
                  ].map(({ label, value }) => (
                    <div key={label}>
                      <span className="text-xs text-muted-foreground">{label}</span>
                      <p className="text-sm font-medium text-foreground mt-0.5">
                        {value || <span className="text-muted-foreground italic">Not set</span>}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </SectionCard>
          </motion.div>

          {/* ── Compensation (required) ── */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.15 }}
          >
            <SectionCard
              icon={Zap}
              title="Compensation & Availability"
              editing={editSection === "compensation"}
              onEdit={startEditComp}
              onSave={saveComp}
              onCancel={() => setEditSection(null)}
              saving={saving}
            >
              {(!comp.current_salary || !comp.expected_salary) && editSection !== "compensation" && (
                <div className="flex items-center gap-2 mb-4 px-3 py-2 rounded-lg
                                bg-amber-50 border border-amber-200 text-amber-700 text-xs">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  Current CTC and Expected CTC are required for AI job matching.
                  <button onClick={startEditComp} className="ml-auto font-semibold underline">
                    Fill now
                  </button>
                </div>
              )}

              {editSection === "compensation" && draftComp ? (
                <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                  <div>
                    <label htmlFor="comp-current-ctc" className={LABEL_CLS}>
                      Current CTC (₹/year) <span className="text-red-500">*</span>
                    </label>
                    <input
                      id="comp-current-ctc"
                      type="number"
                      className={INPUT_CLS}
                      value={draftComp.current_salary}
                      onChange={e => setDraftComp({ ...draftComp, current_salary: e.target.value })}
                      placeholder="e.g. 800000"
                    />
                  </div>
                  <div>
                    <label htmlFor="comp-expected-ctc" className={LABEL_CLS}>
                      Expected CTC (₹/year) <span className="text-red-500">*</span>
                    </label>
                    <input
                      id="comp-expected-ctc"
                      type="number"
                      className={INPUT_CLS}
                      value={draftComp.expected_salary}
                      onChange={e => setDraftComp({ ...draftComp, expected_salary: e.target.value })}
                      placeholder="e.g. 1200000"
                    />
                  </div>
                  <div>
                    <label htmlFor="comp-notice-period" className={LABEL_CLS}>Notice Period</label>
                    <select
                      id="comp-notice-period"
                      className={INPUT_CLS}
                      value={draftComp.notice_period}
                      onChange={e => setDraftComp({ ...draftComp, notice_period: e.target.value })}
                    >
                      {NOTICE_OPTIONS.map(o => (
                        <option key={o} value={o}>{o}</option>
                      ))}
                    </select>
                  </div>
                </div>
              ) : (
                <div className="grid grid-cols-3 gap-6">
                  {[
                    { label: "Current CTC",  value: comp.current_salary  ? `₹${Number(comp.current_salary).toLocaleString("en-IN")}` : null },
                    { label: "Expected CTC", value: comp.expected_salary ? `₹${Number(comp.expected_salary).toLocaleString("en-IN")}` : null },
                    { label: "Notice Period", value: comp.notice_period },
                  ].map(({ label, value }) => (
                    <div key={label}>
                      <span className="text-xs text-muted-foreground">{label}</span>
                      <p className={`text-sm font-semibold mt-0.5 ${
                        value ? "text-foreground" : "text-amber-600 italic"
                      }`}>
                        {value || "Not set — required"}
                      </p>
                    </div>
                  ))}
                </div>
              )}
            </SectionCard>
          </motion.div>

          {/* ── Professional Summary ── */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            <SectionCard
              icon={Briefcase}
              title="Professional Summary"
              editing={editSection === "summary"}
              onEdit={startEditSummary}
              onSave={saveSummary}
              onCancel={() => setEditSection(null)}
              saving={saving}
            >
              {editSection === "summary" && draftSummary !== null ? (
                <textarea
                  rows={5}
                  className={`${INPUT_CLS} resize-none`}
                  value={draftSummary}
                  onChange={e => setDraftSummary(e.target.value)}
                  placeholder="A brief overview of your experience, skills, and career goals…"
                />
              ) : cv.summary ? (
                <p className="text-sm text-foreground leading-relaxed whitespace-pre-wrap">
                  {cv.summary}
                </p>
              ) : (
                <EmptyState message="No summary yet. Click Edit to add one." />
              )}
            </SectionCard>
          </motion.div>

          {/* ── Work Experience ── */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.25 }}
            className="glass-card overflow-hidden"
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                  <Briefcase className="w-4 h-4 text-primary" />
                </div>
                <h3 className="text-sm font-bold text-foreground">Work Experience</h3>
              </div>
              <button
                onClick={() => { setExpDraft(EMPTY_EXP()); setExpEditing("new"); setSaveError(""); }}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold
                           bg-primary/10 text-primary border border-primary/25
                           hover:bg-primary/20 transition"
              >
                <Plus className="w-3.5 h-3.5" /> Add
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* New entry form */}
              <AnimatePresence>
                {expEditing === "new" && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden"
                  >
                    <ExperienceForm
                      value={expDraft}
                      onChange={setExpDraft}
                      onRemoveBullet={i => setExpDraft(d => ({
                        ...d, bullets: d.bullets.filter((_, idx) => idx !== i),
                      }))}
                      onAddBullet={() => setExpDraft(d => ({ ...d, bullets: [...d.bullets, ""] }))}
                    />
                    <div className="flex gap-2 mt-3">
                      <button onClick={commitExp} disabled={expSaving}
                        className="flex items-center gap-1 px-4 py-2 rounded-lg text-xs font-semibold
                                   bg-primary text-white hover:bg-primary/90 disabled:opacity-60 transition">
                        {expSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                        Save Entry
                      </button>
                      <button onClick={() => setExpEditing(null)}
                        className="px-4 py-2 rounded-lg text-xs border border-border
                                   text-muted-foreground hover:bg-muted transition">
                        Cancel
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {(cv.work_experience?.length ?? 0) === 0 && expEditing !== "new" && (
                <EmptyState message="No work experience added yet. Click Add to get started." />
              )}

              {(cv.work_experience ?? []).map((exp, i) => (
                <div key={exp.id} className="border border-border rounded-xl overflow-hidden">
                  {expEditing === i ? (
                    <div className="p-4 space-y-3">
                      <ExperienceForm
                        value={expDraft}
                        onChange={setExpDraft}
                        onRemoveBullet={idx => setExpDraft(d => ({
                          ...d, bullets: d.bullets.filter((_, bi) => bi !== idx),
                        }))}
                        onAddBullet={() => setExpDraft(d => ({ ...d, bullets: [...d.bullets, ""] }))}
                      />
                      <div className="flex gap-2">
                        <button onClick={commitExp} disabled={expSaving}
                          className="flex items-center gap-1 px-4 py-2 rounded-lg text-xs font-semibold
                                     bg-primary text-white hover:bg-primary/90 disabled:opacity-60 transition">
                          {expSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                          Save
                        </button>
                        <button onClick={() => setExpEditing(null)}
                          className="px-4 py-2 rounded-lg text-xs border border-border
                                     text-muted-foreground hover:bg-muted transition">
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-bold text-foreground">{exp.title}</p>
                          <p className="text-sm text-muted-foreground">
                            {exp.company}{exp.location ? ` · ${exp.location}` : ""}
                          </p>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {exp.start_date}
                            {exp.start_date ? " – " : ""}
                            {exp.currently_working ? "Present" : exp.end_date}
                          </p>
                          {exp.bullets.filter(Boolean).length > 0 && (
                            <ul className="mt-2 space-y-1 list-disc list-inside">
                              {exp.bullets.filter(Boolean).map((b, bi) => (
                                <li key={bi} className="text-xs text-foreground/80">{b}</li>
                              ))}
                            </ul>
                          )}
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            onClick={() => { setExpDraft({ ...exp }); setExpEditing(i); setSaveError(""); }}
                            className="p-1.5 rounded-lg text-muted-foreground
                                       hover:text-foreground hover:bg-muted transition"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => deleteExp(i)}
                            className="p-1.5 rounded-lg text-muted-foreground
                                       hover:text-red-500 hover:bg-red-50 transition"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </motion.div>

          {/* ── Education ── */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
            className="glass-card overflow-hidden"
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                  <GraduationCap className="w-4 h-4 text-primary" />
                </div>
                <h3 className="text-sm font-bold text-foreground">Education</h3>
              </div>
              <button
                onClick={() => { setEduDraft(EMPTY_EDU()); setEduEditing("new"); setSaveError(""); }}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold
                           bg-primary/10 text-primary border border-primary/25
                           hover:bg-primary/20 transition"
              >
                <Plus className="w-3.5 h-3.5" /> Add
              </button>
            </div>

            <div className="p-5 space-y-4">
              <AnimatePresence>
                {eduEditing === "new" && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden"
                  >
                    <EducationForm value={eduDraft} onChange={setEduDraft} />
                    <div className="flex gap-2 mt-3">
                      <button onClick={commitEdu} disabled={eduSaving}
                        className="flex items-center gap-1 px-4 py-2 rounded-lg text-xs font-semibold
                                   bg-primary text-white hover:bg-primary/90 disabled:opacity-60 transition">
                        {eduSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                        Save Entry
                      </button>
                      <button onClick={() => setEduEditing(null)}
                        className="px-4 py-2 rounded-lg text-xs border border-border
                                   text-muted-foreground hover:bg-muted transition">
                        Cancel
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {(cv.education?.length ?? 0) === 0 && eduEditing !== "new" && (
                <EmptyState message="No education added yet. Click Add to get started." />
              )}

              {(cv.education ?? []).map((edu, i) => (
                <div key={edu.id} className="border border-border rounded-xl overflow-hidden">
                  {eduEditing === i ? (
                    <div className="p-4 space-y-3">
                      <EducationForm value={eduDraft} onChange={setEduDraft} />
                      <div className="flex gap-2">
                        <button onClick={commitEdu} disabled={eduSaving}
                          className="flex items-center gap-1 px-4 py-2 rounded-lg text-xs font-semibold
                                     bg-primary text-white hover:bg-primary/90 disabled:opacity-60 transition">
                          {eduSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                          Save
                        </button>
                        <button onClick={() => setEduEditing(null)}
                          className="px-4 py-2 rounded-lg text-xs border border-border
                                     text-muted-foreground hover:bg-muted transition">
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-bold text-foreground">{edu.degree}</p>
                          <p className="text-sm text-muted-foreground">{edu.institution}</p>
                          <p className="text-xs text-muted-foreground mt-0.5">
                            {edu.start_year}{edu.start_year && edu.end_year ? " – " : ""}{edu.end_year}
                            {edu.gpa ? ` · GPA ${edu.gpa}` : ""}
                          </p>
                          {edu.relevant_coursework && (
                            <p className="text-xs text-muted-foreground mt-1">
                              <span className="font-medium">Coursework:</span> {edu.relevant_coursework}
                            </p>
                          )}
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            onClick={() => { setEduDraft({ ...edu }); setEduEditing(i); setSaveError(""); }}
                            className="p-1.5 rounded-lg text-muted-foreground
                                       hover:text-foreground hover:bg-muted transition"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => deleteEdu(i)}
                            className="p-1.5 rounded-lg text-muted-foreground
                                       hover:text-red-500 hover:bg-red-50 transition"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </motion.div>

          {/* ── Skills ── */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.35 }}
          >
            <SectionCard
              icon={Code2}
              title="Skills"
              editing={editSection === "skills"}
              onEdit={startEditSkills}
              onSave={saveSkills}
              onCancel={() => setEditSection(null)}
              saving={saving}
            >
              {editSection === "skills" && draftTechSkills && draftSoftSkills ? (
                <div className="space-y-5">
                  <div>
                    <label className={LABEL_CLS}>Technical Skills</label>
                    <SkillTagInput
                      tags={draftTechSkills}
                      onChange={setDraftTechSkills}
                      placeholder="Type a skill and press Enter…"
                    />
                  </div>
                  <div>
                    <label className={LABEL_CLS}>Soft Skills</label>
                    <SkillTagInput
                      tags={draftSoftSkills}
                      onChange={setDraftSoftSkills}
                      placeholder="Type a skill and press Enter…"
                    />
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div>
                    <p className={LABEL_CLS}>Technical Skills</p>
                    {(cv.skills?.technical?.length ?? 0) > 0 ? (
                      <div className="flex flex-wrap gap-2 mt-1">
                        {(cv.skills?.technical ?? []).map(s => (
                          <span key={s}
                            className="px-2.5 py-1 rounded-full text-xs font-medium
                                       bg-primary/10 text-primary border border-primary/20">
                            {s}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <EmptyState message="No technical skills added." />
                    )}
                  </div>
                  <div>
                    <p className={LABEL_CLS}>Soft Skills</p>
                    {(cv.skills?.soft?.length ?? 0) > 0 ? (
                      <div className="flex flex-wrap gap-2 mt-1">
                        {(cv.skills?.soft ?? []).map(s => (
                          <span key={s}
                            className="px-2.5 py-1 rounded-full text-xs font-medium
                                       bg-muted text-muted-foreground border border-border">
                            {s}
                          </span>
                        ))}
                      </div>
                    ) : (
                      <EmptyState message="No soft skills added." />
                    )}
                  </div>
                </div>
              )}
            </SectionCard>
          </motion.div>

          {/* ── Projects ── */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="glass-card overflow-hidden"
          >
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-primary/10 flex items-center justify-center">
                  <BookOpen className="w-4 h-4 text-primary" />
                </div>
                <h3 className="text-sm font-bold text-foreground">Projects</h3>
              </div>
              <button
                onClick={() => { setProjDraft(EMPTY_PROJ()); setProjEditing("new"); setSaveError(""); }}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs
                           text-muted-foreground border border-border hover:bg-muted hover:text-foreground transition"
              >
                <Plus className="w-3.5 h-3.5" /> Add
              </button>
            </div>

            <div className="p-5 space-y-4">
              <AnimatePresence>
                {projEditing === "new" && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: "auto" }}
                    exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden"
                  >
                    <ProjectForm
                      value={projDraft}
                      onChange={setProjDraft}
                      onRemoveBullet={i => setProjDraft(d => ({ ...d, bullets: d.bullets.filter((_, idx) => idx !== i) }))}
                      onAddBullet={() => setProjDraft(d => ({ ...d, bullets: [...d.bullets, ""] }))}
                    />
                    <div className="flex gap-2 mt-3">
                      <button onClick={commitProj} disabled={projSaving}
                        className="flex items-center gap-1 px-4 py-2 rounded-lg text-xs font-semibold
                                   bg-primary text-white hover:bg-primary/90 disabled:opacity-60 transition">
                        {projSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                        Save Entry
                      </button>
                      <button onClick={() => setProjEditing(null)}
                        className="px-4 py-2 rounded-lg text-xs border border-border text-muted-foreground hover:bg-muted transition">
                        Cancel
                      </button>
                    </div>
                  </motion.div>
                )}
              </AnimatePresence>

              {(cv.projects?.length ?? 0) === 0 && projEditing !== "new" && (
                <EmptyState message="No projects added yet. Click Add to get started." />
              )}

              {(cv.projects ?? []).map((p, i) => (
                <div key={p.id} className="border border-border rounded-xl overflow-hidden">
                  {projEditing === i ? (
                    <div className="p-4 space-y-3">
                      <ProjectForm
                        value={projDraft}
                        onChange={setProjDraft}
                        onRemoveBullet={idx => setProjDraft(d => ({ ...d, bullets: d.bullets.filter((_, bi) => bi !== idx) }))}
                        onAddBullet={() => setProjDraft(d => ({ ...d, bullets: [...d.bullets, ""] }))}
                      />
                      <div className="flex gap-2">
                        <button onClick={commitProj} disabled={projSaving}
                          className="flex items-center gap-1 px-4 py-2 rounded-lg text-xs font-semibold
                                     bg-primary text-white hover:bg-primary/90 disabled:opacity-60 transition">
                          {projSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                          Save
                        </button>
                        <button onClick={() => setProjEditing(null)}
                          className="px-4 py-2 rounded-lg text-xs border border-border text-muted-foreground hover:bg-muted transition">
                          Cancel
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-bold text-foreground">{p.name}</p>
                          {p.tech_stack && (
                            <p className="text-xs text-muted-foreground mt-0.5">{p.tech_stack}</p>
                          )}
                          {p.description && (
                            <p className="text-xs text-foreground/80 mt-1 leading-relaxed">{p.description}</p>
                          )}
                          {p.bullets?.filter(Boolean).length > 0 && (
                            <ul className="mt-2 space-y-1 list-disc list-inside">
                              {p.bullets.filter(Boolean).map((b, bi) => (
                                <li key={bi} className="text-xs text-foreground/80">{b}</li>
                              ))}
                            </ul>
                          )}
                          {p.outcome && (
                            <p className="text-xs text-primary font-medium mt-1">{p.outcome}</p>
                          )}
                          {p.link && (
                            <a href={p.link} target="_blank" rel="noopener noreferrer"
                              className="text-xs text-primary underline mt-1 inline-block">
                              {p.link}
                            </a>
                          )}
                        </div>
                        <div className="flex items-center gap-1 shrink-0">
                          <button
                            onClick={() => { setProjDraft({ ...p }); setProjEditing(i); setSaveError(""); }}
                            className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-muted transition"
                          >
                            <Pencil className="w-3.5 h-3.5" />
                          </button>
                          <button
                            onClick={() => deleteProj(i)}
                            className="p-1.5 rounded-lg text-muted-foreground hover:text-red-500 hover:bg-red-50 transition"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </motion.div>

        </div>
      </main>
    </div>
  );
}
