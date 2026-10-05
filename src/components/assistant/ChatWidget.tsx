/**
 * Floating AI Assistant Chat Widget for RiskLens.
 *
 * Implements:
 * - Floating trigger button (bottom-5 right-5 z-[60], icon brain)
 * - Accessible labelled dialog panel (380x560 desktop, full-screen on <=480px)
 * - Auto-scroll, textarea (Enter to send, Shift+Enter newline, max 2000 chars)
 * - In-flight cancellation via AbortController on unmount
 * - Local date builder using getFullYear/getMonth/getDate (bypassing UTC bug)
 * - Extensible block rendering via BlockRenderer
 * - Pluggable send prop for fixture testing
 */

import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  AssistantChatResponse,
  AssistantMessageState,
  ChatMessage,
} from "../../lib/assistantTypes";
import { sendAssistantMessage } from "../../lib/assistantApi";
import { FIXTURE_RESPONSES } from "./fixtures";
import { BlockRenderer } from "./BlockRenderer";
import { I } from "../icons";

export interface ChatWidgetProps {
  /** Optional custom send function for fixture testing */
  send?: (
    messages: ChatMessage[],
    clientDate: string,
    signal?: AbortSignal
  ) => Promise<AssistantChatResponse>;
}

const STARTER_PROMPTS = [
  "Predict my next month's expenses and finances",
  "Financial report for the past week",
  "What can you do?",
];

