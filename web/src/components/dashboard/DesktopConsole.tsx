"use client";

import { useCallback, useEffect, useState } from "react";
import { ConcentricLoading } from "@/components/dashboard/ConcentricLoading";
import {
  Activity,
  AlertTriangle,
  Bell,
  Brain,
  Check,
  ChevronDown,
  ChevronUp,
  Clock3,
  GraduationCap,
  History,
  LoaderCircle,
  Play,
  RefreshCw,
  ShieldAlert,
  X,
} from "lucide-react";

type ConsoleTab = "alerts" | "history" | "statistics" | "training" | "behavior";
type ApiResponse = { success: boolean; error?: string; message?: string; [key: string]: unknown };
type AlertRow = {
  timestamp: number;
  pid: number;
  name: string;
  exe?: string;
  riskLevel: string;
  score: number;
  reasons?: string[];
  actioned?: boolean;
};
type HistoryRow = {
  id: number;
  detected_at: number;
  pid: number;
  process_name: string;
  risk_level: string;
  score: number;
  actioned: boolean;
  reasons?: string[] | string;
};

const ROW_LIMIT = 10;

const tabs: { id: ConsoleTab; label: string; icon: typeof Bell }[] = [
  { id: "alerts", label: "Live Alerts", icon: Bell },
  { id: "history", label: "History", icon: History },
  { id: "statistics", label: "Statistics", icon: Activity },
  { id: "training", label: "Train Model", icon: GraduationCap },
  { id: "behavior", label: "Behavior", icon: Brain },
];

function formatTime(epoch?: number) {
  return epoch ? new Date(epoch * 1000).toLocaleString() : "--";
}

function riskStyle(risk: string) {
  const value = risk.toLowerCase();
  if (value === "malicious") return "text-rose-300 bg-rose-400/10";
  if (value === "suspicious") return "text-amber-300 bg-amber-400/10";
  return "text-emerald-300 bg-emerald-400/10";
}

