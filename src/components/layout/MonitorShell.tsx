import { Footer } from "@/components/layout/Footer";
import { Navbar } from "@/components/layout/Navbar";
import { Sidebar } from "@/components/layout/Sidebar";

interface MonitorShellProps {
  username: string;
  children: React.ReactNode;
}

/** Paper-trading Monitor chrome — design-frozen; do not couple to ResearchShell. */
export function MonitorShell({ username, children }: MonitorShellProps) {
  return (
    <div className="dashboard-shell min-h-screen bg-bg-base text-text-primary">
      <div className="mx-auto max-w-[1600px] px-[var(--shell-padding-x)] pb-[var(--shell-padding-bottom)] pt-[var(--shell-padding-top)]">
        <Navbar username={username} />
        <div className="mt-[var(--header-gap)] grid gap-[var(--main-gap)] lg:grid-cols-[280px_minmax(0,1fr)]">
          <Sidebar />
          <main className="min-w-0">{children}</main>
        </div>
        <div className="mt-[var(--footer-gap)]">
          <Footer />
        </div>
      </div>
    </div>
  );
}
