import Link from "next/link";

import { LogoutButton } from "@/components/monitor/LogoutButton";
import { requireAuth } from "@/lib/auth/server";

export const dynamic = "force-dynamic";

const NAV = [
  { href: "/dashboard", label: "Overview" },
  { href: "/dashboard/status", label: "Status" },
  { href: "/dashboard/positions", label: "Positions" },
  { href: "/dashboard/wallet", label: "Wallet" },
  { href: "/dashboard/orders", label: "Orders" },
  { href: "/dashboard/fills", label: "Fills" },
  { href: "/dashboard/stops", label: "Stops" },
  { href: "/dashboard/scheduler", label: "Scheduler" },
  { href: "/dashboard/equity", label: "Equity" },
  { href: "/dashboard/incidents", label: "Incidents" },
];

export default async function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const session = await requireAuth();

  return (
    <div className="min-h-screen bg-bg-base text-text-primary">
      <header className="border-b border-border-subtle bg-bg-elevated">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3">
          <div>
            <p className="font-semibold">Paper Trading Monitor</p>
            <p className="text-xs text-text-muted">Signed in as {session.username}</p>
          </div>
          <LogoutButton />
        </div>
        <nav className="mx-auto flex max-w-7xl gap-3 overflow-x-auto px-4 pb-3 text-sm">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="whitespace-nowrap rounded-md px-2 py-1 hover:bg-bg-base"
            >
              {item.label}
            </Link>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-6">{children}</main>
    </div>
  );
}
