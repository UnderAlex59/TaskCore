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
  description = "Задавайте вопросы по требованию, предлагайте изменения или используйте служебную команду /qaagent для явной проверки.",
  disabled = true,
  eyebrow = "Обсуждение задачи",
  inputPlaceholder,
  messages,
  onSend,
  sending = false,
  title = "Обсуждение",
}: Props) {
  return (
    <section
      className={[
        "flex min-h-[34rem] flex-col overflow-hidden rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-white shadow-[0_1px_2px_rgba(9,30,66,0.06),0_12px_32px_rgba(9,30,66,0.05)]",
        className,
      ].join(" ")}
    >
      <div className="border-b border-[rgba(9,30,66,0.08)] bg-[#fafbfc] px-5 py-4 sm:px-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
              {eyebrow}
            </p>
            <h3 className="mt-2 text-2xl font-semibold text-[#172b4d]">
              {title}
            </h3>
            <p className="mt-2 max-w-2xl text-sm leading-7 text-[#44546f]">
              {description}
            </p>
          </div>
          {actions ? <div className="shrink-0">{actions}</div> : null}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto bg-[#fcfcfd] px-5 py-5 sm:px-6">
        <MessageList currentUserId={currentUserId} messages={messages} />
      </div>

      <div className="border-t border-[rgba(9,30,66,0.08)] bg-white px-5 py-4 sm:px-6">
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
