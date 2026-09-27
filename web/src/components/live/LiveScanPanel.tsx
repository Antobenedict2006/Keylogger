"use client";

/**
 * LiveScanPanel
 * =============
 * Polls GET /api/live every POLL_INTERVAL_MS and renders the latest
 * process scan from the running Python detector using the same
 * MetricsCards + ProcessTable components used for the CSV upload flow.
 *
 * States
 * ------
 *  connecting  – first fetch in progress
 *  live        – data received, polling active
 *  stale       – last fetch succeeded but data is >15 s old
 *  error       – Python not running or returned an error
 *  paused      – user clicked Pause
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Activity,
  AlertCircle,
  Loader2,
  Pause,
  Play,
  Radio,
  RefreshCw,
  Wifi,
  WifiOff,
} from "lucide-react";
import { MetricsCards } from "@/components/dashboard/MetricsCards";
import { ProcessTable } from "@/components/dashboard/ProcessTable";
import { ScanSummary } from "@/lib/types";

// How often to refresh (ms)
const POLL_INTERVAL_MS = 3_000;
// After this many ms without a successful fetch, flag as stale
const STALE_THRESHOLD_MS = 15_000;

type PanelState = "connecting" | "live" | "stale" | "error" | "paused";

export function LiveScanPanel() {
  const [state, setState]           = useState<PanelState>("connecting");
  const [summary, setSummary]       = useState<ScanSummary | null>(null);
  const [errorMsg, setErrorMsg]     = useState<string>("");
  const [lastUpdated, setLastUpdated] = useState<number>(0);
  const [scanCount, setScanCount]   = useState(0);
  const intervalRef                 = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── fetch one scan ──────────────────────────────────────────────────────
  const fetchScan = useCallback(async () => {
    try {
      const res  = await fetch("/api/live", { cache: "no-store" });
      const data = await res.json();

      if (!res.ok || !data.success) {
        setErrorMsg(data.error ?? "Unknown error from Python detector.");
        setState("error");
        return;
      }

      // data.summary contains the ScanSummary with .results array attached
      setSummary(data.summary as ScanSummary);
      setLastUpdated(Date.now());
      setScanCount((c) => c + 1);
      setState("live");
      setErrorMsg("");
    } catch (err) {
      setErrorMsg(
        err instanceof Error ? err.message : "Network error — check console."
      );
      setState("error");
    }
  }, []);

  // ── polling loop ────────────────────────────────────────────────────────
  const startPolling = useCallback(() => {
    if (intervalRef.current) return;
    fetchScan(); // immediate first fetch
    intervalRef.current = setInterval(fetchScan, POLL_INTERVAL_MS);
  }, [fetchScan]);

  const stopPolling = useCallback(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  // Start on mount
  useEffect(() => {
    startPolling();
    return stopPolling;
  }, [startPolling, stopPolling]);

  // Mark stale if data is too old
  useEffect(() => {
    if (state !== "live" || lastUpdated === 0) return;
    const id = setInterval(() => {
      if (Date.now() - lastUpdated > STALE_THRESHOLD_MS) {
        setState("stale");
      }
    }, 2000);
    return () => clearInterval(id);
  }, [state, lastUpdated]);

  const handlePauseResume = () => {
    if (state === "paused") {
      setState("connecting");
      startPolling();
    } else {
      stopPolling();
      setState("paused");
    }
  };

  const handleRefresh = () => {
    stopPolling();
    setState("connecting");
    startPolling();
  };

  // ── helpers ─────────────────────────────────────────────────────────────
  const elapsed = lastUpdated
    ? Math.round((Date.now() - lastUpdated) / 1000)
    : null;

  const statusDot =
    state === "live"
      ? "bg-emerald-500"
      : state === "stale"
      ? "bg-amber-500"
      : state === "error"
      ? "bg-rose-500"
      : state === "paused"
      ? "bg-slate-500"
      : "bg-indigo-500 animate-pulse";

  // ── render ───────────────────────────────────────────────────────────────
  return (
    <div className="space-y-6">

      {/* ── Status bar ─────────────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-900/60 px-5 py-3 backdrop-blur-md">
        {/* Left: indicator + label */}
        <div className="flex items-center gap-3">
          <span className={`h-2.5 w-2.5 rounded-full ${statusDot}`} />
          <span className="text-sm font-semibold text-white">
            {state === "live"    && "Live — Python Detector Connected"}
            {state === "stale"   && "Stale — Waiting for next scan…"}
            {state === "error"   && "Disconnected — Python not running"}
            {state === "paused"  && "Paused"}
            {state === "connecting" && "Connecting to Python detector…"}
          </span>
          {state === "live" && (
            <span className="flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-400">
              <Radio className="h-3 w-3" />
              Polling every {POLL_INTERVAL_MS / 1000}s
            </span>
          )}
        </div>

        {/* Right: stats + controls */}
        <div className="flex items-center gap-3 text-xs text-slate-400">
          {scanCount > 0 && (
            <span className="flex items-center gap-1">
              <Activity className="h-3.5 w-3.5" />
              {scanCount} scan{scanCount !== 1 ? "s" : ""}
            </span>
          )}
          {elapsed !== null && state !== "paused" && (
            <span>Updated {elapsed}s ago</span>
          )}
          <button
            onClick={handleRefresh}
            className="rounded-lg border border-slate-700 bg-slate-800 p-1.5 text-slate-300 hover:bg-slate-700 hover:text-white"
            title="Force refresh"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
          <button
            onClick={handlePauseResume}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-slate-300 hover:bg-slate-700 hover:text-white"
          >
            {state === "paused" ? (
              <><Play className="h-3.5 w-3.5" /> Resume</>
            ) : (
              <><Pause className="h-3.5 w-3.5" /> Pause</>
            )}
          </button>
        </div>
      </div>

      {/* ── Error state ────────────────────────────────────────────────── */}
      {state === "error" && (
        <div className="flex items-start gap-4 rounded-xl border border-rose-500/30 bg-rose-950/20 p-5">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-rose-500/10 text-rose-400">
            <WifiOff className="h-5 w-5" />
          </div>
          <div>
            <p className="font-semibold text-rose-300">
              Python Detector Not Reachable
            </p>
            <p className="mt-1 text-sm text-rose-400/80">{errorMsg}</p>
            <div className="mt-3 space-y-1 rounded-lg bg-slate-900/60 p-3 font-mono text-xs text-slate-400">
              <p className="text-slate-300 font-semibold">To connect:</p>
              <p>1. Open a terminal in the project root</p>
              <p>2. Run: <span className="text-emerald-400">python main.py</span></p>
              <p>3. This panel will auto-connect within {POLL_INTERVAL_MS / 1000}s</p>
            </div>
          </div>
        </div>
      )}

      {/* ── Connecting spinner ─────────────────────────────────────────── */}
      {state === "connecting" && (
        <div className="flex flex-col items-center justify-center gap-3 py-12 text-slate-400">
          <Loader2 className="h-8 w-8 animate-spin text-indigo-400" />
          <p className="text-sm">Connecting to Python detector on port 8765…</p>
        </div>
      )}

      {/* ── Live data ──────────────────────────────────────────────────── */}
      {(state === "live" || state === "stale" || state === "paused") && summary && (
        <>
          {state === "stale" && (
            <div className="flex items-center gap-2 rounded-xl border border-amber-500/30 bg-amber-950/20 px-4 py-2.5 text-sm text-amber-300">
              <AlertCircle className="h-4 w-4 shrink-0" />
              Data may be stale — Python scan is taking longer than expected.
            </div>
          )}
          {state === "paused" && (
            <div className="flex items-center gap-2 rounded-xl border border-slate-700 bg-slate-900/40 px-4 py-2.5 text-sm text-slate-400">
              <Pause className="h-4 w-4 shrink-0" />
              Polling paused — showing last known scan.
            </div>
          )}

          {/* KPI cards */}
          <MetricsCards summary={summary} />

          {/* Process table */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-white">
                Live Process Scan
                <span className="ml-2 text-sm font-normal text-slate-400">
                  ({summary.results?.length ?? 0} processes)
                </span>
              </h2>
              <div className="flex items-center gap-1.5 text-xs text-slate-400">
                <Wifi className="h-3.5 w-3.5 text-emerald-400" />
                <span>
                  Scan ID:{" "}
                  <span className="font-mono text-slate-300">{summary.id}</span>
                </span>
              </div>
            </div>
            {summary.results && summary.results.length > 0 ? (
              <ProcessTable results={summary.results} />
            ) : (
              <div className="flex flex-col items-center justify-center gap-2 rounded-xl border border-slate-800 bg-slate-900/40 py-12 text-slate-500">
                <Activity className="h-8 w-8" />
                <p className="text-sm">
                  Waiting for the first scan to complete…
                </p>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
