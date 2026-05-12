const API: string = import.meta.env.VITE_API_URL ?? "";

// ─── Types ────────────────────────────────────────────────────────────────────

export interface CvExtractedData {
  jobTitle:          string;
  yearsOfExperience: number;
  skills:            string[];
}

export interface ProfileData {
  firstName:    string;
  lastName:     string;
  phone:        string;
  email:        string;
  currentCtc:   string;
  expectedCtc:  string;
  location:     string;
  jobTitle:     string;
  noticePeriod: string;
  experience:   string;
  linkedin:     string;
  github:       string;
}

export interface ShortlistedJob {
  application_id:  string;
  applied_at:      string;
  ai_match_score:  number | null;
  job_id:          string | null;
  title:           string;
  company:         string;
  location:        string;
  work_mode:       string | null;
  job_type:        string | null;
  salary_min:      number | null;
  salary_max:      number | null;
  salary_currency: string | null;
  skills:          string[];
  source:          "portal";
  platform:        string | null;
  job_url:         string | null;
}

import { getToken } from "@/lib/auth";

// ─── Helpers ─────────────────────────────────────────────────────────────────

const _authHeader = (): Record<string, string> => {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
};

// ─── CV upload ────────────────────────────────────────────────────────────────

export const uploadCv = async (file: File): Promise<CvExtractedData> => {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API}/api/cv/upload`, {
    method:  "POST",
    headers: _authHeader(),
    body:    form,
  });

  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`CV upload failed: ${detail}`);
  }

  return res.json() as Promise<CvExtractedData>;
};

// ─── Profile management ───────────────────────────────────────────────────────

export const getProfileData = async (): Promise<Record<string, unknown>> => {
  const res = await fetch(`${API}/api/cv/profile`, { headers: _authHeader() });
  if (!res.ok) throw new Error("No saved profile found.");
  return res.json();
};

export const updateProfileData = async (fields: Record<string, unknown>): Promise<void> => {
  const res = await fetch(`${API}/api/cv/profile`, {
    method:  "PATCH",
    headers: { "Content-Type": "application/json", ..._authHeader() },
    body:    JSON.stringify(fields),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as { detail?: string }).detail ?? "Profile update failed.");
  }
};

export const deleteProfileData = async (): Promise<void> => {
  const res = await fetch(`${API}/api/cv/profile`, {
    method:  "DELETE",
    headers: _authHeader(),
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as { detail?: string }).detail ?? "Reset failed.");
  }
};

// ─── Shortlisted Jobs ─────────────────────────────────────────────────────────

export const getShortlistedJobs = async (): Promise<ShortlistedJob[]> => {
  const res = await fetch(`${API}/api/portal/shortlisted`, { headers: _authHeader() });
  if (!res.ok) throw new Error("Failed to load shortlisted jobs.");
  return res.json();
};
