import { NextResponse } from "next/server";

import { PaperApiError, PaperApiTimeoutError } from "@/lib/paper-api/client";

const API_TIMEOUT_MS = 30_000;

function apiBaseUrl(): string {
  const url = process.env.PRIVATE_PAPER_API_URL;
  if (!url) {
    throw new Error("PRIVATE_PAPER_API_URL is required");
  }
  return url.replace(/\/$/, "");
}

export async function proxyResearch(
  path: string,
  init?: {
    method?: string;
    body?: unknown;
    /** When true, forward upstream Content-Type (artifact content #357). */
    preserveContentType?: boolean;
  },
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    const response = await fetch(`${apiBaseUrl()}${path}`, {
      method: init?.method ?? "GET",
      cache: "no-store",
      headers: {
        Accept: "*/*",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
      },
      body: init?.body ? JSON.stringify(init.body) : undefined,
      signal: controller.signal,
    });
    const text = await response.text();
    const upstreamType = response.headers.get("Content-Type");
    const contentType =
      init?.preserveContentType && upstreamType
        ? upstreamType
        : "application/json";
    const headers = new Headers({ "Content-Type": contentType });
    const nosniff = response.headers.get("X-Content-Type-Options");
    if (nosniff) {
      headers.set("X-Content-Type-Options", nosniff);
    }
    const rel = response.headers.get("X-Artifact-Relative-Path");
    if (rel) {
      headers.set("X-Artifact-Relative-Path", rel);
    }
    const checksum = response.headers.get("X-Artifact-Checksum-Sha256");
    if (checksum) {
      headers.set("X-Artifact-Checksum-Sha256", checksum);
    }
    return new NextResponse(text, {
      status: response.status,
      headers,
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") {
      return NextResponse.json(
        { detail: "Research API timeout" },
        { status: 504 },
      );
    }
    const message =
      error instanceof PaperApiError || error instanceof PaperApiTimeoutError
        ? error.message
        : "Research API unavailable";
    return NextResponse.json({ detail: message }, { status: 502 });
  } finally {
    clearTimeout(timeoutId);
  }
}
