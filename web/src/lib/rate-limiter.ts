// In-memory sliding window fallback for local dev / serverless demo
const memoryStore = new Map<string, { count: number; windowStart: number }>();

const WINDOW_MS = 60 * 1000; // 1 minute
const MAX_REQUESTS = 15;      // 15 scans per minute

export interface RateLimitResult {
  success: boolean;
  limit: number;
  remaining: number;
  reset: number;
}

export async function checkRateLimit(identifier: string): Promise<RateLimitResult> {
  const now = Date.now();
  const record = memoryStore.get(identifier);

  if (!record || now - record.windowStart > WINDOW_MS) {
    memoryStore.set(identifier, { count: 1, windowStart: now });
    return {
      success: true,
      limit: MAX_REQUESTS,
      remaining: MAX_REQUESTS - 1,
      reset: now + WINDOW_MS,
    };
  }

  if (record.count >= MAX_REQUESTS) {
    const resetTime = record.windowStart + WINDOW_MS;
    return {
      success: false,
      limit: MAX_REQUESTS,
      remaining: 0,
      reset: resetTime,
    };
  }

  record.count += 1;
  return {
    success: true,
    limit: MAX_REQUESTS,
    remaining: MAX_REQUESTS - record.count,
    reset: record.windowStart + WINDOW_MS,
  };
}
