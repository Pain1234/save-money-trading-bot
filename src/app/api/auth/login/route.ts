import { NextResponse } from "next/server";

import { verifyCredentials } from "@/lib/auth/credentials";
import { checkLoginRateLimit, resetLoginRateLimit } from "@/lib/auth/rate-limit";
import { getSession } from "@/lib/auth/server";
import { requireSessionSecret } from "@/lib/auth/session";

export async function POST(request: Request) {
  try {
    requireSessionSecret();
  } catch {
    return NextResponse.json({ detail: "auth not configured" }, { status: 503 });
  }

  const clientIp =
    request.headers.get("x-forwarded-for")?.split(",")[0]?.trim() ?? "unknown";
  if (!checkLoginRateLimit(clientIp)) {
    return NextResponse.json({ detail: "too many login attempts" }, { status: 429 });
  }

  const body = (await request.json()) as { username?: string; password?: string };
  if (!body.username || !body.password) {
    return NextResponse.json({ detail: "username and password required" }, { status: 400 });
  }

  const valid = await verifyCredentials(body.username, body.password);
  if (!valid) {
    return NextResponse.json({ detail: "invalid credentials" }, { status: 401 });
  }

  resetLoginRateLimit(clientIp);
  const session = await getSession();
  session.isLoggedIn = true;
  session.username = body.username;
  await session.save();
  return NextResponse.json({ ok: true });
}
