import { NextResponse } from "next/server";

import { getSession } from "@/lib/auth/server";

export async function POST() {
  const session = await getSession();
  session.destroy();
  return NextResponse.json({ ok: true });
}
