import { useEffect, useRef } from "react";

import type { MessageRead } from "@/api/chatApi";
import MessageBubble from "@/features/chat/MessageBubble";

interface Props {
  currentUserId?: string;
  messages: MessageRead[];
}

export default function MessageList({ currentUserId, messages }: Props) {
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const lastMessageId = messages.at(-1)?.id;

  useEffect(() => {
    if (!bottomRef.current) {
      return;
    }

    bottomRef.current.scrollIntoView({
      behavior: messages.length > 1 ? "smooth" : "auto",
      block: "end",
    });
  }, [lastMessageId, messages.length]);

  if (messages.length === 0) {
    return (
      <div className="flex h-full min-h-[16rem] items-center justify-center rounded-[10px] border border-dashed border-black/10 bg-white/55 px-5 py-8">
        <p
          aria-live="polite"
          className="max-w-md text-center text-sm leading-7 text-slate/70"
        >
          Сообщений пока нет. Начните обсуждение, чтобы уточнить требование,
          запросить изменение или перейти к следующему шагу проверки.
        </p>
      </div>
    );
  }

  return (
    <div
      aria-live="polite"
      aria-relevant="additions text"
      className="space-y-4 pb-1"
      role="log"
    >
      {messages.map((message) => (
        <MessageBubble
          currentUserId={currentUserId}
          key={message.id}
          message={message}
        />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
