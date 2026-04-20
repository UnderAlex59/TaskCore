import { useEffect, useId, useRef } from "react";

interface Props {
  busy?: boolean;
  cancelLabel?: string;
  confirmLabel?: string;
  description: string;
  destructive?: boolean;
  onClose: () => void;
  onConfirm?: () => void | Promise<void>;
  open: boolean;
  title: string;
}

export function ConfirmDialog({
  busy = false,
  cancelLabel = "Отмена",
  open,
  title,
  description,
  confirmLabel = "Подтвердить",
  destructive = false,
  onClose,
  onConfirm,
}: Props) {
  const titleId = useId();
  const descriptionId = useId();
  const cancelButtonRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!open) {
      return undefined;
    }

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    cancelButtonRef.current?.focus();

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape" && !busy) {
        event.preventDefault();
        onClose();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [busy, onClose, open]);

  if (!open) {
    return null;
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(9,30,66,0.24)] px-6 py-8 [overscroll-behavior:contain]"
      onClick={busy ? undefined : onClose}
    >
      <div
        aria-busy={busy}
        aria-describedby={descriptionId}
        aria-labelledby={titleId}
        aria-modal="true"
        className="w-full max-w-md rounded-[20px] border border-[rgba(9,30,66,0.12)] bg-white p-8 shadow-[0_24px_48px_rgba(9,30,66,0.18)]"
        onClick={(event) => event.stopPropagation()}
        role="dialog"
      >
        <h2 className="text-2xl font-semibold text-[#172b4d]" id={titleId}>
          {title}
        </h2>
        <p className="mt-3 text-sm leading-7 text-[#44546f]" id={descriptionId}>
          {description}
        </p>
        <div className="mt-6 flex justify-end gap-3">
          <button
            className="ui-button-secondary"
            onClick={onClose}
            ref={cancelButtonRef}
            type="button"
          >
            {cancelLabel}
          </button>
          <button
            className={destructive ? "ui-button-danger" : "ui-button-primary"}
            disabled={busy}
            onClick={() => void onConfirm?.()}
            type="button"
          >
            {busy ? `${confirmLabel}...` : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
