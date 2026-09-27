"use client";

import React, { useState } from "react";
import { Navbar } from "@/components/Navbar";
import { FileUploader } from "@/components/upload/FileUploader";
import { MetricsCards } from "@/components/dashboard/MetricsCards";
import { ProcessTable } from "@/components/dashboard/ProcessTable";
import { BiometricTrackerCard } from "@/components/behavioral/BiometricTrackerCard";
import { LiveScanPanel } from "@/components/live/LiveScanPanel";
import { DesktopConsole } from "@/components/dashboard/DesktopConsole";
import { ScanSummary } from "@/lib/types";
import { ShieldCheck, Cpu, Layers, Sparkles, Radio, Upload } from "lucide-react";

type ViewMode = "upload" | "live";

export default function DashboardPage() {
  const [scanSummary, setScanSummary] = useState<ScanSummary | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>("upload");

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 selection:bg-indigo-500 selection:text-white">
      <Navbar />

      <main className="mx-auto max-w-7xl space-y-8 px-4 py-8 sm:px-6 lg:px-8">
        {/* Hero & Overview */}
        <div className="flex flex-col justify-between gap-4 border-b border-slate-800/80 pb-6 md:flex-row md:items-center">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-indigo-500/30 bg-indigo-500/10 px-3 py-1 text-xs font-semibold text-indigo-400">
              <Sparkles className="h-3.5 w-3.5" /> Next-Gen Threat Intelligence
            </div>
            <h1 className="mt-2 text-2xl font-extrabold tracking-tight text-white sm:text-3xl">
              AI Keylogger & Surveillance Detection
            </h1>
            <p className="mt-1 text-xs text-slate-400 sm:text-sm">
              Serverless machine learning inference engine and multi-modal behavioral dynamics on Vercel.
            </p>
          </div>

          <div className="flex items-center gap-3">
            {/* Mode Toggle */}
            <div className="flex items-center gap-1 rounded-xl border border-slate-800 bg-slate-900/60 p-1">
              <button
                onClick={() => setViewMode("upload")}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-all ${
                  viewMode === "upload"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Upload className="h-3.5 w-3.5" />
                Upload CSV
              </button>
              <button
                onClick={() => setViewMode("live")}
                className={`flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-medium transition-all ${
                  viewMode === "live"
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Radio className="h-3.5 w-3.5" />
                Live Mode
              </button>
            </div>

            <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-3 text-right">
              <p className="text-[11px] text-slate-400">Inference Runtime</p>
              <p className="text-xs font-bold text-emerald-400">&lt; 35ms (Serverless Edge)</p>
            </div>
          </div>
        </div>

        <DesktopConsole />

        {/* 1. KPIs & Metrics (only in upload mode) */}
        {viewMode === "upload" && <MetricsCards summary={scanSummary} />}

        {/* 2. Conditional View: CSV Upload OR Live Scan */}
        {viewMode === "upload" ? (
          <>
            {/* File Upload & Snapshot Analysis */}
            <div className="grid grid-cols-1 gap-8 lg:grid-cols-3">
              <div className="lg:col-span-2">
                <FileUploader onScanComplete={(summary) => setScanSummary(summary)} />
              </div>

              {/* Quick Technical Specs Card */}
              <div className="rounded-2xl border border-slate-800 bg-slate-900/40 p-6 backdrop-blur-md">
                <h3 className="text-sm font-bold text-white">Detection Stack Details</h3>
                <ul className="mt-4 space-y-3 text-xs text-slate-400">
                  <li className="flex items-start gap-2.5">
                    <div className="mt-0.5 rounded bg-indigo-500/10 p-1 text-indigo-400">
                      <Cpu className="h-3.5 w-3.5" />
                    </div>
                    <div>
                      <span className="font-semibold text-slate-200">Gradient Boosting ML:</span>
                      <p className="text-[11px] text-slate-400">300 Decision Trees with StandardScaler normalization.</p>
                    </div>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <div className="mt-0.5 rounded bg-purple-500/10 p-1 text-purple-400">
                      <Layers className="h-3.5 w-3.5" />
                    </div>
                    <div>
                      <span className="font-semibold text-slate-200">24 Multi-Signal Features:</span>
                      <p className="text-[11px] text-slate-400">Hook APIs, stealth windows, write rates, whitelisted tool checks.</p>
                    </div>
                  </li>
                  <li className="flex items-start gap-2.5">
                    <div className="mt-0.5 rounded bg-emerald-500/10 p-1 text-emerald-400">
                      <ShieldCheck className="h-3.5 w-3.5" />
                    </div>
                    <div>
                      <span className="font-semibold text-slate-200">Zero-Install Web Architecture:</span>
                      <p className="text-[11px] text-slate-400">Pure web snapshot evaluation without local driver requirements.</p>
                    </div>
                  </li>
                </ul>
              </div>
            </div>

            {/* Process Inspection Results (upload mode only) */}
            {scanSummary && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-lg font-bold text-white">
                    Detailed Process Inspection ({scanSummary.results.length} Scanned)
                  </h2>
                  <span className="text-xs text-slate-400">
                    Scan ID: <span className="font-mono text-slate-300">{scanSummary.id}</span>
                  </span>
                </div>

                <ProcessTable results={scanSummary.results} />
              </div>
            )}
          </>
        ) : (
          <>
            {/* Live Scan Panel */}
            <LiveScanPanel />
          </>
        )}

        {/* 3. Real-time Behavioral Biometrics Playfield */}
        <BiometricTrackerCard />
      </main>

      {/* Footer */}
      <footer className="mt-16 border-t border-slate-900 bg-slate-950/60 py-6 text-center text-xs text-slate-600">
        <p>KeyGuard AI SaaS Engine • Next.js 14 App Router & Scikit-Learn Model Pipeline</p>
      </footer>
    </div>
  );
}
