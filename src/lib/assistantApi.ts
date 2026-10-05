/**
 * Assistant API client wrapper.
 * Calls POST /assistant/chat via authenticated apiRequest, passing signal for cancellation.
 */

import { apiRequest } from "./api";
import { AssistantChatResponse, ChatMessage } from "./assistantTypes";

export async function sendAssistantMessage(
  messages: ChatMessage[],
  clientDate: string,
  signal?: AbortSignal
): Promise<AssistantChatResponse> {
  return apiRequest<AssistantChatResponse>("/assistant/chat", {
    method: "POST",
    body: JSON.stringify({
      messages,
      client_date: clientDate,
    }),
    signal,
  });
}
