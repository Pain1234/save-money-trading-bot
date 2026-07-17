"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { FormEvent, useState } from "react";

export default function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    setLoading(true);
    setError(null);
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    setLoading(false);
    if (!response.ok) {
      const body = (await response.json().catch(() => ({}))) as { detail?: string };
      setError(body.detail ?? "Login failed");
      return;
    }
    const next = searchParams.get("next") || "/dashboard";
    router.replace(next);
    router.refresh();
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-base px-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-md rounded-xl border border-border-subtle bg-bg-elevated p-6 shadow-lg"
      >
        <h1 className="mb-2 text-xl font-semibold text-text-primary">
          Paper Trading Dashboard
        </h1>
        <p className="mb-6 text-sm text-text-muted">
          Sign in to monitor the read-only paper trading orchestrator.
        </p>
        <label className="mb-4 block text-sm text-text-secondary">
          Username
          <input
            name="username"
            className="mt-1 w-full rounded-md border border-border-subtle bg-bg-base px-3 py-2"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </label>
        <label className="mb-4 block text-sm text-text-secondary">
          Password
          <input
            name="password"
            type="password"
            className="mt-1 w-full rounded-md border border-border-subtle bg-bg-base px-3 py-2"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error ? <p className="mb-4 text-sm text-red-400">{error}</p> : null}
        <button
          type="submit"
          disabled={loading}
          className="w-full rounded-md bg-accent px-4 py-2 font-medium text-white disabled:opacity-60"
        >
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </div>
  );
}
