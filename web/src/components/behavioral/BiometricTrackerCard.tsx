"use client";

import React, { useState, useEffect, useRef } from "react";
import { BrowserBiometricsCollector } from "@/lib/behavioral/browser-tracker";
import { BiometricProfile } from "@/lib/types";
import { Fingerprint, MousePointer2, Keyboard, ShieldCheck, AlertTriangle, RefreshCw, Gauge } from "lucide-react";

export function BiometricTrackerCard() {
  const [profile, setProfile] = useState<BiometricProfile>({
    keystrokeDwellMean: 0,
    keystrokeFlightMean: 0,
    typingSpeedWPM: 0,
    mouseSpeedMean: 0,
    mouseAccelerationMean: 0,
    mouseStraightness: 0,
    anomalyScore: 0,
    confidence: 0,
    verdict: "INSUFFICIENT_DATA",
  });

  const [inputVal, setInputVal] = useState("");
  const trackerRef = useRef<BrowserBiometricsCollector | null>(null);

  useEffect(() => {
    trackerRef.current = new BrowserBiometricsCollector();

    const handleKeyDown = (e: KeyboardEvent) => trackerRef.current?.onKeyDown(e);
    const handleKeyUp = (e: KeyboardEvent) => trackerRef.current?.onKeyUp(e);
    const handleMouseMove = (e: MouseEvent) => trackerRef.current?.onMouseMove(e);

    // Passive listeners — never block the browser's input pipeline
    window.addEventListener("keydown", handleKeyDown, { passive: true });
    window.addEventListener("keyup", handleKeyUp, { passive: true });
    window.addEventListener("mousemove", handleMouseMove, { passive: true });

    // Update the displayed profile at 200 ms — smooth enough for the human eye,
    // half the CPU cost of the previous 500 ms poll. Skip updates when the tab
    // is not visible so background tabs waste zero resources.
    let intervalId: ReturnType<typeof setInterval> | null = null;

    const startInterval = () => {
      if (intervalId !== null) return;
      intervalId = setInterval(() => {
        if (trackerRef.current) {
          setProfile(trackerRef.current.getProfile());
        }
      }, 200);
    };

    const stopInterval = () => {
      if (intervalId !== null) {
        clearInterval(intervalId);
        intervalId = null;
      }
    };

    const handleVisibilityChange = () => {
      if (document.hidden) {
        stopInterval();
      } else {
        startInterval();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    startInterval(); // begin immediately

    return () => {
      stopInterval();
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("keyup", handleKeyUp);
      window.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("visibilitychange", handleVisibilityChange);
    };
  }, []);

  const handleReset = () => {
    trackerRef.current?.reset();
    setInputVal("");
    setProfile({
      keystrokeDwellMean: 0,
      keystrokeFlightMean: 0,
      typingSpeedWPM: 0,
      mouseSpeedMean: 0,
      mouseAccelerationMean: 0,
      mouseStraightness: 0,
      anomalyScore: 0,
      confidence: 0,
      verdict: "INSUFFICIENT_DATA",
    });
  };

  return (
    <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-md">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-500/10 text-purple-400">
            <Fingerprint className="h-5 w-5" />
          </div>
          <div>
            <h2 className="text-base font-semibold text-white">Live In-Browser Behavioral Biometrics</h2>
            <p className="text-xs text-slate-400">
              Zero-hook privacy-preserving biometrics (Dwell time, Flight time, Mouse kinematics)
            </p>
          </div>
        </div>

        <button
          onClick={handleReset}
          className="flex items-center gap-1.5 rounded-lg border border-slate-800 bg-slate-950/60 px-2.5 py-1 text-xs text-slate-400 hover:border-slate-700 hover:text-white"
        >
          <RefreshCw className="h-3 w-3" />
          Reset Baseline
        </button>
      </div>

      {/* Interactive Typing Test Playground */}
      <div className="mt-5 grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="space-y-3">
          <label className="text-xs font-medium text-slate-300">
            Interactive Biometric Test Field (Type or move mouse):
          </label>
          <textarea
            value={inputVal}
            onChange={(e) => setInputVal(e.target.value)}
            placeholder="Type a sentence here to analyze your natural typing cadence and keystroke dynamics in real-time..."
            className="h-28 w-full rounded-xl border border-slate-800 bg-slate-950/60 p-3 text-xs text-slate-200 placeholder-slate-500 focus:border-purple-500 focus:outline-none focus:ring-1 focus:ring-purple-500"
          />

          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Biometric Confidence: {profile.confidence}%</span>
            <div className="h-1.5 w-32 rounded-full bg-slate-800 overflow-hidden">
              <div
                className="h-full bg-purple-500 transition-all duration-300"
                style={{ width: `${profile.confidence}%` }}
              />
            </div>
          </div>
        </div>

        {/* Biometrics Metrics Grid */}
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-xl border border-slate-800/80 bg-slate-950/40 p-3">
            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <Keyboard className="h-3.5 w-3.5 text-indigo-400" />
              <span>Dwell Time</span>
            </div>
            <p className="mt-1 text-lg font-bold text-white">
              {profile.keystrokeDwellMean} <span className="text-xs font-normal text-slate-500">ms</span>
            </p>
            <p className="text-[10px] text-slate-500">Key hold duration</p>
          </div>

          <div className="rounded-xl border border-slate-800/80 bg-slate-950/40 p-3">
            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <Gauge className="h-3.5 w-3.5 text-indigo-400" />
              <span>Typing Cadence</span>
            </div>
            <p className="mt-1 text-lg font-bold text-white">
              {profile.typingSpeedWPM} <span className="text-xs font-normal text-slate-500">WPM</span>
            </p>
            <p className="text-[10px] text-slate-500">Flight: {profile.keystrokeFlightMean} ms</p>
          </div>

          <div className="rounded-xl border border-slate-800/80 bg-slate-950/40 p-3">
            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <MousePointer2 className="h-3.5 w-3.5 text-purple-400" />
              <span>Mouse Velocity</span>
            </div>
            <p className="mt-1 text-lg font-bold text-white">
              {profile.mouseSpeedMean} <span className="text-xs font-normal text-slate-500">px/s</span>
            </p>
            <p className="text-[10px] text-slate-500">Accel: {profile.mouseAccelerationMean} px/s²</p>
          </div>

          <div className="rounded-xl border border-slate-800/80 bg-slate-950/40 p-3">
            <div className="flex items-center gap-1.5 text-xs text-slate-400">
              <Fingerprint className="h-3.5 w-3.5 text-purple-400" />
              <span>Biometric Verdict</span>
            </div>
            <div className="mt-1 flex items-center gap-1">
              {profile.verdict === "GENUINE_USER" ? (
                <span className="text-xs font-semibold text-emerald-400">Genuine User</span>
              ) : profile.verdict === "SUSPICIOUS_ANOMALY" ? (
                <span className="text-xs font-semibold text-rose-400">Anomaly Detected</span>
              ) : (
                <span className="text-xs font-semibold text-slate-500">Gathering Data...</span>
              )}
            </div>
            <p className="text-[10px] text-slate-500">Anomaly Index: {profile.anomalyScore}%</p>
          </div>
        </div>
      </div>
    </div>
  );
}
