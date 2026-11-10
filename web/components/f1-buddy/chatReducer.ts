import type { ChatReply } from "@/lib/chatbot/types";

export type WindowMode = "closed" | "open" | "minimized";

export type ConversationMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; reply: ChatReply };

export interface ChatState {
  mode: WindowMode;
  messages: ConversationMessage[];
  draft: string;
  pending: boolean;
  error: string | null;
}

export type ChatAction =
  | { type: "OPEN" }
  | { type: "RESTORE" }
  | { type: "MINIMIZE" }
  | { type: "CLOSE" }
  | { type: "SET_DRAFT"; draft: string }
  | { type: "SUBMIT"; id: string; text: string }
  | { type: "SUCCEED"; id: string; reply: ChatReply }
  | { type: "FAIL"; error: string };

export const initialChatState: ChatState = {
  mode: "closed",
  messages: [],
  draft: "",
  pending: false,
  error: null,
};

export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "OPEN":
    case "RESTORE":
      return { ...state, mode: "open" };
    case "MINIMIZE":
      return { ...state, mode: "minimized" };
    case "CLOSE":
      return { ...initialChatState, messages: [] };
    case "SET_DRAFT":
      return { ...state, draft: action.draft };
    case "SUBMIT":
      if (state.pending) return state;
      return {
        ...state,
        draft: "",
        pending: true,
        error: null,
        messages: [
          ...state.messages,
          { id: action.id, role: "user", text: action.text },
        ],
      };
    case "SUCCEED":
      return {
        ...state,
        pending: false,
        error: null,
        messages: [
          ...state.messages,
          { id: action.id, role: "assistant", reply: action.reply },
        ],
      };
    case "FAIL":
      return { ...state, pending: false, error: action.error };
  }
}
