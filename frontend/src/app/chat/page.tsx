"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { config } from "@/lib/config";
import styles from "./page.module.css";

interface ToolCallInfo {
  tool: string;
  args: Record<string, unknown>;
  result?: string;
}

interface Message {
  role: "user" | "assistant";
  content: string;
  toolCalls?: ToolCallInfo[];
}

interface Session {
  id: number;
  title: string;
  updated_at: string;
}

interface SessionDetail {
  id: number;
  title: string;
  messages: { id: number; role: string; content: string }[];
}

interface PdfResource {
  pdf_id: number;
  filename: string;
  status: string;
  source: "uploaded" | "fetched";
  source_url?: string | null;
}

export default function ChatPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pdfResources, setPdfResources] = useState<PdfResource[]>([]);
  const [dragOver, setDragOver] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = useCallback(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  const upsertPdfResource = useCallback((resource: PdfResource) => {
    setPdfResources((prev) => {
      const exists = prev.find((item) => item.pdf_id === resource.pdf_id);
      if (!exists) return [...prev, resource];
      return prev.map((item) =>
        item.pdf_id === resource.pdf_id ? { ...item, ...resource } : item
      );
    });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  useEffect(() => {
    loadSessions();
  }, []);

  async function loadSessions() {
    try {
      const data = await api.get<Session[]>("/chat/sessions");
      setSessions(data);
    } catch {
      /* backend may not be running */
    }
  }

  async function loadSession(sessionId: number) {
    try {
      const [detail, resources] = await Promise.all([
        api.get<SessionDetail>(`/chat/sessions/${sessionId}`),
        api.get<PdfResource[]>(`/chat/sessions/${sessionId}/pdfs`),
      ]);
      setActiveSessionId(detail.id);
      setMessages(
        detail.messages.map((m) => ({
          role: m.role as "user" | "assistant",
          content: m.content,
        }))
      );
      setPdfResources(resources);
      setError(null);
    } catch {
      setError("Failed to load session");
    }
  }

  function handleNewChat() {
    setActiveSessionId(null);
    setMessages([]);
    setPdfResources([]);
    setError(null);
    inputRef.current?.focus();
  }

  const uploadPdfFile = useCallback(
    async (file: File) => {
      if (file.type !== "application/pdf") {
        setError("Only PDF files are supported");
        return;
      }

      const formData = new FormData();
      formData.append("file", file);

      try {
        const res = await fetch(`${config.apiBaseUrl}/files/upload`, {
          method: "POST",
          body: formData,
        });
        if (!res.ok) {
          const err = await res.json().catch(() => null);
          throw new Error(err?.detail || `Error ${res.status}`);
        }
        const data = (await res.json()) as {
          pdf_id: number;
          filename: string;
          status: string;
        };
        upsertPdfResource({ ...data, source: "uploaded" });
        setError(null);
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Failed to upload PDF";
        setError(msg);
      }
    },
    [upsertPdfResource]
  );

  async function handlePdfUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    await uploadPdfFile(file);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  async function handleDeleteSession(id: number) {
    try {
      await api.delete(`/chat/sessions/${id}`);
      if (activeSessionId === id) {
        handleNewChat();
      }
      await loadSessions();
    } catch {
      /* ignore */
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || streaming) return;

    setInput("");
    setError(null);

    const userMsg: Message = { role: "user", content: text };
    const allMessages = [...messages, userMsg];
    setMessages([...allMessages, { role: "assistant", content: "" }]);
    setStreaming(true);

    try {
      const res = await fetch(`${config.apiBaseUrl}/chat/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: activeSessionId,
          messages: allMessages.map((m) => ({
            role: m.role,
            content: m.content,
          })),
          pdf_ids: pdfResources.map((p) => p.pdf_id),
          stream: true,
        }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail || `Error ${res.status}`);
      }

      const reader = res.body?.getReader();
      if (!reader) throw new Error("No stream available");

      const decoder = new TextDecoder();
      let assistantContent = "";
      const toolCalls: ToolCallInfo[] = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        const lines = chunk.split("\n");

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const payload = line.slice(6).trim();
          if (payload === "[DONE]") continue;

          try {
            const data = JSON.parse(payload);
            if (data.error) throw new Error(data.error);
            if (data.session_id && !activeSessionId) {
              setActiveSessionId(data.session_id);
            }
            if (data.tool_call) {
              toolCalls.push({ tool: data.tool_call, args: data.args || {} });
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: "",
                  toolCalls: [...toolCalls],
                };
                return updated;
              });
            }
            if (data.tool_result) {
              const last = toolCalls[toolCalls.length - 1];
              if (last && last.tool === data.tool_result) {
                last.result = data.result;
              }

              if (data.tool_result === "fetch_pdf_and_upload" && data.result) {
                try {
                  const parsed = JSON.parse(data.result) as {
                    pdf_id?: number;
                    filename?: string;
                    status?: string;
                    source_url?: string;
                  };
                  if (parsed.pdf_id && parsed.filename) {
                    upsertPdfResource({
                      pdf_id: parsed.pdf_id,
                      filename: parsed.filename,
                      status: parsed.status || "processed",
                      source: "fetched",
                      source_url: parsed.source_url,
                    });
                  }
                } catch {
                  // ignore invalid payload
                }
              }

              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: "",
                  toolCalls: [...toolCalls],
                };
                return updated;
              });
            }
            if (data.token) {
              assistantContent += data.token;
              setMessages((prev) => {
                const updated = [...prev];
                updated[updated.length - 1] = {
                  role: "assistant",
                  content: assistantContent,
                  toolCalls: toolCalls.length > 0 ? [...toolCalls] : undefined,
                };
                return updated;
              });
            }
          } catch (parseErr) {
            if (
              parseErr instanceof Error &&
              parseErr.message !== "Unexpected end of JSON input"
            ) {
              throw parseErr;
            }
          }
        }
      }

      await loadSessions();
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Something went wrong";
      setError(msg);
      setMessages((prev) => {
        if (
          prev.length > 0 &&
          prev[prev.length - 1].role === "assistant" &&
          prev[prev.length - 1].content === ""
        ) {
          return prev.slice(0, -1);
        }
        return prev;
      });
    } finally {
      setStreaming(false);
      inputRef.current?.focus();
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  }

  return (
    <div className={styles.container}>
      <aside className={styles.sessionSidebar}>
        <button className={styles.newChatBtn} onClick={handleNewChat}>
          + New Chat
        </button>
        <div className={styles.sessionList}>
          {sessions.map((s) => (
            <div
              key={s.id}
              className={`${styles.sessionItem} ${
                activeSessionId === s.id ? styles.sessionActive : ""
              }`}
            >
              <button
                className={styles.sessionBtn}
                onClick={() => loadSession(s.id)}
                title={s.title}
              >
                {s.title}
              </button>
              <button
                className={styles.sessionDeleteBtn}
                onClick={(e) => {
                  e.stopPropagation();
                  handleDeleteSession(s.id);
                }}
                title="Delete"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      </aside>

      <div
        className={`${styles.chatMain} ${dragOver ? styles.chatMainDragOver : ""}`}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setDragOver(false);
        }}
        onDrop={async (e) => {
          e.preventDefault();
          setDragOver(false);
          const file = e.dataTransfer.files?.[0];
          if (!file) return;
          await uploadPdfFile(file);
        }}
      >
        <div className={styles.header}>
          <h1 className={styles.heading}>Study Chat</h1>
        </div>

        <div className={styles.chatArea}>
          {messages.length === 0 ? (
            <div className={styles.empty}>
              <div className={styles.emptyIcon}>解</div>
              <p className={styles.emptyTitle}>Ask anything about your studies</p>
              <p className={styles.emptyHint}>
                Questions about schools, exam topics, study strategies, or past
                exam problems — I&apos;m here to help you find your own answer.
              </p>
              <div className={styles.suggestions}>
                {[
                  "东京大学情報理工学系の入試科目を教えてください",
                  "How should I prepare for math in graduate entrance exams?",
                  "帮我分析一下京都大学和东北大学信息学研究科的区别",
                ].map((s) => (
                  <button
                    key={s}
                    className={styles.suggestion}
                    onClick={() => setInput(s)}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className={styles.messages}>
              {messages.map((m, i) => (
                <div
                  key={i}
                  className={`${styles.message} ${
                    m.role === "user" ? styles.userMsg : styles.assistantMsg
                  }`}
                >
                  <div className={styles.msgAvatar}>{m.role === "user" ? "You" : "解"}</div>
                  <div className={styles.msgContent}>
                    {m.toolCalls && m.toolCalls.length > 0 && (
                      <div className={styles.toolCalls}>
                        {m.toolCalls.map((tc, j) => (
                          <div key={j} className={styles.toolCallItem}>
                            <span className={styles.toolCallIcon}>{tc.result ? "✓" : "⟳"}</span>
                            <span className={styles.toolCallName}>{tc.tool}</span>
                            {tc.args && Object.keys(tc.args).length > 0 && (
                              <span className={styles.toolCallArgs}>
                                {Object.values(tc.args).join(", ").slice(0, 80)}
                              </span>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                    {m.content || (
                      <span className={styles.thinking}>
                        {m.toolCalls && m.toolCalls.length > 0
                          ? "Processing…"
                          : "Thinking…"}
                      </span>
                    )}
                  </div>
                </div>
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>

        {error && (
          <div className={styles.errorBar}>
            {error}
            {error.includes("No active LLM provider") && (
              <a href="/settings/" className={styles.errorLink}>
                Go to Settings
              </a>
            )}
          </div>
        )}

        <form onSubmit={handleSubmit} className={styles.inputArea}>
          <input
            ref={fileInputRef}
            type="file"
            accept="application/pdf"
            className={styles.hiddenFileInput}
            onChange={handlePdfUpload}
          />
          <button
            type="button"
            className={styles.uploadBtn}
            onClick={() => fileInputRef.current?.click()}
            disabled={streaming}
          >
            Upload PDF
          </button>
          {pdfResources.length > 0 && (
            <div className={styles.pdfChipList}>
              {pdfResources.map((pdf) => (
                <div
                  key={pdf.pdf_id}
                  className={styles.pdfChip}
                  title={pdf.source_url || `${pdf.source} · ${pdf.status}`}
                >
                  <span className={styles.pdfChipName}>{pdf.filename}</span>
                  <span className={styles.pdfChipMeta}>
                    {pdf.source} · {pdf.status}
                  </span>
                  <button
                    type="button"
                    onClick={() =>
                      setPdfResources((prev) =>
                        prev.filter((item) => item.pdf_id !== pdf.pdf_id)
                      )
                    }
                  >
                    ×
                  </button>
                </div>
              ))}
            </div>
          )}
          <textarea
            ref={inputRef}
            className={styles.textarea}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type your message… (Enter to send, Shift+Enter for new line)"
            rows={1}
            disabled={streaming}
          />
          <button
            type="submit"
            className={`btn-primary ${styles.sendBtn}`}
            disabled={!input.trim() || streaming}
          >
            {streaming ? "…" : "Send"}
          </button>
        </form>
      </div>
    </div>
  );
}
