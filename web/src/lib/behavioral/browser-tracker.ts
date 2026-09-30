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

/**
 * BrowserBiometricsCollector
 * ==========================
 * Passive, zero-blocking keystroke and mouse dynamics tracker.
 *
 * Performance design:
 *  - Incremental stats: dwell / flight / mouse sums are updated on every event
 *    so getProfile() is O(1) — it reads pre-computed accumulators instead of
 *    iterating the full buffer on every 500 ms tick.
 *  - Mouse throttle: 40 Hz (25 ms gate) prevents the mousemove storm from
 *    filling the buffer during fast cursor movements.
 *  - Hidden-tab guard: getProfile() returns the cached last result immediately
 *    when document.hidden is true so the setInterval in the component wastes
 *    no CPU while the tab is not visible.
 *  - No synchronous work in event handlers beyond a push and a running-sum
 *    update — keeps the browser input pipeline completely unblocked.
 */
export class BrowserBiometricsCollector {
  // ── Keystroke buffers ────────────────────────────────────────────────────
  private keyRecords: KeyRecord[] = [];
  private activeKeys = new Map<string, number>();

  // Incremental keystroke accumulators — updated in onKeyUp so getProfile is O(1)
  private dwellSum = 0;
  private dwellCount = 0;
  private flightSum = 0;
  private flightCount = 0;
  private lastUpTime: number | null = null;

  // ── Mouse buffers ────────────────────────────────────────────────────────
  private mouseRecords: MouseRecord[] = [];
  private lastMouseMoveTime = 0;

  // Incremental mouse accumulators — updated in onMouseMove
  private speedSum = 0;
  private speedCount = 0;
  private accelSum = 0;
  private accelCount = 0;
  private prevSpeed = 0;
  private trajectoryDist = 0;
  private firstMouseRecord: MouseRecord | null = null;

  // ── Cache ────────────────────────────────────────────────────────────────
  private cachedProfile: BiometricProfile | null = null;
  private dirty = false;

  // ── Keyboard event handlers ──────────────────────────────────────────────

  public onKeyDown(e: KeyboardEvent) {
    if (this.activeKeys.has(e.code)) return; // Ignore key-repeat
    const now = performance.now();
    this.activeKeys.set(e.code, now);
    this.keyRecords.push({ key: e.code, downTime: now });
    if (this.keyRecords.length > 400) this.keyRecords.shift();
    this.dirty = true;
  }

  public onKeyUp(e: KeyboardEvent) {
    const downTime = this.activeKeys.get(e.code);
    if (downTime === undefined) return;
    this.activeKeys.delete(e.code);
    const now = performance.now();

    // Update dwell accumulator
    const dwell = now - downTime;
    if (dwell > 5 && dwell < 1000) {
      this.dwellSum += dwell;
      this.dwellCount++;
    }

    // Update flight accumulator (time between consecutive key releases)
    if (this.lastUpTime !== null) {
      const flight = downTime - this.lastUpTime;
      if (flight > 0 && flight < 2000) {
        this.flightSum += flight;
        this.flightCount++;
      }
    }
    this.lastUpTime = now;

    // Back-fill upTime in the records array for compatibility
    for (let i = this.keyRecords.length - 1; i >= 0; i--) {
      if (this.keyRecords[i].key === e.code && !this.keyRecords[i].upTime) {
        this.keyRecords[i].upTime = now;
        break;
      }
    }
    this.dirty = true;
  }

  // ── Mouse event handler ──────────────────────────────────────────────────

