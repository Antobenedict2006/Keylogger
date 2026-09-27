"use client";

import React, { useState, useRef } from "react";
import { UploadCloud, FileText, CheckCircle2, AlertCircle, Loader2, Sparkles, RefreshCw } from "lucide-react";
import { ScanSummary } from "@/lib/types";

interface FileUploaderProps {
  onScanComplete: (summary: ScanSummary) => void;
}

export function FileUploader({ onScanComplete }: FileUploaderProps) {
  const [uploadState, setUploadState] = useState<
    "idle" | "uploading" | "analyzing" | "complete" | "error"
  >("idle");
  const [progress, setProgress] = useState(0);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [fileName, setFileName] = useState<string | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileProcess = async (file: File) => {
    try {
      setFileName(file.name);
      setUploadState("uploading");
      setProgress(25);
      setErrorMessage(null);

      const formData = new FormData();
      formData.append("file", file);

      // Simulate network upload progression
      setTimeout(() => setProgress(50), 200);

      const response = await fetch("/api/analyze", {
        method: "POST",
        body: formData,
      });

      setProgress(75);
      setUploadState("analyzing");

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.error || `HTTP ${response.status}: Failed to analyze snapshot`);
      }

      setProgress(100);
      setUploadState("complete");
      onScanComplete(data.summary);
    } catch (err: unknown) {
      setUploadState("error");
      const msg = err instanceof Error ? err.message : "An unexpected error occurred during scan.";
      setErrorMessage(msg);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleFileProcess(e.dataTransfer.files[0]);
    }
  };

  const handleSampleLoad = (type: "malicious" | "clean") => {
    let sampleCsv = "";
    if (type === "malicious") {
      sampleCsv = `Process Name,PID,CPU %,Memory (MB),Has Window,Signed,Path
svchost.exe,1044,0.1,18.4,No,Yes,C:\\Windows\\System32\\svchost.exe
explorer.exe,2930,0.8,112.5,Yes,Yes,C:\\Windows\\explorer.exe
Discord.exe,4812,1.2,165.2,Yes,Yes,C:\\Users\\User\\AppData\\Local\\Discord\\app.exe
winhook_spy.exe,8824,4.8,12.4,No,No,C:\\Users\\User\\AppData\\Local\\Temp\\winhook_spy.exe
autohotkey.exe,3112,0.2,8.1,No,Yes,C:\\Program Files\\AutoHotkey\\AutoHotkey.exe
stealth_keylogger.exe,9941,6.5,15.2,No,No,C:\\Users\\User\\AppData\\Local\\Temp\\stealth_keylogger.exe
chrome.exe,5520,2.1,340.8,Yes,Yes,C:\\Program Files\\Google\\Chrome\\chrome.exe
`;
    } else {
      sampleCsv = `Process Name,PID,CPU %,Memory (MB),Has Window,Signed,Path
svchost.exe,1044,0.1,18.4,No,Yes,C:\\Windows\\System32\\svchost.exe
explorer.exe,2930,0.8,112.5,Yes,Yes,C:\\Windows\\explorer.exe
chrome.exe,5520,2.1,340.8,Yes,Yes,C:\\Program Files\\Google\\Chrome\\chrome.exe
code.exe,6120,1.5,245.0,Yes,Yes,C:\\Users\\User\\AppData\\Local\\Programs\\Microsoft VS Code\\Code.exe
spotify.exe,7410,0.5,95.0,Yes,Yes,C:\\Users\\User\\AppData\\Roaming\\Spotify\\Spotify.exe
`;
    }

    const blob = new Blob([sampleCsv], { type: "text/csv" });
    const file = new File([blob], `${type}_process_snapshot.csv`, { type: "text/csv" });
    handleFileProcess(file);
  };

  const handleReset = () => {
    setUploadState("idle");
    setProgress(0);
    setErrorMessage(null);
    setFileName(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className="w-full rounded-2xl border border-slate-800 bg-slate-900/60 p-6 backdrop-blur-md transition-all hover:border-slate-700/80">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="text-base font-semibold text-white">Upload Process Snapshot</h2>
          <p className="text-xs text-slate-400">
            Supports CSV exports from Task Manager, Process Explorer, or KeyGuard Desktop CLI.
          </p>
        </div>
        
        <div className="flex items-center gap-2">
          <button
            onClick={() => handleSampleLoad("malicious")}
            className="flex items-center gap-1.5 rounded-lg border border-rose-500/30 bg-rose-500/10 px-2.5 py-1 text-xs font-medium text-rose-300 transition-colors hover:bg-rose-500/20"
          >
            <Sparkles className="h-3.5 w-3.5" />
            Test Threat Sample
          </button>
          <button
            onClick={() => handleSampleLoad("clean")}
            className="flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800/80 px-2.5 py-1 text-xs font-medium text-slate-300 transition-colors hover:bg-slate-700 hover:text-white"
          >
            Test Clean Sample
          </button>
        </div>
      </div>

      {/* Upload Zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragOver(true);
        }}
        onDragLeave={() => setIsDragOver(false)}
        onDrop={handleDrop}
        onClick={() => fileInputRef.current?.click()}
        className={`relative flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-8 transition-all ${
          isDragOver
            ? "border-indigo-500 bg-indigo-500/10"
            : "border-slate-800 bg-slate-950/40 hover:border-slate-700 hover:bg-slate-900/40"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".csv,.txt"
          className="hidden"
          onChange={(e) => {
            if (e.target.files && e.target.files.length > 0) {
              handleFileProcess(e.target.files[0]);
            }
          }}
        />

        {uploadState === "idle" && (
          <div className="text-center">
            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-500/10 text-indigo-400">
              <UploadCloud className="h-6 w-6" />
            </div>
            <p className="text-sm font-medium text-slate-200">
              Click to browse or drag and drop process snapshot CSV
            </p>
            <p className="mt-1 text-xs text-slate-500">Max file size: 10MB (CSV, TXT)</p>
          </div>
        )}

        {uploadState === "uploading" && (
          <div className="w-full max-w-xs text-center">
            <Loader2 className="mx-auto mb-3 h-8 w-8 animate-spin text-indigo-400" />
            <p className="text-sm font-medium text-slate-200">Uploading {fileName}...</p>
            <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-800">
              <div
                className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {uploadState === "analyzing" && (
          <div className="w-full max-w-xs text-center">
            <div className="relative mx-auto mb-3 flex h-10 w-10 items-center justify-center">
              <div className="absolute inset-0 animate-ping rounded-full bg-purple-500/20" />
              <Loader2 className="h-8 w-8 animate-spin text-purple-400" />
            </div>
            <p className="text-sm font-semibold text-purple-300">
              Evaluating 24 Features & ML Ensemble...
            </p>
            <p className="mt-1 text-xs text-slate-400">StandardScaler + 300 Decision Trees</p>
          </div>
        )}

        {uploadState === "complete" && (
          <div className="text-center">
            <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-emerald-500/10 text-emerald-400">
              <CheckCircle2 className="h-6 w-6" />
            </div>
            <p className="text-sm font-semibold text-emerald-400">Analysis Complete!</p>
            <p className="mt-0.5 text-xs text-slate-400">File: {fileName}</p>
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleReset();
              }}
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-1 text-xs text-slate-300 hover:bg-slate-700 hover:text-white"
            >
              <RefreshCw className="h-3 w-3" />
              Scan Another File
            </button>
          </div>
        )}

        {uploadState === "error" && (
          <div className="text-center">
            <div className="mx-auto mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-rose-500/10 text-rose-400">
              <AlertCircle className="h-6 w-6" />
            </div>
            <p className="text-sm font-semibold text-rose-400">Scan Failed</p>
            <p className="mt-1 max-w-md text-xs text-rose-300/80">{errorMessage}</p>
            <button
              onClick={(e) => {
                e.stopPropagation();
                handleReset();
              }}
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-rose-500/40 bg-rose-500/20 px-3 py-1 text-xs font-medium text-rose-200 hover:bg-rose-500/30"
            >
              Try Again
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
