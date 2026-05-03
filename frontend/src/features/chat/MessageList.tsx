import { useEffect, useRef } from "react";

import type { MessageRead } from "@/api/chatApi";
import MessageBubble from "@/features/chat/MessageBubble";

interface Props {
  currentUserId?: string;
  messages: MessageRead[];
}

function getPendingQuestion(messages: MessageRead[]) {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (message.author_id === null) {
      return null;
    }
    if (message.message_type === "question") {
      return message;
    }
  }

  return null;
}

function AgentThinkingIndicator({ question }: { question: MessageRead }) {
  return (
    <div
      aria-live="polite"
      className="flex min-w-0 items-start gap-3"
      role="status"
    >
      <div
        aria-hidden="true"
        className="grid h-10 w-10 shrink-0 place-items-center rounded-full border border-[#bfd4f6] bg-[#f4f8ff]"
      >
        <div className="flex items-center gap-1">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#0c66e4]" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#0c66e4] [animation-delay:120ms]" />
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#0c66e4] [animation-delay:240ms]" />
        </div>
      </div>
      <div className="min-w-0 max-w-[42rem] rounded-[14px] border border-[rgba(12,102,228,0.16)] bg-[#f8fbff] px-4 py-3 text-sm text-[#172b4d] shadow-[0_1px_2px_rgba(9,30,66,0.05)]">
        <p className="text-anywhere font-semibold text-[#172b4d]">
          Агент готовит ответ по задаче
        </p>
        <p className="text-anywhere mt-1 text-xs leading-5 text-[#626f86]">
          Вопрос распознан. Ответ появится в этой ветке чата.
        </p>
        <p className="text-anywhere mt-2 line-clamp-2 text-xs leading-5 text-[#44546f]">
          «{question.content}»
        </p>
      </div>
    </div>
  );
}

export default function MessageList({ currentUserId, messages }: Props) {
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const lastMessageId = messages.at(-1)?.id;
  const pendingQuestion = getPendingQuestion(messages);

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
      <div className="flex h-full min-h-[18rem] items-center justify-center rounded-[16px] border border-dashed border-[rgba(9,30,66,0.12)] bg-white px-6 py-10">
        <p
          aria-live="polite"
          className="max-w-md text-center text-sm leading-7 text-[#626f86]"
        >
          Сообщений пока нет. Начните обсуждение, чтобы уточнить требование,
          предложить изменение или принять решение по следующему шагу.
        </p>
      </div>
    );
  }

  return (
    <div
      aria-live="polite"
      aria-relevant="additions text"
      className="min-w-0 space-y-4 pb-1"
      role="log"
    >
      {messages.map((message) => (
        <MessageBubble
          currentUserId={currentUserId}
          key={message.id}
          message={message}
        />
      ))}
      {pendingQuestion ? (
        <AgentThinkingIndicator question={pendingQuestion} />
      ) : null}
      <div ref={bottomRef} />
    </div>
  );
}
