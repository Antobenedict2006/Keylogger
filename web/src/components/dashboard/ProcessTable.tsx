"use client";

import React, { useState, useMemo } from "react";
import {
  ProcessAnalysisResult,
} from "@/lib/types";
import {
  Search,
  Filter,
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Info,
  CheckCircle,
  XCircle,
  Cpu,
  HardDrive,
} from "lucide-react";

interface ProcessTableProps {
  results: ProcessAnalysisResult[];
}

export function ProcessTable({ results }: ProcessTableProps) {
  const [searchTerm, setSearchTerm] = useState("");
  const [filterSeverity, setFilterSeverity] = useState<"ALL" | "MALICIOUS" | "SUSPICIOUS" | "SAFE">("ALL");
  const [sortField, setSortField] = useState<"riskScore" | "cpu" | "memoryMb" | "name">("riskScore");
  const [sortAsc, setSortAsc] = useState(false);
  const [expandedPid, setExpandedPid] = useState<number | null>(null);

  const filtered = useMemo(() => {
    return results
      .filter((proc) => {
        const matchesSearch =
          proc.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
          (proc.path && proc.path.toLowerCase().includes(searchTerm.toLowerCase())) ||
          proc.pid.toString().includes(searchTerm);

        const matchesSeverity =
          filterSeverity === "ALL" || proc.classification === filterSeverity;

        return matchesSearch && matchesSeverity;
      })
      .sort((a, b) => {
        let comp = 0;
        if (sortField === "riskScore") comp = a.riskScore - b.riskScore;
        if (sortField === "cpu") comp = a.cpu - b.cpu;
        if (sortField === "memoryMb") comp = a.memoryMb - b.memoryMb;
        if (sortField === "name") comp = a.name.localeCompare(b.name);
        return sortAsc ? comp : -comp;
      });
  }, [results, searchTerm, filterSeverity, sortField, sortAsc]);

  const toggleSort = (field: "riskScore" | "cpu" | "memoryMb" | "name") => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(false);
    }
  };

  const getBadge = (cls: "SAFE" | "SUSPICIOUS" | "MALICIOUS") => {
    if (cls === "MALICIOUS") {
      return (
        <span className="inline-flex items-center gap-1 rounded-md border border-rose-500/30 bg-rose-500/10 px-2 py-0.5 text-xs font-semibold text-rose-400">
          <ShieldAlert className="h-3.5 w-3.5" />
          Malicious
        </span>
      );
    }
    if (cls === "SUSPICIOUS") {
      return (
        <span className="inline-flex items-center gap-1 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-xs font-semibold text-amber-400">
          <AlertTriangle className="h-3.5 w-3.5" />
          Suspicious
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-xs font-semibold text-emerald-400">
        <ShieldCheck className="h-3.5 w-3.5" />
        Safe
      </span>
    );
  };

  return (
    <div className="space-y-4 rounded-2xl border border-slate-800 bg-slate-900/60 p-5 backdrop-blur-md">
      {/* Controls Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-slate-500" />
          <input
            type="text"
            placeholder="Search process name, PID, or path..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full rounded-xl border border-slate-800 bg-slate-950/60 py-2 pl-9 pr-4 text-xs text-slate-200 placeholder-slate-500 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        </div>

        {/* Severity Filter Buttons */}
        <div className="flex flex-wrap items-center gap-1.5 rounded-xl border border-slate-800 bg-slate-950/40 p-1 text-xs">
          {(["ALL", "MALICIOUS", "SUSPICIOUS", "SAFE"] as const).map((sev) => (
            <button
              key={sev}
              onClick={() => setFilterSeverity(sev)}
              className={`rounded-lg px-3 py-1 font-medium transition-all ${
                filterSeverity === sev
                  ? "bg-indigo-600 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {sev === "ALL" ? `All (${results.length})` : sev}
            </button>
          ))}
        </div>
      </div>

      {/* 1. Mobile Card View (< lg screens) */}
      <div className="space-y-3 lg:hidden">
        {filtered.length === 0 ? (
          <p className="py-8 text-center text-xs text-slate-500">No matching processes found.</p>
        ) : (
          filtered.map((proc) => {
            const isExpanded = expandedPid === proc.pid;
            return (
              <div
                key={proc.pid}
                className="rounded-xl border border-slate-800/80 bg-slate-950/60 p-4 transition-all"
              >
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-white">{proc.name}</span>
                      <span className="text-[11px] text-slate-500">PID: {proc.pid}</span>
                    </div>
                    {proc.path && (
                      <p className="mt-0.5 truncate text-[11px] text-slate-500 max-w-[220px]">
                        {proc.path}
                      </p>
                    )}
                  </div>
                  {getBadge(proc.classification)}
                </div>

                <div className="mt-3 flex items-center justify-between border-t border-slate-800/60 pt-3 text-xs text-slate-400">
                  <div className="flex items-center gap-3">
                    <span>CPU: {proc.cpu}%</span>
                    <span>Mem: {proc.memoryMb} MB</span>
                  </div>
                  <div className="flex items-center gap-1.5 font-bold">
                    <span className="text-slate-500">Risk:</span>
                    <span
                      className={
                        proc.riskScore >= 70
                          ? "text-rose-400"
                          : proc.riskScore >= 35
                          ? "text-amber-400"
                          : "text-emerald-400"
                      }
                    >
                      {proc.riskScore}%
                    </span>
                  </div>
                </div>

                {/* Mobile Expand Button */}
                <button
                  onClick={() => setExpandedPid(isExpanded ? null : proc.pid)}
                  className="mt-2 flex w-full items-center justify-center gap-1 text-[11px] text-indigo-400 hover:text-indigo-300"
                >
                  {isExpanded ? (
                    <>
                      Hide Explanations <ChevronUp className="h-3.5 w-3.5" />
                    </>
                  ) : (
                    <>
                      Show Explanations ({proc.reasons.length}) <ChevronDown className="h-3.5 w-3.5" />
                    </>
                  )}
                </button>

                {isExpanded && (
                  <div className="mt-2 space-y-1.5 rounded-lg border border-slate-800 bg-slate-900/90 p-3 text-xs text-slate-300">
                    <p className="font-semibold text-indigo-300">Model Insights & Probabilities:</p>
                    <div className="flex gap-2 text-[11px] text-slate-400">
                      <span>Safe: {Math.round(proc.probabilities.safe * 100)}%</span>
                      <span>Susp: {Math.round(proc.probabilities.suspicious * 100)}%</span>
                      <span>Mal: {Math.round(proc.probabilities.malicious * 100)}%</span>
                    </div>
                    {proc.reasons.length > 0 ? (
                      <ul className="list-inside list-disc space-y-0.5 pt-1 text-[11px] text-rose-300">
                        {proc.reasons.map((r, i) => (
                          <li key={i}>{r}</li>
                        ))}
                      </ul>
                    ) : (
                      <p className="pt-1 text-[11px] text-emerald-400">No anomalous signals detected.</p>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* 2. Desktop Responsive Table (>= lg screens) */}
      <div className="hidden overflow-x-auto lg:block">
        <table className="w-full text-left text-xs text-slate-300">
          <thead className="border-b border-slate-800 bg-slate-950/40 text-[11px] uppercase tracking-wider text-slate-400">
            <tr>
              <th
                onClick={() => toggleSort("name")}
                className="cursor-pointer py-3 pl-4 pr-3 font-semibold hover:text-white"
              >
                Process Name
              </th>
              <th className="px-3 py-3 font-semibold">PID</th>
              <th className="px-3 py-3 font-semibold">Status</th>
              <th
                onClick={() => toggleSort("riskScore")}
                className="cursor-pointer px-3 py-3 font-semibold hover:text-white"
              >
                Risk Score {sortField === "riskScore" && (sortAsc ? "▲" : "▼")}
              </th>
              <th
                onClick={() => toggleSort("cpu")}
                className="cursor-pointer px-3 py-3 font-semibold hover:text-white"
              >
                CPU % {sortField === "cpu" && (sortAsc ? "▲" : "▼")}
              </th>
              <th
                onClick={() => toggleSort("memoryMb")}
                className="cursor-pointer px-3 py-3 font-semibold hover:text-white"
              >
                Memory {sortField === "memoryMb" && (sortAsc ? "▲" : "▼")}
              </th>
              <th className="px-3 py-3 font-semibold">Signed</th>
              <th className="px-3 py-3 font-semibold">Window</th>
              <th className="py-3 pl-3 pr-4 text-right font-semibold">Details</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={9} className="py-8 text-center text-slate-500">
                  No matching processes found.
                </td>
              </tr>
            ) : (
              filtered.map((proc) => {
                const isExpanded = expandedPid === proc.pid;
                return (
                  <React.Fragment key={proc.pid}>
                    <tr className="transition-colors hover:bg-slate-800/30">
                      <td className="py-3 pl-4 pr-3 font-medium text-white">
                        <div className="flex flex-col">
                          <span>{proc.name}</span>
                          {proc.path && (
                            <span className="truncate text-[10px] text-slate-500 max-w-xs">
                              {proc.path}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-3 text-slate-400 font-mono">{proc.pid}</td>
                      <td className="px-3 py-3">{getBadge(proc.classification)}</td>
                      <td className="px-3 py-3 font-bold">
                        <div className="flex items-center gap-2">
                          <div className="h-1.5 w-12 rounded-full bg-slate-800 overflow-hidden">
                            <div
                              className={`h-full ${
                                proc.riskScore >= 70
                                  ? "bg-rose-500"
                                  : proc.riskScore >= 35
                                  ? "bg-amber-500"
                                  : "bg-emerald-500"
                              }`}
                              style={{ width: `${Math.max(8, proc.riskScore)}%` }}
                            />
                          </div>
                          <span
                            className={
                              proc.riskScore >= 70
                                ? "text-rose-400"
                                : proc.riskScore >= 35
                                ? "text-amber-400"
                                : "text-emerald-400"
                            }
                          >
                            {proc.riskScore}%
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-3 text-slate-400">{proc.cpu}%</td>
                      <td className="px-3 py-3 text-slate-400">{proc.memoryMb} MB</td>
                      <td className="px-3 py-3">
                        {proc.isSigned ? (
                          <CheckCircle className="h-4 w-4 text-emerald-400" />
                        ) : (
                          <XCircle className="h-4 w-4 text-slate-600" />
                        )}
                      </td>
                      <td className="px-3 py-3">
                        {proc.hasWindow ? (
                          <span className="text-emerald-400 text-[11px]">Yes</span>
                        ) : (
                          <span className="text-slate-500 text-[11px]">Stealth</span>
                        )}
                      </td>
                      <td className="py-3 pl-3 pr-4 text-right">
                        <button
                          onClick={() => setExpandedPid(isExpanded ? null : proc.pid)}
                          className="inline-flex items-center gap-1 rounded-lg border border-slate-700 bg-slate-800 px-2.5 py-1 text-[11px] font-medium text-slate-300 hover:bg-slate-700 hover:text-white"
                        >
                          {isExpanded ? "Close" : "Inspect"}
                        </button>
                      </td>
                    </tr>

                    {/* Detailed Row Dropdown */}
                    {isExpanded && (
                      <tr className="bg-slate-950/80">
                        <td colSpan={9} className="p-4">
                          <div className="rounded-xl border border-slate-800/80 bg-slate-900/60 p-4">
                            <div className="grid grid-cols-3 gap-4 border-b border-slate-800 pb-3 text-xs">
                              <div>
                                <span className="text-slate-400">Class Probabilities:</span>
                                <p className="mt-0.5 font-semibold text-slate-200">
                                  Safe: {Math.round(proc.probabilities.safe * 100)}% | Susp:{" "}
                                  {Math.round(proc.probabilities.suspicious * 100)}% | Mal:{" "}
                                  {Math.round(proc.probabilities.malicious * 100)}%
                                </p>
                              </div>
                              <div>
                                <span className="text-slate-400">Full Image Path:</span>
                                <p className="mt-0.5 font-mono text-[11px] text-slate-300 truncate">
                                  {proc.path || "Not Available (System / Protected)"}
                                </p>
                              </div>
                              <div>
                                <span className="text-slate-400">Threat Verdict:</span>
                                <p className="mt-0.5 font-semibold text-indigo-300">
                                  {proc.classification}
                                </p>
                              </div>
                            </div>

                            <div className="mt-3">
                              <span className="text-xs font-semibold text-slate-300">
                                Identified Heuristic Signals & Triggers:
                              </span>
                              {proc.reasons.length > 0 ? (
                                <ul className="mt-1.5 list-inside list-disc space-y-1 text-xs text-rose-300">
                                  {proc.reasons.map((r, i) => (
                                    <li key={i}>{r}</li>
                                  ))}
                                </ul>
                              ) : (
                                <p className="mt-1 text-xs text-emerald-400">
                                  No suspicious indicators found. Verified clean execution profile.
                                </p>
                              )}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
