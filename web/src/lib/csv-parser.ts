import Papa from "papaparse";
import { RawProcessRow } from "./types";

export class CSVParseError extends Error {
  public details?: string[];
  constructor(message: string, details?: string[]) {
    super(message);
    this.name = "CSVParseError";
    this.details = details;
  }
}

// Column aliases for wide compatibility (Windows Task Manager, Process Explorer, Sysinternals)
const HEADER_ALIASES: Record<string, string[]> = {
  name: ["process name", "name", "imagename", "image_name", "caption", "process_name"],
  pid: ["pid", "process id", "processid", "id"],
  cpu: ["cpu %", "cpu", "cpu_percent", "cpu usage", "cpu_usage"],
  memoryMb: ["memory (mb)", "memory", "mem_mb", "working_set_mb", "ws_mb", "memory (kb)", "working set (private)"],
  hasWindow: ["has window", "has_window", "window_title", "visible_window", "main_window_title"],
  isSigned: ["signed", "is_signed", "verified_signer", "signature", "publisher"],
  exePath: ["path", "exe_path", "image_path", "executablepath", "commandline", "executable_path"],
  hookApiPresent: ["hook_api_present", "hook_api", "has_hook"],
  hasLLKeyboardHook: ["has_ll_keyboard_hook", "ll_keyboard_hook", "keyboard_hook"],
};

function normalizeHeader(rawHeader: string): string {
  const cleaned = rawHeader.toLowerCase().trim().replace(/['"]/g, "");
  for (const [canonical, aliases] of Object.entries(HEADER_ALIASES)) {
    if (cleaned === canonical.toLowerCase() || aliases.includes(cleaned)) {
      return canonical;
    }
  }
  return cleaned;
}

export function parseProcessCSV(csvText: string): RawProcessRow[] {
  if (!csvText || !csvText.trim()) {
    throw new CSVParseError("CSV content is empty");
  }

  const result = Papa.parse<Record<string, string>>(csvText, {
    header: true,
    skipEmptyLines: "greedy",
    transformHeader: (header) => normalizeHeader(header),
  });

  if (result.errors.length > 0 && result.data.length === 0) {
    throw new CSVParseError(
      "Failed to parse CSV format",
      result.errors.map((e) => `Line ${e.row ?? "?"}: ${e.message}`)
    );
  }

  const headers = result.meta.fields || [];
  const hasName = headers.includes("name");
  
  if (!hasName) {
    throw new CSVParseError(
      `Missing required process identifier column. Found columns: ${headers.slice(0, 8).join(", ")}...`
    );
  }

  const rows: RawProcessRow[] = [];

  for (const raw of result.data) {
    const name = (raw.name || "").trim();
    if (!name || name.toLowerCase() === "system idle process") continue;

    const pid = parseInt(raw.pid || "0", 10) || undefined;
    const cpu = parseFloat(raw.cpu || "0") || 0;
    let memoryMb = parseFloat(raw.memoryMb || "0") || 0;
    
    // Auto-convert KB to MB if values are large
    if (memoryMb > 10000 && !headers.some(h => h.includes("mb"))) {
      memoryMb = memoryMb / 1024;
    }

    const hasWindowStr = (raw.hasWindow || "").toLowerCase().trim();
    const hasWindow = hasWindowStr === "yes" || hasWindowStr === "true" || hasWindowStr === "1" || (hasWindowStr.length > 0 && hasWindowStr !== "no" && hasWindowStr !== "false" && hasWindowStr !== "0");

    const isSignedStr = (raw.isSigned || "").toLowerCase().trim();
    const isSigned = isSignedStr === "yes" || isSignedStr === "true" || isSignedStr === "1" || isSignedStr.includes("microsoft") || isSignedStr.includes("verified");

    const exePath = raw.exePath?.trim() || undefined;

    rows.push({
      name,
      pid,
      cpu,
      memoryMb: Math.round(memoryMb * 10) / 10,
      hasWindow,
      isSigned,
      exePath,
      hookApiPresent: raw.hookApiPresent === "1" || raw.hookApiPresent === "true",
      hasLLKeyboardHook: raw.hasLLKeyboardHook === "1" || raw.hasLLKeyboardHook === "true",
      hookDllCount: parseInt(raw.hookDllCount || "0", 10) || 0,
      openFiles: parseInt(raw.openFiles || "0", 10) || 0,
      netConnections: parseInt(raw.netConnections || "0", 10) || 0,
      bytesSent: parseFloat(raw.bytesSent || "0") || 0,
      bytesWritten: parseFloat(raw.bytesWritten || "0") || 0,
      writeRate: parseFloat(raw.writeRate || "0") || 0,
      cmdline: raw.cmdline || "",
      ageSeconds: parseFloat(raw.ageSeconds || "0") || 0,
    });
  }

  if (rows.length === 0) {
    throw new CSVParseError("No valid process records were found in the uploaded file.");
  }

  return rows;
}
