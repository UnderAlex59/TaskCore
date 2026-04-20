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
      <div className="flex items-center gap-3 rounded-[14px] border border-[rgba(9,30,66,0.12)] bg-white px-5 py-3 shadow-[0_1px_2px_rgba(9,30,66,0.06)]">
        <span className="h-3 w-3 animate-pulse rounded-full bg-[#0c66e4]" />
        <span className="text-sm font-semibold text-[#44546f]">{label}</span>
      </div>
    </div>
  );
}