  public onMouseMove(e: MouseEvent) {
    const now = performance.now();
    // 40 Hz throttle (25 ms gate) — prevents CPU spike during fast sweeps
    if (now - this.lastMouseMoveTime < 25) return;
    this.lastMouseMoveTime = now;

    const rec: MouseRecord = { x: e.clientX, y: e.clientY, time: now };

    if (this.mouseRecords.length > 0) {
      const prev = this.mouseRecords[this.mouseRecords.length - 1];
      const dt = (now - prev.time) / 1000;
      if (dt > 0) {
        const dist = Math.hypot(rec.x - prev.x, rec.y - prev.y);
        const speed = dist / dt;
        this.trajectoryDist += dist;

        this.speedSum += speed;
        this.speedCount++;

        const accel = Math.abs(speed - this.prevSpeed) / dt;
        this.accelSum += accel;
        this.accelCount++;
        this.prevSpeed = speed;
      }
    } else {
      // First point — record as reference for straight-line distance
      this.firstMouseRecord = rec;
    }

    this.mouseRecords.push(rec);
    if (this.mouseRecords.length > 300) {
      // Evict oldest point; update firstMouseRecord to keep straightDist valid
      this.mouseRecords.shift();
      this.firstMouseRecord = this.mouseRecords[0] ?? null;
    }
    this.dirty = true;
  }

  // ── Profile computation (O(1) thanks to accumulators) ───────────────────

  public getProfile(): BiometricProfile {
    // Return cached result immediately if tab is hidden or nothing changed
    if (typeof document !== "undefined" && document.hidden && this.cachedProfile) {
      return this.cachedProfile;
    }
    if (!this.dirty && this.cachedProfile) {
      return this.cachedProfile;
    }

    // ── Keyboard metrics (read pre-computed accumulators) ────────────────
    const dwellMean = this.dwellCount > 0 ? this.dwellSum / this.dwellCount : 85.0;
    const flightMean = this.flightCount > 0 ? this.flightSum / this.flightCount : 120.0;
    const typingSpeedWPM =
      dwellMean + flightMean > 0
        ? Math.min(160, Math.max(10, Math.round(60000 / ((dwellMean + flightMean) * 5))))
        : 45;

    // ── Mouse metrics (read pre-computed accumulators) ───────────────────
    const mouseSpeedMean = this.speedCount > 0 ? this.speedSum / this.speedCount : 350;
    const mouseAccelerationMean = this.accelCount > 0 ? this.accelSum / this.accelCount : 1200;

    let mouseStraightness = 0.85;
    if (this.trajectoryDist > 0 && this.firstMouseRecord && this.mouseRecords.length > 0) {
      const last = this.mouseRecords[this.mouseRecords.length - 1];
      const straight = Math.hypot(
        last.x - this.firstMouseRecord.x,
        last.y - this.firstMouseRecord.y
      );
      mouseStraightness = Math.min(1.0, straight / this.trajectoryDist);
    }

    // ── Confidence & anomaly ──────────────────────────────────────────────
    const sampleCount = this.dwellCount + this.speedCount;
    const confidence = Math.min(100, Math.round((sampleCount / 60) * 100));

    let anomalyScore = 0;
    if (dwellMean < 25) anomalyScore += 40;                              // bot-like instant presses
    if (mouseStraightness > 0.98 && this.speedCount > 10) anomalyScore += 30; // geometric straight lines
    if (typingSpeedWPM > 140) anomalyScore += 20;                        // superhuman speed

    let verdict: BiometricProfile["verdict"] = "GENUINE_USER";
    if (confidence < 25) {
      verdict = "INSUFFICIENT_DATA";
    } else if (anomalyScore >= 40) {
      verdict = "SUSPICIOUS_ANOMALY";
    }

    const profile: BiometricProfile = {
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

    this.cachedProfile = profile;
    this.dirty = false;
    return profile;
  }

  // ── Reset ────────────────────────────────────────────────────────────────

  public reset() {
    this.keyRecords = [];
    this.mouseRecords = [];
    this.activeKeys.clear();
    this.dwellSum = 0;
    this.dwellCount = 0;
    this.flightSum = 0;
    this.flightCount = 0;
    this.lastUpTime = null;
    this.speedSum = 0;
    this.speedCount = 0;
    this.accelSum = 0;
    this.accelCount = 0;
    this.prevSpeed = 0;
    this.trajectoryDist = 0;
    this.firstMouseRecord = null;
    this.cachedProfile = null;
    this.dirty = false;
  }
}
