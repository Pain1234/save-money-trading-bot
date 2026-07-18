import { DashboardChrome } from "@/components/layout/DashboardChrome";
import { requireAuth } from "@/lib/auth/server";

export const dynamic = "force-dynamic";

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await requireAuth();
  const username = session.username ?? "user";

  return <DashboardChrome username={username}>{children}</DashboardChrome>;
}
