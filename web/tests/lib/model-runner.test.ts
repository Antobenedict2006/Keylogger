import { describe, it, expect } from "vitest";
import { predictProcess, analyzeProcesses } from "../../src/lib/ml/model-runner";

describe("ML Model Runner", () => {
  it("should classify standard system process as SAFE with low risk score", () => {
    const res = predictProcess({
      name: "svchost.exe",
      pid: 800,
      cpu: 0.1,
      memoryMb: 20.0,
      hasWindow: false,
      isSigned: true,
      exePath: "C:\\Windows\\System32\\svchost.exe",
    });

    expect(res.classification).toBe("SAFE");
    expect(res.riskScore).toBeLessThan(35);
  });

  it("should flag suspicious keylogger processes with elevated risk score", () => {
    const res = predictProcess({
      name: "spy_hook_stealer.exe",
      pid: 4512,
      cpu: 6.2,
      memoryMb: 12.0,
      hasWindow: false,
      isSigned: false,
      exePath: "C:\\Users\\User\\AppData\\Local\\Temp\\spy_hook_stealer.exe",
      hookApiPresent: true,
      hasLLKeyboardHook: true,
    });

    expect(["SUSPICIOUS", "MALICIOUS"]).toContain(res.classification);
    expect(res.riskScore).toBeGreaterThan(40);
  });

  it("should batch process multiple rows correctly", () => {
    const list = [
      { name: "explorer.exe", pid: 10, hasWindow: true, isSigned: true },
      { name: "chrome.exe", pid: 20, hasWindow: true, isSigned: true },
    ];
    const results = analyzeProcesses(list);
    expect(results).toHaveLength(2);
  });
});
