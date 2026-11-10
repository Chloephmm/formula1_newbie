import Image from "next/image";
import type { ConversationMessage } from "./chatReducer";
import QuickReplies from "./QuickReplies";
import ResponseSections from "./ResponseSections";

interface ChatMessageProps {
  message: ConversationMessage;
  onQuickReply: (prompt: string) => void;
}

export default function ChatMessage({ message, onQuickReply }: ChatMessageProps) {
  if (message.role === "user") {
    return (
      <div className="ml-auto max-w-[84%] rounded-2xl rounded-br-md bg-[#E8002D] px-4 py-3 font-nav text-sm leading-5 text-white shadow-lg shadow-[#E8002D]/10">
        {message.text}
      </div>
    );
  }

  const { reply } = message;
  return (
    <div className="flex items-start gap-2.5">
      <div className="mt-1 h-8 w-8 shrink-0 overflow-hidden rounded-full border border-[#E8002D] bg-white">
        <Image src="/images/f1-buddy-car.jpg" alt="" width={768} height={768} className="h-full w-full object-cover" />
      </div>
      <div className="min-w-0 max-w-[calc(100%-2.625rem)]">
        <article className="rounded-2xl rounded-tl-md bg-[#F4F6F8] px-4 py-3 text-[#171B24] shadow-[0_12px_30px_rgba(0,0,0,.22)]">
          {reply.image ? (
            <div className="mb-3 flex items-center gap-3 border-b border-black/10 pb-3">
              <Image src={reply.image.src} alt={reply.image.alt} width={64} height={64} className="h-12 w-12 rounded-full bg-white object-contain" />
              <h3 className="font-nav text-base font-bold">{reply.heading}</h3>
            </div>
          ) : (
            <h3 className="font-nav text-base font-bold">{reply.heading}</h3>
          )}
          <p className="mt-1 text-xs leading-5 text-[#3E4654]">{reply.body}</p>
          <ResponseSections sections={reply.sections} />
          {reply.sourceUpdatedAt ? (
            <p className="mt-3 border-t border-black/10 pt-2 text-[10px] text-[#697280]">
              Source updated {reply.sourceUpdatedAt}
            </p>
          ) : null}
        </article>
        <QuickReplies items={reply.quickReplies} onSelect={onQuickReply} />
      </div>
    </div>
  );
}
