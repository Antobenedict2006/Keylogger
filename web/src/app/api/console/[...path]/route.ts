import { NextRequest, NextResponse } from "next/server";

const PYTHON_BASE = "http://127.0.0.1:8765";
const ALLOWED_PATHS = new Set([
  "alerts",
  "history",
  "statistics",
  "behavior",
  "train",
  "train/status",
  "recording/start",
  "actions",
  "history/export",
  "settings/notifications",
  "behavior/settings",
  "behavior/action",
  "behavior/export/keyboard",
  "behavior/export/mouse",
  "behavior/export/combined",
  "behavior/export/session-hour",
  "behavior/export/session-day",
  "behavior/export/comparison",
]);

type RouteContext = { params: Promise<{ path: string[] }> };

async function proxy(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  const endpoint = path.join("/");
  if (!ALLOWED_PATHS.has(endpoint)) {
    return NextResponse.json({ success: false, error: "Unknown console endpoint." }, { status: 404 });
  }

  const target = new URL(`/api/${endpoint}`, PYTHON_BASE);
  request.nextUrl.searchParams.forEach((value, key) => target.searchParams.set(key, value));

  try {
    const response = await fetch(target, {
      method: request.method,
      headers: request.method === "POST" ? { "Content-Type": "application/json" } : undefined,
      body: request.method === "POST" ? await request.text() : undefined,
      cache: "no-store",
      signal: AbortSignal.timeout(10_000),
    });
    const body = await response.arrayBuffer();
    const headers = new Headers();
    const contentType = response.headers.get("content-type");
    const contentDisposition = response.headers.get("content-disposition");
    if (contentType) headers.set("content-type", contentType);
    if (contentDisposition) headers.set("content-disposition", contentDisposition);
    return new NextResponse(body, { status: response.status, headers });
  } catch {
    return NextResponse.json(
      { success: false, error: "Python detector not running. Start main.py first.", connected: false },
      { status: 503 }
    );
  }
}

export async function GET(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}

export async function POST(request: NextRequest, context: RouteContext) {
  return proxy(request, context);
}