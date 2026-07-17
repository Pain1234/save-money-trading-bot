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
  init?: { method?: string; body?: unknown },
): Promise<Response> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT_MS);
  try {
    const response = await fetch(`${apiBaseUrl()}${path}`, {
      method: init?.method ?? "GET",
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...(init?.body ? { "Content-Type": "application/json" } : {}),
      },
      body: init?.body ? JSON.stringify(init.body) : undefined,
      signal: controller.signal,
    });
    const text = await response.text();
    return new NextResponse(text, {
      status: response.status,
      headers: { "Content-Type": "application/json" },
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
