import { RawProcessRow } from "../types";

// Legitimate utility / peripheral software whitelist
const KNOWN_SAFE_HOOKS = new Set([
  "autohotkey.exe",
  "razer synapse.exe",
  "razer synapse service.exe",
  "logioptionsplus.exe",
  "logitech options.exe",
  "icue.exe",
  "corsair.service.exe",
  "powertoys.exe",
  "powertoys.keyboardmanagerengine.exe",
  "discord.exe",
  "steam.exe",
  "geforceexperience.exe",
]);

// Suspicious hook/keylogger keywords
const HOOK_SIGNATURES = [
  "hook", "keylog", "intercept", "spy", "capture", "sniff", "record", "stealer", "inject"
];

// System / Windows core process identifiers
const SYSTEM_PROCESS_NAMES = new Set([
  "system", "smss.exe", "csrss.exe", "wininit.exe", "services.exe",
  "lsass.exe", "svchost.exe", "explorer.exe", "dwm.exe", "spoolsv.exe"
]);

export interface ExtractedFeatures {
  vector: number[];
  reasons: string[];
  isWhitelisted: boolean;
}

export function detectHookSuspicion(name: string, path?: string, isSigned?: boolean): { score: number; reasons: string[] } {
  const lowerName = name.toLowerCase();
  const lowerPath = (path || "").toLowerCase();
  const reasons: string[] = [];

  // Whitelist check
  if (KNOWN_SAFE_HOOKS.has(lowerName)) {
    return { score: 0, reasons: ["Known verified utility / gaming hardware software (Whitelisted)"] };
  }

  let score = 0;

  for (const sig of HOOK_SIGNATURES) {
    if (lowerName.includes(sig)) {
      score += 0.35;
      reasons.push(`Process name matches surveillance keyword '${sig}'`);
      break;
    }
  }

  if (lowerPath.includes("\\temp\\") || lowerPath.includes("\\tmp\\")) {
    score += 0.25;
    reasons.push("Executing from temporary directory (\\temp\\)");
  }

  if (lowerPath.includes("\\appdata\\local\\temp\\")) {
    score += 0.25;
    reasons.push("Executing from AppData\\Local\\Temp");
  }

  if (isSigned === false) {
    score += 0.2;
    reasons.push("Unsigned / Unverified binary signature");
  }

  return { score: Math.min(score, 1.0), reasons };
}

/**
 * Extracts 24 features aligned exactly with the Scikit-Learn trained Pipeline:
 * [0]  hook_api_present
 * [1]  has_ll_keyboard_hook
 * [2]  hook_related_dll_count
 * [3]  has_visible_window
 * [4]  window_count
 * [5]  cpu_mean
 * [6]  cpu_max
 * [7]  mem_rss_mb_mean
 * [8]  file_write_bytes_sum
 * [9]  file_write_rate
 * [10] open_file_count_mean
 * [11] net_connections_mean
 * [12] net_bytes_sent_sum
 * [13] is_signed
 * [14] is_system_process
 * [15] has_startup_entry
 * [16] no_exe_path
 * [17] cmdline_empty
 * [18] name_length
 * [19] running_from_temp
 * [20] running_from_appdata
 * [21] age_seconds
 * [22] hook_no_window
 * [23] hook_with_network
 */
export function extractProcessFeatures(row: RawProcessRow): ExtractedFeatures {
  const lowerName = row.name.toLowerCase();
  const lowerPath = (row.exePath || "").toLowerCase();
  const isWhitelisted = KNOWN_SAFE_HOOKS.has(lowerName);

  const { score: hookSuspicionScore, reasons } = detectHookSuspicion(row.name, row.exePath, row.isSigned);

  const hook_api_present = isWhitelisted ? 0 : (row.hookApiPresent ? 1 : (hookSuspicionScore >= 0.3 ? 1 : 0));
  const has_ll_keyboard_hook = isWhitelisted ? 0 : (row.hasLLKeyboardHook ? 1 : (hookSuspicionScore >= 0.6 ? 1 : 0));
  const hook_related_dll_count = row.hookDllCount ?? (hook_api_present ? 2 : 0);
  
  const has_visible_window = row.hasWindow ? 1 : 0;
  const window_count = row.hasWindow ? 1 : 0;
  
  const cpu_mean = row.cpu ?? 0.0;
  const cpu_max = row.cpu ? row.cpu * 1.5 : 0.0;
  const mem_rss_mb_mean = row.memoryMb ?? 0.0;
  
  const file_write_bytes_sum = row.bytesWritten ?? 0.0;
  const file_write_rate = row.writeRate ?? 0.0;
  const open_file_count_mean = row.openFiles ?? 5.0;
  
  const net_connections_mean = row.netConnections ?? 0.0;
  const net_bytes_sent_sum = row.bytesSent ?? 0.0;
  
  const is_signed = row.isSigned ? 1 : (isWhitelisted ? 1 : 0);
  const is_system_process = SYSTEM_PROCESS_NAMES.has(lowerName) ? 1 : 0;
  const has_startup_entry = 0; // Default snapshot heuristic
  const no_exe_path = row.exePath ? 0 : 1;
  const cmdline_empty = (row.cmdline && row.cmdline.length > 0) ? 0 : 1;
  const name_length = row.name.length;
  
  const running_from_temp = (lowerPath.includes("\\temp\\") || lowerPath.includes("/temp/")) ? 1 : 0;
  const running_from_appdata = (lowerPath.includes("\\appdata\\") || lowerPath.includes("/appdata/")) ? 1 : 0;
  const age_seconds = row.ageSeconds ?? 3600;
  
  // Interaction features
  const hook_no_window = (hook_api_present === 1 && has_visible_window === 0) ? 1 : 0;
  const hook_with_network = (hook_api_present === 1 && (net_connections_mean > 0 || net_bytes_sent_sum > 0)) ? 1 : 0;

  if (hook_no_window === 1 && !isWhitelisted) {
    reasons.push("Stealth Hooking: Active input hook running without any visible window interface");
  }
  if (hook_with_network === 1 && !isWhitelisted) {
    reasons.push("Exfiltration Risk: Hook activity combined with active network outbound connections");
  }

  const vector = [
    hook_api_present,
    has_ll_keyboard_hook,
    hook_related_dll_count,
    has_visible_window,
    window_count,
    cpu_mean,
    cpu_max,
    mem_rss_mb_mean,
    file_write_bytes_sum,
    file_write_rate,
    open_file_count_mean,
    net_connections_mean,
    net_bytes_sent_sum,
    is_signed,
    is_system_process,
    has_startup_entry,
    no_exe_path,
    cmdline_empty,
    name_length,
    running_from_temp,
    running_from_appdata,
    age_seconds,
    hook_no_window,
    hook_with_network,
  ];

  return { vector, reasons, isWhitelisted };
}
