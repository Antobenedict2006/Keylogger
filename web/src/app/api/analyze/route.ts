import { NextRequest, NextResponse } from "next/server";
import { parseProcessCSV, CSVParseError } from "@/lib/csv-parser";
import { analyzeProcesses } from "@/lib/ml/model-runner";
import { checkRateLimit } from "@/lib/rate-limiter";
import { ScanSummary } from "@/lib/types";

export async function POST(req: NextRequest) {
  try {
    // 1. Rate Limiting Check (by IP / client header)
    const ip = req.headers.get("x-forwarded-for") || "local-client";
    const rateLimit = await checkRateLimit(ip);
    
    if (!rateLimit.success) {
      return NextResponse.json(
        {
          error: "Rate limit exceeded. Too many scan requests.",
          resetInMs: Math.max(0, rateLimit.reset - Date.now()),
        },
        {
          status: 429,
          headers: {
            "Retry-After": Math.ceil((rateLimit.reset - Date.now()) / 1000).toString(),
            "X-RateLimit-Limit": rateLimit.limit.toString(),
            "X-RateLimit-Remaining": "0",
          },
        }
      );
    }

    // 2. Multi-part form data validation
    const formData = await req.formData();
    const file = formData.get("file");

    if (!file || !(file instanceof File)) {
      return NextResponse.json(
        { error: "No file uploaded. Please provide a valid process snapshot CSV." },
        { status: 400 }
      );
    }

    // 3. File size restriction (Max 10MB)
    const MAX_FILE_SIZE = 10 * 1024 * 1024;
    if (file.size > MAX_FILE_SIZE) {
      return NextResponse.json(
        { error: "File too large. Maximum supported snapshot size is 10MB." },
        { status: 413 }
      );
    }

    // 4. File extension / mime check
    if (!file.name.toLowerCase().endsWith(".csv") && !file.name.toLowerCase().endsWith(".txt")) {
      return NextResponse.json(
        { error: "Invalid file type. Please upload a .CSV or .TXT process list." },
        { status: 400 }
      );
    }

    // 5. Parse CSV
    const csvContent = await file.text();
    const rows = parseProcessCSV(csvContent);

    if (rows.length === 0) {
      return NextResponse.json(
        { error: "No process records were found in the uploaded file." },
        { status: 400 }
      );
    }

    // 6. Execute ML Inference
    const results = analyzeProcesses(rows);

    // 7. Aggregate Scan Summary
    const threats = results.filter((r) => r.classification === "MALICIOUS");
    const suspicious = results.filter((r) => r.classification === "SUSPICIOUS");
    const safe = results.filter((r) => r.classification === "SAFE");

    const maxRisk = results.reduce((max, r) => Math.max(max, r.riskScore), 0);
    const avgRisk = Math.round((results.reduce((acc, r) => acc + r.riskScore, 0) / results.length) * 10) / 10;

    const summary: ScanSummary = {
      id: "scan_" + Date.now().toString(36) + "_" + Math.random().toString(36).substring(2, 6),
      timestamp: new Date().toISOString(),
      totalProcesses: results.length,
      threatsDetected: threats.length,
      suspiciousDetected: suspicious.length,
      safeCount: safe.length,
      maxRiskScore: maxRisk,
      averageRiskScore: avgRisk,
      results: results.sort((a, b) => b.riskScore - a.riskScore), // Highest risk first
    };

    return NextResponse.json(
      {
        success: true,
        summary,
      },
      {
        status: 200,
        headers: {
          "X-RateLimit-Limit": rateLimit.limit.toString(),
          "X-RateLimit-Remaining": rateLimit.remaining.toString(),
        },
      }
    );
  } catch (error: unknown) {
    console.error("[API Error] /api/analyze failed:", error);

    if (error instanceof CSVParseError) {
      return NextResponse.json(
        {
          error: "CSV Syntax Error: " + error.message,
          details: error.details,
        },
        { status: 400 }
      );
    }

    const message = error instanceof Error ? error.message : "Internal server error occurred";
    return NextResponse.json(
      { error: "Analysis failed: " + message },
      { status: 500 }
    );
  }
}
