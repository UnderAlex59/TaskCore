import type { ReactNode } from "react";

import type { MessageRead } from "@/api/chatApi";
import MessageInput from "@/features/chat/MessageInput";
import MessageList from "@/features/chat/MessageList";

interface Props {
  actions?: ReactNode;
  className?: string;
  currentUserId?: string;
  description?: string;
  disabled?: boolean;
  eyebrow?: string;
  inputPlaceholder?: string;
  messages: MessageRead[];
  onSend?: (value: string) => Promise<void>;
  sending?: boolean;
  title?: string;
}

export default function ChatWindow({
  actions,
  className = "",
  currentUserId,
  description = "Задавайте вопросы по требованию, предлагайте изменения или вызывайте конкретного агента через /qaagent, /qa или @agent.",
  disabled = true,
  eyebrow = "Чат задачи",
  inputPlaceholder,
  messages,
  onSend,
  sending = false,
  title = "Диалог",
}: Props) {
  return (
    <section
      className={[
        "glass-panel flex min-h-[34rem] flex-col overflow-hidden border border-black/10 p-5 shadow-panel sm:p-6 xl:min-h-[40rem]",
        className,
      ].join(" ")}
    >
      <div className="flex flex-col gap-4 border-b border-black/8 pb-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.18em] text-ember">
            {eyebrow}
          </p>
          <h3 className="mt-2 text-2xl font-bold text-ink sm:text-3xl">
            {title}
          </h3>
          <p className="mt-2 max-w-2xl text-sm leading-7 text-slate/75">
            {description}
          </p>
        </div>
        {actions ? <div className="shrink-0">{actions}</div> : null}
      </div>

      <div className="mt-4 min-h-0 flex-1 overflow-y-auto pr-1">
        <MessageList currentUserId={currentUserId} messages={messages} />
      </div>

      <div className="mt-4 border-t border-black/8 pt-4">
        <MessageInput
          busy={sending}
          disabled={disabled}
          onSend={onSend}
          placeholder={inputPlaceholder}
        />
      </div>
    </section>
  );
}
