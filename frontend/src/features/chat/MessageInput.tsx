import { useState } from "react";

interface Props {
  busy?: boolean;
  compact?: boolean;
  disabled?: boolean;
  onSend?: (value: string) => void | Promise<void>;
  placeholder?: string;
}

export default function MessageInput({
  compact = false,
  disabled = false,
  onSend,
  busy = false,
  placeholder,
}: Props) {
  const [value, setValue] = useState("");

  async function submitMessage() {
    if (!value.trim() || disabled || busy) {
      return;
    }

    await onSend?.(value.trim());
    setValue("");
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitMessage();
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void submitMessage();
    }
  }

  return (
    <form
      className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_auto]"
      onSubmit={handleSubmit}
    >
      <div>
        <label className="sr-only" htmlFor="task-chat-message">
          Сообщение в чат
        </label>
        <textarea
          className={
            compact
              ? "ui-field min-h-16 resize-none sm:min-h-20"
              : "ui-field min-h-20 resize-none sm:min-h-24"
          }
          disabled={disabled || busy}
          id="task-chat-message"
          name="message"
          onChange={(event) => setValue(event.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={
            placeholder ??
            (disabled
              ? "Чат недоступен в текущем состоянии задачи."
              : "Напишите сообщение, используйте /qaagent или запросите изменение...")
          }
          value={value}
        />
        {compact ? null : (
          <p className="mt-2 text-xs leading-5 text-slate/60">
            {disabled
              ? "Чат сейчас недоступен."
              : "Нажмите Enter для отправки. Shift+Enter переносит строку."}
          </p>
        )}
      </div>
      <button
        className="ui-button-primary self-end px-5 py-3"
        disabled={disabled || busy}
        type="submit"
      >
        {busy ? "Отправляем..." : "Отправить"}
      </button>
    </form>
  );
}
