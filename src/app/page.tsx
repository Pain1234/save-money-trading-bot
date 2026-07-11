import { DashboardMain } from "@/components/dashboard/DashboardMain";
import { Footer } from "@/components/layout/Footer";
import { Navbar } from "@/components/layout/Navbar";
import { Sidebar } from "@/components/layout/Sidebar";

export default function HomePage() {
  return (
    <div className="min-h-screen overflow-x-hidden bg-bg-base">
      <div className="dashboard-shell">
        <div className="main-grid">
          <aside className="min-w-0">
            <Sidebar />
          </aside>

          <div className="main-column min-w-0">
            <Navbar />
            <main>
              <DashboardMain />
            </main>
            <Footer />
          </div>
        </div>
      </div>
    </div>
  );
}
