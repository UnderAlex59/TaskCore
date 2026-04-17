import type { MessageRead } from "@/api/chatApi";
import { Avatar } from "@/shared/components/Avatar";
import { formatDateTime } from "@/shared/lib/locale";

interface Props {
  message: MessageRead;
}

function formatTimestamp(value: string) {
  return formatDateTime(value);
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.author_id !== null;
  const authorLabel = isUser
    ? (message.author_name ?? "Пользователь")
    : (message.agent_name ?? "Агент");
  const agentKey =
    typeof message.source_ref?.agent_key === "string"
      ? message.source_ref.agent_key
      : null;
  const accent =
    agentKey === "change-tracker" || message.agent_name === "ChangeTrackerAgent"
      ? "border-ember/20 bg-mist/70"
      : agentKey === "qa" || message.agent_name === "QAAgent"
        ? "border-ink/10 bg-white/90"
        : "border-black/10 bg-white/80";

  return (
    <div className={`flex items-end gap-3 ${isUser ? "justify-end" : "justify-start"}`}>
      {!isUser ? (
        <Avatar
          className="h-10 w-10 shrink-0 text-xs"
          imageUrl={message.author_avatar_url}
          name={authorLabel}
        />
      ) : null}

      <div
        className={[
          "max-w-[92%] border px-4 py-3 shadow-soft sm:max-w-[88%]",
          isUser
            ? "rounded-[12px] border-ink bg-ink text-white"
            : `rounded-[10px] ${accent}`,
        ].join(" ")}
      >
        <div className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-[0.14em]">
          <span>{authorLabel}</span>
          <span className={isUser ? "text-white/60" : "text-slate/60"}>
            {formatTimestamp(message.created_at)}
          </span>
        </div>
        <p
          className={`break-words text-sm leading-7 ${isUser ? "text-white/90" : "text-slate/80"}`}
        >
          {message.content}
        </p>
      </div>

      {isUser ? (
        <Avatar
          className="h-10 w-10 shrink-0 text-xs"
          imageUrl={message.author_avatar_url}
          name={authorLabel}
        />
      ) : null}
    </div>
  );
}
