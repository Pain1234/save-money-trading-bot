export function StatusBadge({
  status,
}: {
  status: "READY" | "DEGRADED" | "STOPPED";
}) {
  const styles =
    status === "READY"
      ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
      : status === "DEGRADED"
        ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
        : "bg-red-500/20 text-red-300 border-red-500/40";
  return (
    <span className={`rounded-full border px-3 py-1 text-xs font-medium ${styles}`}>
      {status}
    </span>
  );
}
