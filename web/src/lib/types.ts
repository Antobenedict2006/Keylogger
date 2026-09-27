export interface RawProcessRow {
  name: string;
  pid?: number;
  cpu?: number;
  memoryMb?: number;
  hasWindow?: boolean;
  isSigned?: boolean;
  exePath?: string;
  hookApiPresent?: boolean;
  hasLLKeyboardHook?: boolean;
  hookDllCount?: number;
  openFiles?: number;
  netConnections?: number;
  bytesSent?: number;
  bytesWritten?: number;
  writeRate?: number;
  cmdline?: string;
  ageSeconds?: number;
}

export interface ProcessAnalysisResult {
  pid: number;
  name: string;
  riskScore: number; // 0 - 100
  classification: "SAFE" | "SUSPICIOUS" | "MALICIOUS";
  probabilities: {
    safe: number;
    suspicious: number;
    malicious: number;
  };
  features: number[];
  reasons: string[];
  cpu: number;
  memoryMb: number;
  hasWindow: boolean;
  isSigned: boolean;
  path?: string;
}

export interface ScanSummary {
  id: string;
  timestamp: string;
  totalProcesses: number;
  threatsDetected: number;
  suspiciousDetected: number;
  safeCount: number;
  maxRiskScore: number;
  averageRiskScore: number;
  results: ProcessAnalysisResult[];
}

export interface BiometricProfile {
  keystrokeDwellMean: number;
  keystrokeFlightMean: number;
  typingSpeedWPM: number;
  mouseSpeedMean: number;
  mouseAccelerationMean: number;
  mouseStraightness: number;
  anomalyScore: number;
  confidence: number;
  verdict: "GENUINE_USER" | "SUSPICIOUS_ANOMALY" | "INSUFFICIENT_DATA";
}
