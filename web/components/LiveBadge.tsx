// Indicator showing whether data came live from Jolpica or fell back to a static snapshot.
export default function LiveBadge({ live }: { live: boolean }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1 text-xs text-muted">
      <span className={`h-2 w-2 rounded-full ${live ? "bg-green-500" : "bg-muted"}`} aria-hidden />
      {live ? "Live from Jolpica" : "Showing saved snapshot"}
    </span>
  );
}
