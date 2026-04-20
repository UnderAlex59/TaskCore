import type { MessageRead } from "@/api/chatApi";
import { Avatar } from "@/shared/components/Avatar";
import { formatDateTime } from "@/shared/lib/locale";

interface Props {
  currentUserId?: string;
  message: MessageRead;
}

function formatTimestamp(value: string) {
  return formatDateTime(value);
}

export default function MessageBubble({ currentUserId, message }: Props) {
  const isHumanMessage = message.author_id !== null;
  const isOwnMessage =
    isHumanMessage &&
    currentUserId != null &&
    message.author_id === currentUserId;
  const authorLabel = isHumanMessage
    ? (message.author_name ?? "Пользователь")
    : (message.agent_name ?? "Система");
  const agentKey =
    typeof message.source_ref?.agent_key === "string"
      ? message.source_ref.agent_key
      : null;

  const surfaceClass = isOwnMessage
    ? "border-[#0c66e4] bg-[#0c66e4] text-white"
    : agentKey === "change-tracker" ||
        message.agent_name === "ChangeTrackerAgent"
      ? "border-[rgba(172,107,8,0.18)] bg-[#fff4e5] text-[#172b4d]"
      : agentKey === "qa" || message.agent_name === "QAAgent"
        ? "border-[rgba(12,102,228,0.14)] bg-[#e9f2ff] text-[#172b4d]"
        : "border-[rgba(9,30,66,0.1)] bg-white text-[#172b4d]";

  return (
    <div
      className={`flex items-end gap-3 ${isOwnMessage ? "justify-end" : "justify-start"}`}
    >
      {!isOwnMessage ? (
        <Avatar
          className="h-10 w-10 shrink-0 text-xs"
          imageUrl={message.author_avatar_url}
          name={authorLabel}
        />
      ) : null}

      <div
        className={[
          "max-w-[92%] rounded-[16px] border px-4 py-3 shadow-[0_1px_2px_rgba(9,30,66,0.05)] sm:max-w-[88%]",
          surfaceClass,
        ].join(" ")}
      >
        <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em]">
          <span>{authorLabel}</span>
          <span className={isOwnMessage ? "text-white/70" : "text-[#626f86]"}>
            {formatTimestamp(message.created_at)}
          </span>
        </div>
        <p
          className={`break-words text-sm leading-7 ${isOwnMessage ? "text-white/95" : "text-[#172b4d]"}`}
        >
          {message.content}
        </p>
      </div>

      {isOwnMessage ? (
        <Avatar
          className="h-10 w-10 shrink-0 text-xs"
          imageUrl={message.author_avatar_url}
          name={authorLabel}
        />
      ) : null}
    </div>
  );
}
