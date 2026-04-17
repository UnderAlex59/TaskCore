interface Props {
  fullscreen?: boolean;
  label?: string;
}

export function LoadingSpinner({
  fullscreen = false,
  label = "Загрузка",
}: Props) {
  const wrapperClass = fullscreen
    ? "flex min-h-screen items-center justify-center"
    : "flex items-center justify-center py-8";

  return (
    <div aria-live="polite" className={wrapperClass} role="status">
      <div className="glass-panel flex items-center gap-3 rounded-[10px] border border-black/10 px-5 py-3 shadow-panel">
        <span className="h-3 w-3 animate-pulse rounded-full bg-ember" />
        <span className="text-sm font-semibold uppercase tracking-[0.18em] text-ink/70">
          {label}
        </span>
      </div>
    </div>
  );
}
