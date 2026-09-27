/**
 * /api/live  —  Next.js server-side proxy to the Python Flask bridge
 *
 * The Python app runs a Flask server on http://127.0.0.1:8765.
 * Browser clients cannot call it directly because of mixed-content /
 * CORS restrictions in production, so every request is forwarded here
 * server-side and the response is returned as-is.
 *
 * GET  /api/live          → proxies GET http://127.0.0.1:8765/api/scan
 * GET  /api/live/health   → proxies GET http://127.0.0.1:8765/api/health
 *
 * If the Python process is not running the route returns a JSON error
 * with status 503 so the frontend can show a "not connected" state
 * instead of a generic network error.
 */

import { NextRequest, NextResponse } from "next/server";

const PYTHON_BASE = "http://127.0.0.1:8765";
/** Timeout in ms — one scan cycle is 5 s, so 6 s is a safe limit */
const FETCH_TIMEOUT_MS = 6_000;

async function proxyGet(path: string) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), FETCH_TIMEOUT_MS);

  try {
    const res = await fetch(`${PYTHON_BASE}${path}`, {
      method: "GET",
      signal: controller.signal,
      // Tell Next.js not to cache — we always want the latest scan
      cache: "no-store",
    });
    clearTimeout(timer);

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (err: unknown) {
    clearTimeout(timer);

    // AbortError means the Python server didn't respond in time
    const isTimeout =
      err instanceof Error && err.name === "AbortError";

    const isConnRefused =
      err instanceof TypeError &&
      (err.message.includes("ECONNREFUSED") ||
        err.message.includes("fetch failed") ||
        err.message.includes("Failed to fetch"));

    if (isTimeout || isConnRefused) {
      return NextResponse.json(
        {
          success: false,
          error: "Python detector not running. Start main.py first.",
          connected: false,
        },
        { status: 503 }
      );
    }

    return NextResponse.json(
      { success: false, error: "Proxy error: " + String(err) },
      { status: 500 }
    );
  }
}

/** GET /api/live  →  full scan with summary + results array */
export async function GET(_req: NextRequest) {
  return proxyGet("/api/scan");
}
