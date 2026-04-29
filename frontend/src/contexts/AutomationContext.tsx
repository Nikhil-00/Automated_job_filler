import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import { LogEntry, CompanyEntry, CostSummary, StartAutomationParams } from '@/lib/mockApi';

const API = (import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000").replace(/\/$/, "");
const WS  = (import.meta.env.VITE_WS_URL      ?? "ws://localhost:8000").replace(/\/$/, "");

interface AutomationState {
  isRunning:   boolean;
  logs:        LogEntry[];
  progress:    { current: number; total: number };
  screenshot:  string | null;
  companies:   CompanyEntry[];
  costSummary: CostSummary | null;
  sessionId:   string | null;
  loginStatus: "idle" | "opening" | "logging" | "connected" | "error";
}

const initialPlatformState: AutomationState = {
  isRunning:   false,
  logs:        [],
  progress:    { current: 0, total: 0 },
  screenshot:  null,
  companies:   [],
  costSummary: null,
  sessionId:   null,
  loginStatus: "idle",
};

interface AutomationContextType {
  states:          Record<'linkedin' | 'naukri', AutomationState>;
  startAutomation: (params: StartAutomationParams) => Promise<void>;
  stopAutomation:  (platform: 'linkedin' | 'naukri') => Promise<void>;
  setLoginStatus:  (platform: 'linkedin' | 'naukri', status: AutomationState['loginStatus']) => void;
}

const AutomationContext = createContext<AutomationContextType | undefined>(undefined);

export const AutomationProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [states, setStates] = useState<Record<'linkedin' | 'naukri', AutomationState>>({
    linkedin: { ...initialPlatformState },
    naukri:   { ...initialPlatformState },
  });

  // wsRefs stores the active WebSocket per platform.
  // retryRefs stores the retry timeout handle for reconnection.
  // intentionalCloseRef: set true before we close a socket ourselves so onclose
  // knows not to mark the automation as stopped — we're just swapping connections.
  const wsRefs             = useRef<Record<string, WebSocket | null>>({});
  const retryRefs          = useRef<Record<string, ReturnType<typeof setTimeout> | null>>({});
  const intentionalCloseRef = useRef<Record<string, boolean>>({});
  const stateRef           = useRef(states);
  useEffect(() => { stateRef.current = states; }, [states]);

  const connectWebSocket = useCallback((platform: 'linkedin' | 'naukri', sessionId: string, attempt = 0) => {
    // Cancel any pending reconnect before opening a fresh connection
    const retryHandle = retryRefs.current[platform];
    if (retryHandle != null) {
      clearTimeout(retryHandle);
      retryRefs.current[platform] = null;
    }

    // Close any existing socket; flag it as intentional so onclose doesn't
    // incorrectly mark isRunning = false while we are just swapping sessions.
    const existing = wsRefs.current[platform];
    if (existing && existing.readyState < WebSocket.CLOSING) {
      intentionalCloseRef.current[platform] = true;
      existing.close();
    }

    const token  = sessionStorage.getItem("auth_token");
    const wsUrl  = `${WS}/ws/${sessionId}${token ? `?token=${encodeURIComponent(token)}` : ""}`;
    const ws     = new WebSocket(wsUrl);
    wsRefs.current[platform] = ws;

    let logCounter = stateRef.current[platform].logs.length;

    ws.onmessage = (event) => {
      let msg: { type: string; payload?: any };
      try { msg = JSON.parse(event.data); } catch { return; }
      if (msg.type === "ping") return;

      setStates(prev => {
        const current = prev[platform];
        const next    = { ...current };

        if (msg.type === "screenshot") {
          next.screenshot = msg.payload.data;
        } else if (msg.type === "company") {
          next.companies = [...next.companies, msg.payload];
        } else if (msg.type === "cost") {
          next.costSummary = msg.payload;
        } else if (msg.type === "progress") {
          next.progress = { current: Number(msg.payload.current), total: Number(msg.payload.total) };
        } else if (msg.type === "log") {
          logCounter++;
          next.logs = [...next.logs, {
            id:        logCounter,
            message:   msg.payload.message,
            type:      msg.payload.logType || "info",
            timestamp: new Date(msg.payload.timestamp || Date.now()),
          }];
          if (msg.payload.message?.toLowerCase().includes("logged in")) {
            next.loginStatus = "connected";
          }
        } else if (msg.type === "completed" || msg.type === "error") {
          next.isRunning = false;
        }

        return { ...prev, [platform]: next };
      });
    };

    ws.onclose = (ev) => {
      // If WE closed this socket (session swap / stop), do not touch isRunning.
      if (intentionalCloseRef.current[platform]) {
        intentionalCloseRef.current[platform] = false;
        return;
      }

      const isRunning = stateRef.current[platform]?.isRunning;

      // Unexpected close while automation is running → reconnect with backoff
      if (isRunning && ev.code !== 1000 && ev.code !== 4001) {
        const delay = Math.min(1000 * 2 ** attempt, 30000);
        retryRefs.current[platform] = setTimeout(() => {
          const sid = stateRef.current[platform]?.sessionId;
          if (sid && stateRef.current[platform]?.isRunning) {
            connectWebSocket(platform, sid, attempt + 1);
          }
        }, delay);
      } else {
        setStates(prev => ({
          ...prev,
          [platform]: { ...prev[platform], isRunning: false },
        }));
      }
    };

    ws.onerror = () => {
      // onclose fires after onerror — reconnect logic lives there
    };
  }, []);

  const startAutomation = async (params: StartAutomationParams) => {
    const { platform } = params;
    const proposedSessionId = crypto.randomUUID();

    setStates(prev => ({
      ...prev,
      [platform]: {
        ...initialPlatformState,
        isRunning: true,
        sessionId: proposedSessionId,
        progress: { current: 0, total: params.count },
      },
    }));

    try {
      // POST first so the server tells us the canonical sessionId.
      // If another session for this user+platform is already running the server
      // returns {status:"already_running", sessionId:<existing>} (still HTTP 200),
      // and we re-attach to that session instead of a dead one.
      const token = sessionStorage.getItem("auth_token");
      const res   = await fetch(`${API}/api/automation/start`, {
        method:  "POST",
        headers: {
          "Content-Type":  "application/json",
          ...(token ? { "Authorization": `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ ...params, sessionId: proposedSessionId }),
      });

      if (!res.ok) {
        const error = await res.json().catch(() => ({ detail: "Failed to start" }));
        throw new Error(error.detail);
      }

      const data = await res.json();
      // Use the server's authoritative sessionId (may differ on already_running)
      const activeSessionId: string = data.sessionId ?? proposedSessionId;

      if (activeSessionId !== proposedSessionId) {
        setStates(prev => ({
          ...prev,
          [platform]: { ...prev[platform], sessionId: activeSessionId },
        }));
      }

      // Connect after we know the real sessionId; history replay in the WebSocket
      // handler ensures no messages are lost during the POST round-trip.
      connectWebSocket(platform, activeSessionId);
    } catch (err: any) {
      setStates(prev => ({ ...prev, [platform]: { ...prev[platform], isRunning: false } }));
      throw err;
    }
  };

  const stopAutomation = async (platform: 'linkedin' | 'naukri') => {
    // Cancel any pending reconnect
    const retryHandle = retryRefs.current[platform];
    if (retryHandle != null) {
      clearTimeout(retryHandle);
      retryRefs.current[platform] = null;
    }

    // Mark the WS close as intentional so onclose doesn't fight us on isRunning
    const wsToClose = wsRefs.current[platform];
    if (wsToClose && wsToClose.readyState < WebSocket.CLOSING) {
      intentionalCloseRef.current[platform] = true;
      wsToClose.close();
    }

    const token = sessionStorage.getItem("auth_token");
    if (!token) return;

    try {
      await fetch(`${API}/api/automation/stop`, {
        method:  "POST",
        headers: { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
        body:    JSON.stringify({ platform }),
      });
      setStates(prev => ({ ...prev, [platform]: { ...prev[platform], isRunning: false } }));
    } catch (err) {
      console.error(`Failed to stop automation for ${platform}:`, err);
    }
  };

  const setLoginStatus = (platform: 'linkedin' | 'naukri', status: AutomationState['loginStatus']) => {
    setStates(prev => ({ ...prev, [platform]: { ...prev[platform], loginStatus: status } }));
  };

  // On mount: check for active sessions and re-attach
  useEffect(() => {
    const platforms: ('linkedin' | 'naukri')[] = ['linkedin', 'naukri'];
    const token = sessionStorage.getItem("auth_token");
    if (!token) return;

    platforms.forEach(async (p) => {
      try {
        const res  = await fetch(`${API}/api/automation/active-session/${p}`, {
          headers: { "Authorization": `Bearer ${token}` },
        });
        const data = await res.json();
        if (data.sessionId) {
          setStates(prev => ({
            ...prev,
            [p]: { ...prev[p], isRunning: true, sessionId: data.sessionId, loginStatus: "connected" },
          }));
          connectWebSocket(p, data.sessionId);
        }
      } catch (err) {
        console.error(`Failed to check active session for ${p}:`, err);
      }
    });
  }, []);

  // Kill all timers and sockets when the provider unmounts (SPA navigation away
  // from the dashboard). Without this, retry timers keep firing after unmount,
  // creating an infinite zombie WebSocket loop that fills the browser's
  // connection pool and blocks subsequent fetch() calls (e.g. login POST).
  useEffect(() => {
    return () => {
      (['linkedin', 'naukri'] as const).forEach(p => {
        const h = retryRefs.current[p];
        if (h != null) { clearTimeout(h); retryRefs.current[p] = null; }

        const ws = wsRefs.current[p];
        if (ws && ws.readyState < WebSocket.CLOSING) {
          intentionalCloseRef.current[p] = true;
          ws.close();
        }
      });
    };
  }, []);

  // Stop automation on tab close / full page reload
  useEffect(() => {
    const handleUnload = () => {
      const token = sessionStorage.getItem("auth_token");
      if (!token) return;
      (Object.keys(stateRef.current) as ('linkedin' | 'naukri')[]).forEach(p => {
        if (stateRef.current[p].isRunning) {
          fetch(`${API}/api/automation/stop`, {
            method:    "POST",
            headers:   { "Content-Type": "application/json", "Authorization": `Bearer ${token}` },
            body:      JSON.stringify({ platform: p }),
            keepalive: true,
          });
        }
      });
    };

    window.addEventListener('unload', handleUnload);
    return () => {
      window.removeEventListener('unload', handleUnload);
      handleUnload();
    };
  }, []);

  return (
    <AutomationContext.Provider value={{ states, startAutomation, stopAutomation, setLoginStatus }}>
      {children}
    </AutomationContext.Provider>
  );
};

export const useAutomation = () => {
  const context = useContext(AutomationContext);
  if (context === undefined) {
    throw new Error('useAutomation must be used within an AutomationProvider');
  }
  return context;
};
