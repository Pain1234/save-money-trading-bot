/** Shorten long research IDs for Overview chrome — full ID stays in a11y/tooltip. */
export function shortenResearchId(
  id: string,
  head = 8,
  tail = 6,
): string {
  const trimmed = id.trim();
  if (!trimmed) return trimmed;
  if (trimmed.length <= head + tail + 1) return trimmed;
  return `${trimmed.slice(0, head)}…${trimmed.slice(-tail)}`;
}

export function researchIdAriaLabel(kind: string, id: string): string {
  return `${kind}: ${id}`;
}
