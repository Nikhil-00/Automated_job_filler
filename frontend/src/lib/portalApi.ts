const API: string = import.meta.env.VITE_API_URL ?? "";

const _authHeader = (): Record<string, string> => {
  const token = sessionStorage.getItem("auth_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
};

export interface PortalApplication {
  id:              string;
  applied_at:      string;
  status:          "pending" | "reviewed" | "shortlisted" | "rejected";
  ai_match_score:  number | null;
  ai_score_reason: string | null;
  title:           string;
  company:         string;
  location:        string;
  work_mode:       string | null;
  job_type:        string | null;
  source:          "Portal" | "Match";
  platform:        string | null;
  url:             string | null;
}

export const getAllApplications = async (): Promise<PortalApplication[]> => {
  const res = await fetch(`${API}/api/portal/all-applications`, { headers: _authHeader() });
  if (!res.ok) throw new Error("Failed to load applications.");
  return res.json();
};