export function DesktopConsole() {
  const [activeTab, setActiveTab] = useState<ConsoleTab>("alerts");
  const [alerts, setAlerts] = useState<AlertRow[]>([]);
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [alertsExpanded, setAlertsExpanded] = useState(false);
  const [historyExpanded, setHistoryExpanded] = useState(false);
  const [statistics, setStatistics] = useState<Record<string, unknown> | null>(null);
  const [behavior, setBehavior] = useState<Record<string, unknown> | null>(null);
  const [behaviorSettings, setBehaviorSettings] = useState<Record<string, unknown>>({});
  const [training, setTraining] = useState<Record<string, unknown> | null>(null);
  const [notificationsEnabled, setNotificationsEnabled] = useState(true);
  const [savingSettings, setSavingSettings] = useState(false);
  const [behaviorActionBusy, setBehaviorActionBusy] = useState(false);
  const [risk, setRisk] = useState("all");
  const [hours, setHours] = useState(24);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busyPid, setBusyPid] = useState<number | null>(null);
  const [startingRecording, setStartingRecording] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const refresh = useCallback(async () => {
    const endpointByTab: Record<ConsoleTab, string> = {
      alerts: "/api/console/alerts",
      history: `/api/console/history?limit=200&hours=${hours}${risk === "all" ? "" : `&risk=${risk}`}`,
      statistics: "/api/console/statistics",
      training: "/api/console/train/status",
      behavior: "/api/console/behavior",
    };
    try {
      const response = await fetch(endpointByTab[activeTab], { cache: "no-store" });
      const data = (await response.json()) as ApiResponse;
      if (!response.ok || !data.success) throw new Error(data.error || "Unable to load desktop data.");
      setError("");
      if (activeTab === "alerts") setAlerts((data.alerts as AlertRow[]) ?? []);
      if (activeTab === "history") setHistory((data.history as HistoryRow[]) ?? []);
      if (activeTab === "statistics") setStatistics(data.statistics as Record<string, unknown>);
      if (activeTab === "behavior") {
        const profile = data.behavior as Record<string, unknown>;
        setBehavior(profile);
        setBehaviorSettings((profile.settings as Record<string, unknown>) ?? {});
      }
      if (activeTab === "training") setTraining(data.training as Record<string, unknown>);
    } catch (cause) {
      if (activeTab === "alerts") setAlerts([]);
      if (activeTab === "history") setHistory([]);
      if (activeTab === "statistics") setStatistics(null);
      if (activeTab === "behavior") setBehavior(null);
      if (activeTab === "training") setTraining(null);
      setError(cause instanceof Error ? cause.message : "Unable to load desktop data.");
    }
  }, [activeTab, hours, risk]);

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    const interval = window.setInterval(() => void refresh(), 5000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(interval);
    };
  }, [refresh, refreshKey]);

  useEffect(() => {
    void fetch("/api/console/settings/notifications", { cache: "no-store" })
      .then((response) => response.json())
      .then((data: { enabled?: boolean }) => {
        if (typeof data.enabled === "boolean") setNotificationsEnabled(data.enabled);
      })
      .catch(() => undefined);
  }, []);

  const takeAction = async (pid: number, action: string) => {
    setBusyPid(pid);
    setNotice("");
    try {
      const response = await fetch("/api/console/actions", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pid, action }),
      });
      const data = (await response.json()) as ApiResponse;
      if (!response.ok || !data.success) throw new Error(data.error || "Action could not be completed.");
      setNotice(data.message || `${action} action submitted.`);
      await refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Action could not be completed.");
    } finally {
      setBusyPid(null);
    }
  };

  const startRecording = async () => {
    setStartingRecording(true);
    setNotice("");
    try {
      const response = await fetch("/api/console/recording/start", { method: "POST" });
      const data = (await response.json()) as ApiResponse;
      if (!response.ok || !data.success) throw new Error(data.error || "Recording could not be started.");
      setNotice(data.message || "Behavior recording started.");
      setRefreshKey((key) => key + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Recording could not be started.");
    } finally {
      setStartingRecording(false);
    }
  };

  const toggleNotifications = async () => {
    const nextEnabled = !notificationsEnabled;
    try {
      const response = await fetch("/api/console/settings/notifications", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: nextEnabled }),
      });
      const data = (await response.json()) as ApiResponse;
      if (!response.ok || !data.success) throw new Error(data.error || "Notification setting could not be updated.");
      setNotificationsEnabled(nextEnabled);
      setNotice(`Desktop notifications ${nextEnabled ? "enabled" : "disabled"}.`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Notification setting could not be updated.");
    }
  };

  const saveBehaviorSettings = async () => {
    setSavingSettings(true);
    try {
      const response = await fetch("/api/console/behavior/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(behaviorSettings),
      });
      const data = (await response.json()) as ApiResponse;
      if (!response.ok || !data.success) throw new Error(data.error || "Behavior settings could not be saved.");
      setBehaviorSettings(data.settings as Record<string, unknown>);
      setNotice("Behavior settings saved to the local detector.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Behavior settings could not be saved.");
    } finally {
      setSavingSettings(false);
    }
  };

  const runBehaviorAction = async (action: "confirm" | "retrain") => {
    setBehaviorActionBusy(true);
    try {
      const response = await fetch("/api/console/behavior/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
      const data = (await response.json()) as ApiResponse;
      if (!response.ok || !data.success) throw new Error(data.error || "Behavior action failed.");
      setNotice(data.message || "Behavior action completed.");
      setRefreshKey((key) => key + 1);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Behavior action failed.");
    } finally {
      setBehaviorActionBusy(false);
    }
  };

  const setBehaviorSetting = (key: string, value: unknown) => {
    setBehaviorSettings((current) => ({ ...current, [key]: value }));
  };

  const visibleAlerts = alerts.slice(0, alertsExpanded ? alerts.length : ROW_LIMIT);
  const visibleHistory = history.slice(0, historyExpanded ? history.length : ROW_LIMIT);
  const recordingRunning = training?.recording === true;

  return (
    <section className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900/70">
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold text-white">Desktop Detection Console</h2>
          <p className="mt-0.5 text-xs text-slate-400">Connected to the local detector service</p>
        </div>
        <button
          onClick={() => setRefreshKey((key) => key + 1)}
          className="inline-flex items-center gap-2 rounded-md border border-slate-700 px-3 py-2 text-xs font-medium text-slate-300 hover:border-slate-500 hover:text-white"
          title="Refresh current view"
        >
          <RefreshCw className="h-3.5 w-3.5" /> Refresh
        </button>
        <button
          onClick={() => void toggleNotifications()}
          aria-label={`${notificationsEnabled ? "Disable" : "Enable"} desktop notifications`}
          title={`Desktop notifications ${notificationsEnabled ? "on" : "off"}`}
          className={`rounded-md border p-2 ${notificationsEnabled ? "border-emerald-500/40 text-emerald-300" : "border-slate-700 text-slate-500"}`}
        >
          <Bell className="h-4 w-4" />
        </button>
      </div>

      <div className="flex overflow-x-auto border-b border-slate-800 px-3" role="tablist" aria-label="Desktop detection views">
        {tabs.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            role="tab"
            aria-selected={activeTab === id}
            onClick={() => { setActiveTab(id); setNotice(""); }}
            className={`inline-flex shrink-0 items-center gap-2 border-b-2 px-3 py-3 text-xs font-medium transition-colors ${activeTab === id ? "border-cyan-400 text-cyan-300" : "border-transparent text-slate-400 hover:text-slate-200"}`}
          >
            <Icon className="h-3.5 w-3.5" /> {label}
          </button>
        ))}
      </div>

      {(error || notice) && (
        <div className={`mx-4 mt-4 flex items-start gap-2 rounded-md border px-3 py-2 text-xs ${error ? "border-rose-500/30 bg-rose-500/10 text-rose-200" : "border-emerald-500/30 bg-emerald-500/10 text-emerald-200"}`}>
          {error ? <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> : <Check className="mt-0.5 h-3.5 w-3.5 shrink-0" />}
          <span>{error || notice}</span>
        </div>
      )}

      <div className="p-4 sm:p-5">
        {activeTab === "alerts" && (
          <div>
            <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-xs">
              <thead className="text-[11px] uppercase text-slate-500">
                <tr>{["Time", "PID", "Process", "Risk", "Score", "Indicators", "Actions"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr>
              </thead>
              <tbody className="divide-y divide-slate-800/80">
                {visibleAlerts.map((row) => (
                  <tr key={`${row.pid}-${row.timestamp}`} className="text-slate-300">
                    <td className="whitespace-nowrap px-3 py-3 text-slate-400">{formatTime(row.timestamp)}</td>
                    <td className="px-3 py-3 font-mono">{row.pid}</td>
                    <td className="px-3 py-3 font-medium text-white">{row.name}</td>
                    <td className="px-3 py-3"><span className={`rounded px-2 py-1 text-[10px] font-semibold uppercase ${riskStyle(row.riskLevel)}`}>{row.riskLevel}</span></td>
                    <td className="px-3 py-3">{row.score}%</td>
                    <td className="max-w-[260px] truncate px-3 py-3 text-slate-400" title={row.reasons?.join("; ")}>{row.reasons?.join("; ") || "No indicators recorded"}</td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-1.5">
                        {[{ id: "terminate", label: "Terminate", icon: X, tone: "text-rose-300" }, { id: "quarantine", label: "Quarantine", icon: ShieldAlert, tone: "text-amber-300" }, { id: "whitelist", label: "Whitelist", icon: Check, tone: "text-emerald-300" }, { id: "dismiss", label: "Dismiss", icon: X, tone: "text-slate-300" }].map(({ id, label, icon: Icon, tone }) => (
                          <button key={id} disabled={busyPid === row.pid} onClick={() => void takeAction(row.pid, id)} title={label} aria-label={`${label} ${row.name}`} className={`rounded border border-slate-700 p-1.5 hover:bg-slate-800 disabled:opacity-40 ${tone}`}>
                            {busyPid === row.pid ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <Icon className="h-3.5 w-3.5" />}
                          </button>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
                {!alerts.length && <tr><td colSpan={7} className="px-3 py-4"><ConcentricLoading /></td></tr>}
              </tbody>
            </table>
            </div>
            {alerts.length > ROW_LIMIT && (
              <button
                type="button"
                aria-expanded={alertsExpanded}
                onClick={() => setAlertsExpanded((expanded) => !expanded)}
                className="mt-3 inline-flex items-center gap-1.5 rounded border border-slate-700 px-3 py-2 text-xs font-medium text-slate-300 hover:border-cyan-500/50 hover:text-cyan-200"
              >
                {alertsExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                {alertsExpanded ? "Show 10 alerts" : `Show all ${alerts.length} alerts`}
              </button>
            )}
          </div>
        )}

        {activeTab === "history" && (
          <>
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <label className="text-xs text-slate-400">Risk
                <select value={risk} onChange={(event) => { setRisk(event.target.value); setHistoryExpanded(false); }} className="ml-2 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-200">
                  <option value="all">All</option><option value="malicious">Malicious</option><option value="suspicious">Suspicious</option><option value="safe">Safe</option>
                </select>
              </label>
              <label className="text-xs text-slate-400">Time range
                <select value={hours} onChange={(event) => { setHours(Number(event.target.value)); setHistoryExpanded(false); }} className="ml-2 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-200">
                  <option value={1}>1 hour</option><option value={24}>24 hours</option><option value={168}>7 days</option><option value={720}>30 days</option>
                </select>
              </label>
              <span className="text-xs text-slate-500">{history.length} detections</span>
              <div className="ml-auto flex gap-2">
                {(["csv", "json", "pdf"] as const).map((format) => (
                  <a key={format} href={`/api/console/history/export?format=${format}`} className="rounded border border-slate-700 px-2.5 py-1.5 text-[11px] font-medium uppercase text-slate-300 hover:border-cyan-500/50 hover:text-cyan-200">
                    {format}
                  </a>
                ))}
              </div>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[650px] text-left text-xs">
                <thead className="text-[11px] uppercase text-slate-500"><tr>{["Date / time", "PID", "Process", "Risk", "Score", "Actioned", "Indicators"].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
                <tbody className="divide-y divide-slate-800/80">
                  {visibleHistory.map((row) => <tr key={row.id} className="text-slate-300">
                    <td className="whitespace-nowrap px-3 py-3 text-slate-400">{formatTime(row.detected_at)}</td><td className="px-3 py-3 font-mono">{row.pid}</td><td className="px-3 py-3 font-medium text-white">{row.process_name}</td>
                    <td className="px-3 py-3"><span className={`rounded px-2 py-1 text-[10px] font-semibold uppercase ${riskStyle(row.risk_level)}`}>{row.risk_level}</span></td><td className="px-3 py-3">{Math.round(row.score * 100)}%</td><td className="px-3 py-3">{row.actioned ? "Yes" : "No"}</td><td className="max-w-[240px] truncate px-3 py-3 text-slate-400">{Array.isArray(row.reasons) ? row.reasons.join("; ") : row.reasons || "--"}</td>
                  </tr>)}
                  {!history.length && <tr><td colSpan={7} className="px-3 py-4"><ConcentricLoading /></td></tr>}
                </tbody>
              </table>
            </div>
            {history.length > ROW_LIMIT && (
              <button
                type="button"
                aria-expanded={historyExpanded}
                onClick={() => setHistoryExpanded((expanded) => !expanded)}
                className="mt-3 inline-flex items-center gap-1.5 rounded border border-slate-700 px-3 py-2 text-xs font-medium text-slate-300 hover:border-cyan-500/50 hover:text-cyan-200"
              >
                {historyExpanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
                {historyExpanded ? "Show 10 detections" : `Show all ${history.length} detections`}
              </button>
            )}
          </>
        )}

        {activeTab === "statistics" && statistics && (
          <>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              {[{ label: "Total detections", key: "totalDetections", tone: "text-cyan-300" }, { label: "Malicious", key: "malicious", tone: "text-rose-300" }, { label: "Suspicious", key: "suspicious", tone: "text-amber-300" }, { label: "Actioned", key: "actioned", tone: "text-emerald-300" }].map((item) => <div key={item.key} className="border-l-2 border-slate-700 bg-slate-950/60 px-4 py-3"><p className="text-xs text-slate-400">{item.label}</p><p className={`mt-1 text-2xl font-semibold ${item.tone}`}>{String(statistics[item.key] ?? 0)}</p></div>)}
            </div>
            <div className="mt-5 grid gap-4 md:grid-cols-2">
              <div className="border-t border-slate-800 pt-4"><h3 className="text-sm font-semibold text-white">Actions taken</h3>
                <div className="mt-3 space-y-2">{Object.entries((statistics.actionCounts as Record<string, number>) ?? {}).map(([action, count]) => <div key={action} className="flex justify-between text-xs text-slate-300"><span className="capitalize">{action}</span><span>{count}</span></div>)}
                  {!Object.keys((statistics.actionCounts as Record<string, number>) ?? {}).length && <p className="text-xs text-slate-500">No actions recorded.</p>}
                </div>
              </div>
              <div className="border-t border-slate-800 pt-4"><h3 className="text-sm font-semibold text-white">Detection engine</h3><p className="mt-3 text-xs text-slate-300">{String(statistics.modelStatus ?? "Unknown")}</p></div>
            </div>
          </>
        )}

        {activeTab === "training" && (
          <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
            <div className="max-w-xl">
              <p className="text-sm font-semibold text-white">Behavior recording</p>
              <p className="mt-1 text-xs leading-5 text-slate-400">Starts the existing backend process recorder used by personalized training.</p>
              <p className="mt-3 flex items-center gap-1.5 text-xs text-slate-400"><Clock3 className="h-3.5 w-3.5" /> Captured processes: {String(training?.recording_count ?? 0)}</p>
              <p className="mt-2 text-xs text-slate-300">{recordingRunning ? `Recording active for ${String(training?.recording_elapsed_seconds ?? 0)} seconds.` : `Latest saved recording: ${String(training?.latest_recording || "none")}`}</p>
            </div>
            <button onClick={() => void startRecording()} disabled={startingRecording || recordingRunning} className="inline-flex shrink-0 items-center justify-center gap-2 rounded-md bg-cyan-500 px-4 py-2.5 text-xs font-semibold text-slate-950 hover:bg-cyan-400 disabled:cursor-not-allowed disabled:opacity-40">
              {startingRecording ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
              {recordingRunning ? "Recording active" : "Start recording"}
            </button>
          </div>
        )}

        {activeTab === "behavior" && behavior && (
          <>
            <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-800 pb-4">
              <div><p className="text-sm font-semibold text-white">Local behavioral analysis</p><p className="mt-1 text-xs text-slate-400">{String(behavior.verdict ?? "INSUFFICIENT_DATA")}</p></div>
              <span className={`rounded px-2.5 py-1 text-xs font-semibold ${behavior.status === "green" ? "bg-emerald-400/10 text-emerald-300" : behavior.status === "grey" ? "bg-slate-700 text-slate-300" : "bg-amber-400/10 text-amber-300"}`}>{behavior.enabled ? "Enabled" : "Unavailable"}</span>
            </div>
            <div className="mt-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
              {[{ label: "Typing speed", value: `${behavior.typingSpeedWPM ?? 0} WPM` }, { label: "Keystroke dwell", value: `${behavior.keystrokeDwellMean ?? 0} ms` }, { label: "Keystroke flight", value: `${behavior.keystrokeFlightMean ?? 0} ms` }, { label: "Mouse speed", value: `${behavior.mouseSpeedMean ?? 0} px/s` }, { label: "Keystrokes", value: behavior.keystrokes ?? 0 }, { label: "Mouse movements", value: behavior.mouseMovements ?? 0 }, { label: "Mouse clicks", value: behavior.mouseClicks ?? 0 }, { label: "Similarity", value: `${behavior.similarityScore ?? 100}%` }].map((metric) => <div key={metric.label} className="bg-slate-950/60 px-3 py-3"><p className="text-[11px] text-slate-500">{metric.label}</p><p className="mt-1 text-sm font-semibold text-slate-100">{String(metric.value)}</p></div>)}
            </div>
            <p className="mt-4 text-xs text-slate-400">Baseline: {behavior.baselineAvailable ? behavior.trainingComplete ? "training complete" : "learning" : "not established"} · Keyboard similarity {String(behavior.keyboardSimilarity)}% · Mouse similarity {String(behavior.mouseSimilarity)}%</p>
            {!!(behavior.explanations as string[] | undefined)?.length && <ul className="mt-3 list-inside list-disc space-y-1 text-xs text-amber-200">{(behavior.explanations as string[]).map((item) => <li key={item}>{item}</li>)}</ul>}
            <div className="mt-5 border-t border-slate-800 pt-4">
              <div className="flex flex-wrap gap-2">
                <button onClick={() => void runBehaviorAction("confirm")} disabled={behaviorActionBusy} className="rounded-md border border-emerald-500/40 px-3 py-2 text-xs font-medium text-emerald-300 disabled:opacity-50">This Was Me</button>
                <button onClick={() => void runBehaviorAction("retrain")} disabled={behaviorActionBusy} className="rounded-md border border-amber-500/40 px-3 py-2 text-xs font-medium text-amber-300 disabled:opacity-50">Retrain baseline</button>
              </div>
            </div>
            <div className="mt-5 border-t border-slate-800 pt-4">
              <h3 className="text-sm font-semibold text-white">Behavior settings</h3>
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                {[
                  ["enabled", "Behavior analysis"],
                  ["mouse_tracking_enabled", "Mouse dynamics"],
                  ["auto_pause_on_activity", "Auto-pause during high activity"],
                  ["adaptive_baseline", "Adaptive baseline"],
                  ["desktop_notify", "Behavior anomaly notifications"],
                  ["anonymize_export_timestamps", "Anonymize session export times"],
                ].map(([key, label]) => (
                  <label key={key} className="flex items-center gap-2 text-xs text-slate-300">
                    <input type="checkbox" checked={Boolean(behaviorSettings[key])} onChange={(event) => setBehaviorSetting(key, event.target.checked)} className="accent-cyan-500" />
                    {label}
                  </label>
                ))}
                <label className="text-xs text-slate-400">Mouse tracking precision
                  <select value={String(behaviorSettings.mouse_precision ?? "normal")} onChange={(event) => setBehaviorSetting("mouse_precision", event.target.value)} className="ml-2 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-200">
                    <option value="high">High · 50 Hz</option><option value="normal">Normal · 20 Hz</option><option value="low">Low · 10 Hz</option>
                  </select>
                </label>
              </div>
              <div className="mt-3 flex flex-wrap items-center justify-between gap-3">
                <p className="text-[11px] text-slate-500">Mouse callback: {String(((behavior.mousePerformance as Record<string, unknown> | undefined)?.avg_callback_latency_ms ?? "--"))} ms</p>
                <button onClick={() => void saveBehaviorSettings()} disabled={savingSettings} className="rounded-md bg-cyan-500 px-3 py-2 text-xs font-semibold text-slate-950 disabled:opacity-50">{savingSettings ? "Saving..." : "Save settings"}</button>
              </div>
            </div>
            <div className="mt-5 border-t border-slate-800 pt-4">
              <h3 className="text-sm font-semibold text-white">Behavior data exports</h3>
              <div className="mt-3 flex flex-wrap gap-2">
                {[["keyboard", "Keyboard profile"], ["mouse", "Mouse profile"], ["combined", "Combined profile"], ["session-hour", "Last hour"], ["session-day", "24-hour session"], ["comparison", "Comparison report"]].map(([kind, label]) => (
                  <a key={kind} href={`/api/console/behavior/export/${kind}`} className="rounded border border-slate-700 px-2.5 py-2 text-[11px] text-slate-300 hover:border-cyan-500/50 hover:text-cyan-200">{label} JSON</a>
                ))}
              </div>
            </div>
            {!behavior.available && <p className="mt-3 text-xs text-slate-500">The local keyboard/mouse listener is unavailable on the detector.</p>}
          </>
        )}
      </div>
    </section>
  );
}