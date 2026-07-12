import { getIronSession } from "iron-session";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";

import {
  type DashboardSession,
  requireSessionSecret,
  sessionOptions,
} from "@/lib/auth/session";

export async function getSession() {
  const options = { ...sessionOptions, password: requireSessionSecret() };
  return getIronSession<DashboardSession>(await cookies(), options);
}

export async function requireAuth() {
  const session = await getSession();
  if (!session.isLoggedIn) {
    redirect("/login");
  }
  return session;
}
