/**
 * lib/cvBuilderApi.ts
 * ────────────────────
 * Type definitions + API calls for the CV Builder feature.
 */

import { getToken } from "./auth";

const API = import.meta.env.VITE_API_URL;

// ── Types ─────────────────────────────────────────────────────────────────────

export interface CVContact {
  name:      string;
  phone:     string;
  email:     string;
  linkedin:  string;
  github:    string;
  portfolio: string;
  location:  string;
}

export interface WorkExperience {
  id:                string;
  title:             string;
  company:           string;
  location:          string;
  start_date:        string;
  end_date:          string;
  currently_working: boolean;
  bullets:           string[];
}

export interface Education {
  id:                  string;
  degree:              string;
  institution:         string;
  start_year:          string;
  end_year:            string;
  gpa:                 string;
  relevant_coursework: string;
}

export interface Project {
  id:          string;
  name:        string;
  description: string;
  tech_stack:  string;
  outcome:     string;
  link:        string;
  bullets:     string[];
}

export interface Certification {
  id:     string;
  name:   string;
  issuer: string;
  year:   string;
}

export interface Achievement {
  id:          string;
  description: string;
}

export interface CVData {
  is_fresher:     boolean;
  contact:        CVContact;
  summary:        string;
  work_experience: WorkExperience[];
  education:      Education[];
  skills:         { technical: string[]; soft: string[] };
  projects:       Project[];
  certifications: Certification[];
  achievements:   Achievement[];
}

// ── Factory ───────────────────────────────────────────────────────────────────

export const emptyCVData = (): CVData => ({
  is_fresher: false,
  contact: {
    name: "", phone: "", email: "", linkedin: "",
    github: "", portfolio: "", location: "",
  },
  summary: "",
  work_experience: [],
  education: [{
    id: "edu_1", degree: "", institution: "",
    start_year: "", end_year: "", gpa: "", relevant_coursework: "",
  }],
  skills: { technical: [], soft: [] },
  projects: [],
  certifications: [],
  achievements: [],
});

// ── Fetch helper ──────────────────────────────────────────────────────────────

async function _authFetch(path: string, init: RequestInit = {}): Promise<Response> {
  return fetch(`${API}${path}`, {
    ...init,
    headers: {
      ...(init.headers as Record<string, string> ?? {}),
      Authorization: `Bearer ${getToken() ?? ""}`,
    },
  });
}

// ── API calls ─────────────────────────────────────────────────────────────────

/** Upload PDF → Groq parse → returns cv_data (does NOT save). */
export async function parseCVFile(file: File): Promise<CVData> {
  const form = new FormData();
  form.append("file", file);
  const res  = await _authFetch("/api/cv/parse", { method: "POST", body: form });
  const data = await res.json().catch(() => ({ detail: res.statusText }));
  if (!res.ok) throw new Error(data.detail ?? "Parse failed");
  return data as CVData;
}

/**
 * Get saved cv_data.json.
 * Throws Error("NOT_FOUND") on 404 — used by the routing guard.
 */
export async function getCVBuilder(): Promise<CVData> {
  const res = await _authFetch("/api/cv/builder");
  if (res.status === 404) throw new Error("NOT_FOUND");
  const data = await res.json().catch(() => ({ detail: res.statusText }));
  if (!res.ok) throw new Error(data.detail ?? "Fetch failed");
  return data as CVData;
}

/** Persist cv_data + generate ATS PDF. */
export async function saveCVBuilder(
  cv: CVData,
): Promise<{ status: string; pdf_ready: boolean }> {
  const res = await _authFetch("/api/cv/builder/save", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(cv),
  });
  const data = await res.json().catch(() => ({ detail: res.statusText }));
  if (!res.ok) throw new Error(data.detail ?? "Save failed");
  return data;
}

/** Fetch the ATS PDF via auth and trigger a browser download. */
export async function downloadCVPDF(): Promise<void> {
  const res = await _authFetch("/api/cv/builder/pdf");
  if (!res.ok) throw new Error("PDF not available. Please save your CV first.");
  const blob = await res.blob();
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = "ATS_CV.pdf";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
