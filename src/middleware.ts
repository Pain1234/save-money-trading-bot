import { NextResponse, type NextRequest } from "next/server";
import { getIronSession } from "iron-session";

import { type DashboardSession, sessionOptions } from "@/lib/auth/session";

export async function middleware(request: NextRequest) {
  const secret = process.env.SESSION_SECRET;
  if (!secret || secret.length < 32) {
    return NextResponse.json(
      { detail: "dashboard auth not configured" },
      { status: 503 },
    );
  }

  const response = NextResponse.next();
  const session = await getIronSession<DashboardSession>(
    request,
    response,
    { ...sessionOptions, password: secret },
  );

  if (!session.isLoggedIn) {
    const loginUrl = new URL("/login", request.url);
    loginUrl.searchParams.set("next", request.nextUrl.pathname);
    return NextResponse.redirect(loginUrl);
  }

  return response;
}

export const config = {
  matcher: ["/dashboard/:path*", "/api/research/:path*"],
};
