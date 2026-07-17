export interface NavItem {
  label: string;
  href: string;
  active?: boolean;
}

/** Primary navbar links for the design shell. */
export const PRIMARY_NAV: NavItem[] = [
  { label: "Dashboard", href: "/dashboard", active: true },
  { label: "Positionen", href: "/dashboard/positions" },
  { label: "Fills", href: "/dashboard/fills" },
  { label: "Equity", href: "/dashboard/equity" },
  { label: "Status", href: "/dashboard/status" },
  { label: "Incidents", href: "/dashboard/incidents" },
];

/** Diagnostic detail routes (sidebar + secondary nav). */
export const DETAIL_NAV: NavItem[] = [
  { label: "Overview", href: "/dashboard" },
  { label: "Status", href: "/dashboard/status" },
  { label: "Positions", href: "/dashboard/positions" },
  { label: "Wallet", href: "/dashboard/wallet" },
  { label: "Orders", href: "/dashboard/orders" },
  { label: "Fills", href: "/dashboard/fills" },
  { label: "Stops", href: "/dashboard/stops" },
  { label: "Scheduler", href: "/dashboard/scheduler" },
  { label: "Equity", href: "/dashboard/equity" },
  { label: "Incidents", href: "/dashboard/incidents" },
];
