import { BiometricProfile } from "../types";

export interface KeyRecord {
  key: string;
  downTime: number;
  upTime?: number;
}

export interface MouseRecord {
  x: number;
  y: number;
  time: number;
}

export class BrowserBiometricsCollector {
  private keyRecords: KeyRecord[] = [];
  private activeKeys = new Map<string, number>();
  private mouseRecords: MouseRecord[] = [];
  private lastMouseMoveTime = 0;

  public onKeyDown(e: KeyboardEvent) {
    if (this.activeKeys.has(e.code)) return; // Ignore autorepeat
    const now = performance.now();
    this.activeKeys.set(e.code, now);
    this.keyRecords.push({
      key: e.code,
      downTime: now,
    });
    if (this.keyRecords.length > 300) this.keyRecords.shift();
  }

  public onKeyUp(e: KeyboardEvent) {
    const downTime = this.activeKeys.get(e.code);
    if (downTime === undefined) return;
    this.activeKeys.delete(e.code);
    const now = performance.now();
    
    // Match recent record
    for (let i = this.keyRecords.length - 1; i >= 0; i--) {
      if (this.keyRecords[i].key === e.code && !this.keyRecords[i].upTime) {
        this.keyRecords[i].upTime = now;
        break;
      }
    }
  }

  public onMouseMove(e: MouseEvent) {
    const now = performance.now();
    if (now - this.lastMouseMoveTime < 25) return; // 40Hz sample throttle to prevent CPU strain
    this.lastMouseMoveTime = now;

    this.mouseRecords.push({
      x: e.clientX,
      y: e.clientY,
      time: now,
    });

    if (this.mouseRecords.length > 200) this.mouseRecords.shift();
  }

  public getProfile(): BiometricProfile {
    // 1. Calculate Keystroke Dwell and Flight times
    const dwells: number[] = [];
    const flights: number[] = [];

    for (let i = 0; i < this.keyRecords.length; i++) {
      const rec = this.keyRecords[i];
      if (rec.upTime && rec.upTime > rec.downTime) {
        const dwell = rec.upTime - rec.downTime;
        if (dwell < 1000) dwells.push(dwell);
      }
      if (i > 0) {
        const prev = this.keyRecords[i - 1];
        const flight = rec.downTime - (prev.upTime || prev.downTime);
        if (flight > 0 && flight < 2000) flights.push(flight);
      }
    }

    const dwellMean = dwells.length > 0 ? dwells.reduce((a, b) => a + b, 0) / dwells.length : 85.0;
    const flightMean = flights.length > 0 ? flights.reduce((a, b) => a + b, 0) / flights.length : 120.0;
    const typingSpeedWPM = flightMean > 0 ? Math.min(160, Math.max(10, Math.round(60000 / (dwellMean + flightMean) / 5))) : 45;

    // 2. Calculate Mouse Kinematics
    const speeds: number[] = [];
    const accelerations: number[] = [];
    let straightDist = 0;
    let trajectoryDist = 0;

    if (this.mouseRecords.length > 3) {
      const first = this.mouseRecords[0];
      const last = this.mouseRecords[this.mouseRecords.length - 1];
      straightDist = Math.hypot(last.x - first.x, last.y - first.y);

      for (let i = 1; i < this.mouseRecords.length; i++) {
        const p1 = this.mouseRecords[i - 1];
        const p2 = this.mouseRecords[i];
        const dt = (p2.time - p1.time) / 1000;
        if (dt <= 0) continue;

        const dist = Math.hypot(p2.x - p1.x, p2.y - p1.y);
        trajectoryDist += dist;
        const speed = dist / dt;
        speeds.push(speed);

        if (i > 1 && speeds.length >= 2) {
          const prevSpeed = speeds[speeds.length - 2];
          const accel = Math.abs(speed - prevSpeed) / dt;
          accelerations.push(accel);
        }
      }
    }

    const mouseSpeedMean = speeds.length > 0 ? speeds.reduce((a, b) => a + b, 0) / speeds.length : 350;
    const mouseAccelerationMean = accelerations.length > 0 ? accelerations.reduce((a, b) => a + b, 0) / accelerations.length : 1200;
    const mouseStraightness = trajectoryDist > 0 ? Math.min(1.0, straightDist / trajectoryDist) : 0.85;

    // 3. Compute Anomaly & Confidence
    const sampleCount = dwells.length + speeds.length;
    let confidence = Math.min(100, Math.round((sampleCount / 60) * 100));
    
    // Baseline checks: unnatural typing (>180 WPM or < 20ms dwell) or unnatural mouse movements
    let anomalyScore = 0;
    if (dwellMean < 25) anomalyScore += 40; // Bot-like instant keystrokes
    if (mouseStraightness > 0.98 && speeds.length > 10) anomalyScore += 30; // Synthetic straight lines
    if (typingSpeedWPM > 140) anomalyScore += 20;

    let verdict: "GENUINE_USER" | "SUSPICIOUS_ANOMALY" | "INSUFFICIENT_DATA" = "GENUINE_USER";
    if (confidence < 25) {
      verdict = "INSUFFICIENT_DATA";
    } else if (anomalyScore >= 40) {
      verdict = "SUSPICIOUS_ANOMALY";
    }

    return {
      keystrokeDwellMean: Math.round(dwellMean * 10) / 10,
      keystrokeFlightMean: Math.round(flightMean * 10) / 10,
      typingSpeedWPM,
      mouseSpeedMean: Math.round(mouseSpeedMean),
      mouseAccelerationMean: Math.round(mouseAccelerationMean),
      mouseStraightness: Math.round(mouseStraightness * 100) / 100,
      anomalyScore: Math.min(100, anomalyScore),
      confidence,
      verdict,
    };
  }

  public reset() {
    this.keyRecords = [];
    this.mouseRecords = [];
    this.activeKeys.clear();
  }
}
