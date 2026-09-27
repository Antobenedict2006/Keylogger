import { describe, it, expect } from "vitest";
import { extractProcessFeatures, detectHookSuspicion } from "../../src/lib/ml/feature-extractor";

describe("Feature Extractor & Heuristics", () => {
  it("should whitelist known safe peripheral/macro tools like AutoHotkey", () => {
    const { score, reasons } = detectHookSuspicion("autohotkey.exe", "C:\\Program Files\\AutoHotkey\\AutoHotkey.exe", true);
    expect(score).toBe(0);
    expect(reasons[0]).toContain("Whitelisted");

    const feat = extractProcessFeatures({
      name: "autohotkey.exe",
      pid: 100,
      cpu: 0.1,
      memoryMb: 12,
      hasWindow: false,
      isSigned: true,
      exePath: "C:\\Program Files\\AutoHotkey\\AutoHotkey.exe",
    });

    expect(feat.isWhitelisted).toBe(true);
    expect(feat.vector[0]).toBe(0); // hook_api_present suppressed
  });

  it("should flag suspicious keylogger names executing from temp paths", () => {
    const { score, reasons } = detectHookSuspicion("stealth_keylog.exe", "C:\\Users\\User\\AppData\\Local\\Temp\\stealth_keylog.exe", false);
    expect(score).toBeGreaterThan(0.5);
    expect(reasons.some((r) => r.includes("temp"))).toBe(true);
    expect(reasons.some((r) => r.includes("keyword"))).toBe(true);

    const feat = extractProcessFeatures({
      name: "stealth_keylog.exe",
      pid: 999,
      cpu: 5.0,
      memoryMb: 15,
      hasWindow: false,
      isSigned: false,
      exePath: "C:\\Users\\User\\AppData\\Local\\Temp\\stealth_keylog.exe",
    });

    expect(feat.vector[0]).toBe(1); // hook_api_present flagged
    expect(feat.vector[19]).toBe(1); // running_from_temp = 1
    expect(feat.vector[22]).toBe(1); // hook_no_window = 1
  });
});
