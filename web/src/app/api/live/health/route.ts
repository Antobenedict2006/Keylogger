import { NextRequest, NextResponse } from "next/server";

const PYTHON_BASE = "http://127.0.0.1:8765";

export async function GET(_req: NextRequest) {
  try {
    const res = await fetch(`${PYTHON_BASE}/api/health`, {
      cache: "no-store",
      signal: AbortSignal.timeout(3000),
    });
    const data = await res.json();
    return NextResponse.json({ ...data, connected: true });
  } catch {
    return NextResponse.json(
      { connected: false, error: "Python detector not running." },
      { status: 503 }
    );
  }
}
