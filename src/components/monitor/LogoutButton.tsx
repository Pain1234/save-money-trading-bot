"use client";

import { useRouter } from "next/navigation";

import { cn } from "@/lib/utils";

interface LogoutButtonProps {
  className?: string;
}

export function LogoutButton({ className }: LogoutButtonProps) {
  const router = useRouter();

  async function logout() {
    await fetch("/api/auth/logout", { method: "POST" });
    router.replace("/login");
    router.refresh();
  }

  return (
    <button
      type="button"
      onClick={logout}
      className={cn(
        "rounded-md border border-border-subtle px-3 py-1 text-sm",
        className,
      )}
    >
      Logout
    </button>
  );
}
