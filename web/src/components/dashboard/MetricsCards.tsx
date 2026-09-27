"use client";

import React from "react";
import { ShieldCheck, ShieldAlert, AlertTriangle, Activity, Zap } from "lucide-react";
import { ScanSummary } from "@/lib/types";

interface MetricsCardsProps {
  summary: ScanSummary | null;
}

export function MetricsCards({ summary }: MetricsCardsProps) {
  if (!summary) {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {[
          { label: "Total Processes", icon: Activity, val: "0" },
          { label: "Threats (Keyloggers)", icon: ShieldAlert, val: "0" },
          { label: "Suspicious", icon: AlertTriangle, val: "0" },
          { label: "Safe / Benign", icon: ShieldCheck, val: "0" },
        ].map((card, idx) => (
          <div
            key={idx}
            className="rounded-xl border border-slate-800/80 bg-slate-900/40 p-4 backdrop-blur-sm"
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-400">{card.label}</span>
              <card.icon className="h-4 w-4 text-slate-600" />
            </div>
            <p className="mt-2 text-2xl font-bold text-slate-500">--</p>
          </div>
        ))}
      </div>
    );
  }

  const cards = [
    {
      label: "Total Processes",
      value: summary.totalProcesses,
      sub: "Scanned in snapshot",
      icon: Activity,
      color: "text-slate-200",
      border: "border-slate-800",
      bg: "bg-slate-900/60",
    },
    {
      label: "Malicious Keyloggers",
      value: summary.threatsDetected,
      sub: summary.threatsDetected > 0 ? "Immediate attention required" : "Zero high-risk threats",
      icon: ShieldAlert,
      color: summary.threatsDetected > 0 ? "text-rose-400" : "text-slate-200",
      border: summary.threatsDetected > 0 ? "border-rose-500/40 shadow-lg shadow-rose-500/10" : "border-slate-800",
      bg: summary.threatsDetected > 0 ? "bg-rose-950/20" : "bg-slate-900/60",
    },
    {
      label: "Suspicious Activity",
      value: summary.suspiciousDetected,
      sub: "Requires verification",
      icon: AlertTriangle,
      color: summary.suspiciousDetected > 0 ? "text-amber-400" : "text-slate-200",
      border: summary.suspiciousDetected > 0 ? "border-amber-500/40" : "border-slate-800",
      bg: summary.suspiciousDetected > 0 ? "bg-amber-950/20" : "bg-slate-900/60",
    },
    {
      label: "Safe Processes",
      value: summary.safeCount,
      sub: `${Math.round((summary.safeCount / summary.totalProcesses) * 100)}% of snapshot`,
      icon: ShieldCheck,
      color: "text-emerald-400",
      border: "border-slate-800",
      bg: "bg-slate-900/60",
    },
  ];

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        {cards.map((card, idx) => (
          <div
            key={idx}
            className={`rounded-xl border p-4 backdrop-blur-md transition-all ${card.border} ${card.bg}`}
          >
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-400">{card.label}</span>
              <card.icon className={`h-4 w-4 ${card.color}`} />
            </div>
            <p className={`mt-2 text-3xl font-extrabold tracking-tight ${card.color}`}>
              {card.value}
            </p>
            <p className="mt-1 text-[11px] text-slate-500">{card.sub}</p>
          </div>
        ))}
      </div>

      {/* Risk Assessment Banner */}
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-950/60 px-5 py-3.5">
        <div className="flex items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-500/10 text-indigo-400">
            <Zap className="h-4 w-4" />
          </div>
          <div>
            <p className="text-xs font-semibold text-slate-200">
              Risk Distribution Index: <span className="text-indigo-400">Avg {summary.averageRiskScore}%</span> (Peak {summary.maxRiskScore}%)
            </p>
            <p className="text-[11px] text-slate-500">
              Evaluated across 24 multi-signal OS heuristic features and 300 Gradient Boosting estimators.
            </p>
          </div>
        </div>

        {/* Mini progress bar */}
        <div className="w-full sm:w-48">
          <div className="h-2 w-full overflow-hidden rounded-full bg-slate-800">
            <div
              className={`h-full transition-all duration-500 ${
                summary.threatsDetected > 0
                  ? "bg-gradient-to-r from-amber-500 to-rose-500"
                  : "bg-gradient-to-r from-emerald-500 to-indigo-500"
              }`}
              style={{ width: `${Math.min(100, Math.max(5, summary.maxRiskScore))}%` }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
