import type { ReactNode } from "react";

import type { MessageRead } from "@/api/chatApi";
import MessageInput from "@/features/chat/MessageInput";
import MessageList from "@/features/chat/MessageList";

interface Props {
  agentPendingMessage?: MessageRead | null;
  actions?: ReactNode;
  className?: string;
  compactInput?: boolean;
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
  agentPendingMessage = null,
  actions,
  className = "",
  compactInput = false,
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
  const showHeader = Boolean(actions || eyebrow || title || description) && !compactInput;

  return (
    <section
      className={[
        "flex min-h-0 min-w-0 flex-col overflow-hidden rounded-[18px] border border-[rgba(9,30,66,0.12)] bg-white shadow-[0_1px_2px_rgba(9,30,66,0.06),0_12px_32px_rgba(9,30,66,0.05)]",
        className,
      ].join(" ")}
    >
      {showHeader ? (
        <div className="border-b border-[rgba(9,30,66,0.08)] bg-[#fafbfc] px-5 py-4 sm:px-6">
          <div className="flex min-w-0 flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[#5e6c84]">
                {eyebrow}
              </p>
              <h3 className="mt-2 text-2xl font-semibold text-[#172b4d]">
                {title}
              </h3>
              <p className="text-anywhere mt-2 hidden max-w-2xl text-sm leading-7 text-[#44546f] sm:block">
                {description}
              </p>
            </div>
            {actions ? <div className="shrink-0">{actions}</div> : null}
          </div>
        </div>
      ) : null}

      <div className="min-h-0 flex-1 overflow-y-auto bg-[#fcfcfd] px-5 py-5 sm:px-6">
        <MessageList
          agentPendingMessage={agentPendingMessage}
          currentUserId={currentUserId}
          messages={messages}
        />
      </div>

      <div
        className={
          compactInput
            ? "border-t border-[rgba(9,30,66,0.08)] bg-white px-4 py-3 sm:px-5"
            : "border-t border-[rgba(9,30,66,0.08)] bg-white px-5 py-4 sm:px-6"
        }
      >
        <MessageInput
          busy={sending}
          compact={compactInput}
          disabled={disabled}
          onSend={onSend}
          placeholder={inputPlaceholder}
        />
      </div>
    </section>
  );
}
