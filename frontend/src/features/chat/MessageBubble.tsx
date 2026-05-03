import type { MessageRead } from "@/api/chatApi";
import { Avatar } from "@/shared/components/Avatar";
import { formatDateTime, getAgentKeyLabel } from "@/shared/lib/locale";

interface Props {
  currentUserId?: string;
  message: MessageRead;
}

function formatTimestamp(value: string) {
  return formatDateTime(value);
}

export default function MessageBubble({ currentUserId, message }: Props) {
  const isHumanMessage = message.author_id !== null;
  const isAgentMessage = !isHumanMessage;
  const isOwnMessage =
    isHumanMessage &&
    currentUserId != null &&
    message.author_id === currentUserId;
  const agentKey =
    typeof message.source_ref?.agent_key === "string"
      ? message.source_ref.agent_key
      : null;
  const agentDescription =
    typeof message.source_ref?.agent_description === "string"
      ? message.source_ref.agent_description
      : null;
  const agentLabel = getAgentKeyLabel(agentKey);
  const authorLabel = isHumanMessage
    ? (message.author_name ?? "Пользователь")
    : agentLabel;

  const surfaceClass = isOwnMessage
    ? "border-[#0c66e4] bg-[#0c66e4] text-white"
    : isAgentMessage
      ? "border-[rgba(12,102,228,0.16)] bg-[#f8fbff] text-[#172b4d]"
      : "border-[rgba(9,30,66,0.1)] bg-white text-[#172b4d]";
  const agentAccentClass =
    agentKey === "change-tracker" || message.agent_name === "ChangeTrackerAgent"
      ? "bg-[#ac6b08]"
      : agentKey === "qa" || message.agent_name === "QAAgent"
        ? "bg-[#0c66e4]"
        : "bg-[#44546f]";
  const avatarClass = isAgentMessage
    ? "h-10 w-10 shrink-0 border-[#bfd4f6] bg-[#f4f8ff] text-xs text-[#0c66e4]"
    : "h-10 w-10 shrink-0 text-xs";

  return (
    <div
      className={`flex min-w-0 items-end gap-3 ${isOwnMessage ? "justify-end" : "justify-start"}`}
    >
      {!isOwnMessage ? (
        <Avatar
          className={avatarClass}
          imageUrl={message.author_avatar_url}
          name={authorLabel}
        />
      ) : null}

      <div
        className={[
          "relative min-w-0 max-w-[42rem] rounded-[14px] border px-4 py-3 shadow-[0_1px_2px_rgba(9,30,66,0.05)]",
          isAgentMessage ? "overflow-hidden pl-5" : "",
          surfaceClass,
        ].join(" ")}
      >
        {isAgentMessage ? (
          <span
            aria-hidden="true"
            className={`absolute inset-y-0 left-0 w-1 ${agentAccentClass}`}
          />
        ) : null}
        <div className="mb-2 flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.14em]">
          <span>{authorLabel}</span>
          {isAgentMessage ? (
            <span className="rounded-full border border-[rgba(12,102,228,0.14)] bg-white px-2 py-0.5 text-[10px] text-[#0c66e4]">
              Агент
            </span>
          ) : null}
          <span className={isOwnMessage ? "text-white/70" : "text-[#626f86]"}>
            {formatTimestamp(message.created_at)}
          </span>
        </div>
        <p
          className={`text-anywhere text-sm leading-7 ${isOwnMessage ? "text-white/95" : "text-[#172b4d]"}`}
        >
          {message.content}
        </p>
        {isAgentMessage && agentDescription ? (
          <p className="text-anywhere mt-3 border-t border-[rgba(12,102,228,0.12)] pt-2 text-xs leading-5 text-[#626f86]">
            {agentDescription}
          </p>
        ) : null}
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
