/**
 * lib/auth.ts
 * ────────────
 * Auth API calls + token storage helpers.
 */

const API = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "");

// ─── Token helpers ────────────────────────────────────────────────────────────

export const getToken    = (): string | null => sessionStorage.getItem("auth_token");
export const setToken    = (t: string)        => sessionStorage.setItem("auth_token", t);
export const clearToken  = ()                 => sessionStorage.removeItem("auth_token");
export const isLoggedIn  = (): boolean        => !!getToken();

export const getAuthHeaders = (): Record<string, string> => ({
  "Content-Type":  "application/json",
  "Authorization": `Bearer ${getToken() ?? ""}`,
});

// ─── Types ────────────────────────────────────────────────────────────────────

export interface AuthUser {
  token:       string;
  user_id:     number;
  first_name:  string;
  last_name:   string;
  email:       string;
  role:        string;
  has_profile: boolean;
}

export interface UserInfo {
  user_id:     number;
  first_name:  string;
  last_name:   string;
  email:       string;
  role:        string;
  has_profile: boolean;
}

// ─── API calls ────────────────────────────────────────────────────────────────

async function _post<T>(path: string, body: unknown, auth = false): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (auth) headers["Authorization"] = `Bearer ${getToken() ?? ""}`;

  const res = await fetch(`${API}${path}`, {
    method:  "POST",
    headers,
    body:    JSON.stringify(body),
  });

  const data = await res.json().catch(() => ({ detail: res.statusText }));
  if (!res.ok) throw new Error(data.detail ?? "Request failed");
  return data as T;
}

async function _get<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`, { headers: getAuthHeaders() });
  const data = await res.json().catch(() => ({ detail: res.statusText }));
  if (!res.ok) throw new Error(data.detail ?? "Request failed");
  return data as T;
}

export const signup = (payload: {
  first_name: string;
  last_name:  string;
  email:      string;
  phone:      string;
  password:   string;
}) => _post<{ message: string }>("/api/auth/signup", payload);

export const verifyOtp = (payload: { email: string; otp_code: string }) =>
  _post<AuthUser>("/api/auth/verify-otp", payload);

export const login = (payload: { email: string; password: string }) =>
  _post<AuthUser>("/api/auth/login", payload);

export const resendOtp = (email: string) =>
  _post<{ message: string }>("/api/auth/resend-otp", { email });

export const getMe = () => _get<UserInfo>("/api/auth/me");

export const logout = () => {
  clearToken();
  window.location.replace("/");
};
