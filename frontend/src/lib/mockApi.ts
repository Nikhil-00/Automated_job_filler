/**
 * api.ts  (was mockApi.ts)
 * ──────────────────────────────────────────────────────────────────────────
 * Real API client.  All calls go to the FastAPI backend at VITE_API_BASE_URL.
 * WebSocket streams live automation logs over VITE_WS_URL.
 */

const API  = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const WS   = (import.meta.env.VITE_WS_URL       ?? "ws://localhost:8000"  ).replace(/\/$/, "");

// ─── Types ────────────────────────────────────────────────────────────────────

export interface CvExtractedData {
  jobTitle:          string;
  yearsOfExperience: number;
  skills:            string[];
}

export interface LogEntry {
  id:        number;
  message:   string;
  type:      "info" | "found" | "success" | "error" | "warning";
  timestamp: Date;
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

export interface CostSummary {
  input_tokens:  number;
  output_tokens: number;
  total_tokens:  number;
  cost_usd:      number;
}

export interface CompanyEntry {
  index:       number;
  title:       string;
  company:     string;
  location:    string;
  status:      "applied" | "skipped" | "already_applied";
  reason:      string;
  description: string;
  url:         string;
}

export interface StartAutomationParams {
  platform:    "linkedin" | "naukri";
  credentials: { email: string; password: string };
  filters: {
    role:            string;
    experienceLevel: string[];
    location:        string;
    jobType:         string[];
    applyType:       string;
  };
  count:   number;
  profile: ProfileData;
}

// ─── CV upload ────────────────────────────────────────────────────────────────

export const uploadCv = async (file: File): Promise<CvExtractedData> => {
  const form = new FormData();
  form.append("file", file);

  const res = await fetch(`${API}/api/cv/upload`, { method: "POST", body: form });

  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`CV upload failed: ${detail}`);
  }

  return res.json() as Promise<CvExtractedData>;
};

// ─── Automation  (WebSocket + REST) ──────────────────────────────────────────

export const startAutomation = (
  params:       StartAutomationParams,
  onLog:        (log: LogEntry) => void,
  onProgress:   (current: number, total: number) => void,
  onScreenshot: (b64: string) => void          = () => {},
  onCompany:    (c: CompanyEntry) => void      = () => {},
  onCost:       (c: CostSummary) => void       = () => {},
): Promise<void> => {
  return new Promise((resolve, reject) => {
    const sessionId = crypto.randomUUID();
    const wsUrl     = `${WS}/ws/${sessionId}`;

    const ws = new WebSocket(wsUrl);
    let logCounter = 0;

    ws.onopen = () => {
      // WebSocket is live — now tell the backend to start
      fetch(`${API}/api/automation/start`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body:    JSON.stringify({ ...params, sessionId }),
      }).catch((err) => {
        ws.close();
        reject(err);
      });
    };

    ws.onmessage = (event: MessageEvent) => {
      let msg: { type: string; payload?: Record<string, unknown> };
      try {
        msg = JSON.parse(event.data as string);
      } catch {
        return;
      }

      if (msg.type === "ping") return;

      if (msg.type === "screenshot" && msg.payload) {
        onScreenshot(String(msg.payload.data ?? ""));
        return;
      }

      if (msg.type === "company" && msg.payload) {
        onCompany(msg.payload as unknown as CompanyEntry);
        return;
      }

      if (msg.type === "cost" && msg.payload) {
        onCost(msg.payload as unknown as CostSummary);
        return;
      }

      if (msg.type === "log" && msg.payload) {
        logCounter += 1;
        onLog({
          id:        logCounter,
          message:   String(msg.payload.message   ?? ""),
          type:      (msg.payload.logType as LogEntry["type"]) ?? "info",
          timestamp: new Date(String(msg.payload.timestamp ?? Date.now())),
        });
      }

      if (msg.type === "progress" && msg.payload) {
        onProgress(Number(msg.payload.current), Number(msg.payload.total));
      }

      if (msg.type === "completed") {
        ws.close();
        resolve();
      }

      if (msg.type === "error") {
        ws.close();
        // Surface the error as a final log entry then resolve gracefully
        onLog({
          id:        ++logCounter,
          message:   String(msg.payload?.message ?? "Automation error"),
          type:      "error",
          timestamp: new Date(),
        });
        resolve();
      }
    };

    ws.onerror = () => {
      reject(new Error("WebSocket connection error — is the backend running on port 8000?"));
    };

    ws.onclose = () => {
      // If the socket closed without a completed/error frame, resolve anyway
      resolve();
    };
  });
};