function getLocalClientDate(): string {
  const now = new Date();
  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export const ChatWidget: React.FC<ChatWidgetProps> = ({
  send = sendAssistantMessage,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [inputText, setInputText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [messages, setMessages] = useState<AssistantMessageState[]>([]);

  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // Auto-scroll to bottom of messages
  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    if (isOpen) {
      scrollToBottom();
    }
  }, [messages, isOpen, isLoading]);

  // Focus input when opened
  useEffect(() => {
    if (isOpen) {
      setTimeout(() => {
        textareaRef.current?.focus();
      }, 100);
    }
  }, [isOpen]);

  // Handle escape key to close dialog
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        setIsOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  // Abort in-flight request on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, []);

  const handleSend = useCallback(
    async (textToSend?: string) => {
      const text = (textToSend ?? inputText).trim();
      if (!text || isLoading || text.length > 2000) return;

      const userMsg: AssistantMessageState = {
        id: `user_${Date.now()}`,
        role: "user",
        text,
      };

      const updatedHistory = [...messages, userMsg];
      setMessages(updatedHistory);
      setInputText("");
      setIsLoading(true);

      // Abort any existing in-flight request
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      const controller = new AbortController();
      abortControllerRef.current = controller;

      // Extract last 12 {role, text} turns
      const turnsToSend: ChatMessage[] = updatedHistory.slice(-12).map((m) => ({
        role: m.role,
        text: m.text,
      }));

      try {
        const clientDate = getLocalClientDate();
        let response: AssistantChatResponse;
        const lower = text.toLowerCase();
        if (lower.startsWith("fixture:forecast")) {
          response = FIXTURE_RESPONSES.forecast_single;
        } else if (lower.startsWith("fixture:finances")) {
          response = FIXTURE_RESPONSES.finances_two_line;
        } else if (lower.startsWith("fixture:report")) {
          response = FIXTURE_RESPONSES.report_bars;
        } else {
          response = await send(turnsToSend, clientDate, controller.signal);
        }

        const assistantMsg: AssistantMessageState = {
          id: response.id || `asst_${Date.now()}`,
          role: "assistant",
          text: response.text,
          blocks: response.blocks,
          outcome: response.outcome,
        };

        setMessages((prev) => [...prev, assistantMsg]);
      } catch (err: any) {
        if (err?.name === "AbortError") {
          return;
        }

        const errorMsg: AssistantMessageState = {
          id: `err_${Date.now()}`,
          role: "assistant",
          text: "Something went wrong while connecting to the assistant. Please try again.",
          isError: true,
        };
        setMessages((prev) => [...prev, errorMsg]);
      } finally {
        setIsLoading(false);
        abortControllerRef.current = null;
      }
    },
    [inputText, isLoading, messages, send]
  );

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleRetry = (lastUserMsgText: string) => {
    // Remove the error message and retry
    setMessages((prev) => prev.filter((m) => !m.isError));
    handleSend(lastUserMsgText);
  };

  return (
    <>
      {/* Floating Trigger Button */}
      <button
        type="button"
        id="assistant-toggle-button"
        aria-label="Open AI Assistant"
        aria-expanded={isOpen}
        aria-controls="assistant-panel"
        onClick={() => setIsOpen((prev) => !prev)}
        className="fixed bottom-5 right-5 z-[60] w-12 h-12 rounded-full bg-gradient-primary text-white shadow-lg flex items-center justify-center hover:opacity-95 active:scale-95 transition-all duration-150 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-primary-500"
      >
        <I name={isOpen ? "x" : "brain"} className="w-6 h-6 text-white" />
      </button>

      {/* Floating Chat Panel */}
      {isOpen && (
        <div
          id="assistant-panel"
          role="dialog"
          aria-label="RiskLens Assistant"
          aria-modal="false"
          className="fixed bottom-20 right-5 z-[60] w-[380px] h-[560px] max-w-[calc(100vw-2rem)] max-h-[calc(100vh-6.5rem)] bg-card border border-line rounded-2xl shadow-xl flex flex-col overflow-hidden max-[480px]:inset-0 max-[480px]:w-full max-[480px]:h-full max-[480px]:rounded-none max-[480px]:bottom-0"
        >
          {/* Header */}
          <div className="px-4 py-3 border-b border-line flex items-center justify-between bg-bg-soft">
            <div className="flex items-center gap-2">
              <div className="w-7 h-7 rounded-lg bg-gradient-primary flex items-center justify-center text-white shrink-0">
                <I name="brain" className="w-4 h-4 text-white" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-ink leading-none">
                  RiskLens Assistant
                </h3>
                <span className="text-[10px] text-ink-faint">
                  Insights & Forecasting
                </span>
              </div>
            </div>
            <button
              type="button"
              onClick={() => setIsOpen(false)}
              className="p-1.5 rounded-lg text-ink-faint hover:text-ink hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
              aria-label="Close Assistant"
            >
              <I name="x" className="w-4 h-4" />
            </button>
          </div>

          {/* Message List */}
          <div className="flex-1 p-4 overflow-y-auto space-y-4">
            {messages.length === 0 ? (
              <div className="h-full flex flex-col justify-center items-center text-center px-2 space-y-4">
                <div className="w-12 h-12 rounded-2xl bg-primary-500/10 flex items-center justify-center text-primary-600 dark:text-primary-400">
                  <I name="brain" className="w-6 h-6" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-ink">
                    How can I help you today?
                  </h4>
                  <p className="text-xs text-ink-faint mt-1 max-w-[260px]">
                    Ask about spending trends, financial summaries, or future predictions.
                  </p>
                </div>
                <div className="flex flex-col gap-2 w-full pt-2">
                  {STARTER_PROMPTS.map((prompt, idx) => (
                    <button
                      key={idx}
                      type="button"
                      onClick={() => handleSend(prompt)}
                      className="text-left text-xs p-2.5 rounded-xl border border-line bg-bg-soft hover:bg-black/5 dark:hover:bg-white/5 text-ink transition-colors font-medium"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((msg) => {
                const isUser = msg.role === "user";
                return (
                  <div
                    key={msg.id}
                    className={`flex flex-col ${
                      isUser ? "items-end" : "items-start"
                    } space-y-1.5`}
                  >
                    <div
                      className={`max-w-[88%] rounded-2xl px-3.5 py-2.5 text-xs whitespace-pre-wrap leading-relaxed ${
                        isUser
                          ? "bg-gradient-primary text-white rounded-br-none"
                          : "bg-bg-soft border border-line text-ink rounded-bl-none"
                      }`}
                    >
                      {msg.text}
                      {msg.isError && (
                        <div className="mt-2 pt-2 border-t border-line flex justify-end">
                          <button
                            type="button"
                            onClick={() => {
                              const lastUser = [...messages]
                                .reverse()
                                .find((m) => m.role === "user");
                              if (lastUser) {
                                handleRetry(lastUser.text);
                              }
                            }}
                            className="inline-flex items-center gap-1 text-[11px] font-semibold text-rose-600 dark:text-rose-400 hover:underline"
                          >
                            <I name="refresh" className="w-3 h-3" /> Retry
                          </button>
                        </div>
                      )}
                    </div>

                    {/* Structured Blocks (metrics, chart, notice) */}
                    {!isUser && msg.blocks && msg.blocks.length > 0 && (
                      <div className="w-full space-y-2 pt-1">
                        {msg.blocks.map((block) => (
                          <BlockRenderer key={block.id} block={block} />
                        ))}
                      </div>
                    )}
                  </div>
                );
              })
            )}

            {/* Loading Indicator */}
            {isLoading && (
              <div
                className="flex items-center gap-2 p-3 text-xs text-ink-faint rounded-2xl bg-bg-soft border border-line w-fit"
                aria-live="polite"
              >
                <div className="flex gap-1 items-center">
                  <span className="w-1.5 h-1.5 rounded-full bg-primary-500 animate-bounce" />
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-primary-500 animate-bounce"
                    style={{ animationDelay: "0.2s" }}
                  />
                  <span
                    className="w-1.5 h-1.5 rounded-full bg-primary-500 animate-bounce"
                    style={{ animationDelay: "0.4s" }}
                  />
                </div>
                <span>Analyzing data…</span>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* Input Area */}
          <div className="p-3 border-t border-line bg-card">
            <div className="flex items-end gap-2 bg-bg-soft border border-line rounded-xl px-3 py-2 focus-within:border-primary-500 transition-colors">
              <textarea
                ref={textareaRef}
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about finances or forecasts…"
                maxLength={2000}
                rows={1}
                disabled={isLoading}
                className="flex-1 bg-transparent border-none text-xs text-ink placeholder:text-ink-faint focus:outline-none resize-none max-h-24 py-1"
              />
              <button
                type="button"
                onClick={() => handleSend()}
                disabled={isLoading || !inputText.trim()}
                aria-label="Send message"
                className="p-1.5 rounded-lg bg-gradient-primary text-white disabled:opacity-40 disabled:cursor-not-allowed hover:opacity-90 transition-opacity shrink-0"
              >
                <svg
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  className="w-4 h-4"
                >
                  <line x1="22" y1="2" x2="11" y2="13" />
                  <polygon points="22 2 15 22 11 13 2 9 22 2" />
                </svg>
              </button>
            </div>
            <div className="flex justify-between items-center px-1 pt-1.5">
              <span className="text-[10px] text-ink-faint">
                Enter to send · Shift+Enter newline
              </span>
              <span className="text-[10px] text-ink-faint">
                {inputText.length}/2000
              </span>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
