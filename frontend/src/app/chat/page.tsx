"use client";

import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { config } from "@/lib/config";
import styles from "./page.module.css";

interface StoredMessage {
  id?: number;
  role: "user" | "assistant";
  content: string;
  createdAt?: string;
}

interface RunEventPayload {
  sequence: number;
  type: string;
  status?: string;
  label?: string;
  detail?: string;
  run_id?: number;
  tool_call_id?: string;
  tool_name?: string;
  tool_display_name?: string;
  tool_activity_label?: string;
  args?: Record<string, unknown>;
  success?: boolean;
  error_message?: string;
  assistant_message_id?: number;
  delta?: string;
  content?: string;
  message?: string;
  resource?: {
    pdf_id?: number;
    filename?: string | null;
    status?: string | null;
    source_url?: string | null;
  };
}

interface RunEvent {
  id?: number;
  eventType?: string;
  createdAt?: string;
  payload: RunEventPayload;
}

interface RunRecord {
  id: number | string;
  assistantMessageId?: number | null;
  status: string;
  createdAt?: string;
  updatedAt?: string;
  events: RunEvent[];
}

interface Session {
  id: number;
  title: string;
  updated_at: string;
}

interface SessionDetail {
  id: number;
  title: string;
  messages: { id: number; role: string; content: string; created_at: string }[];
  runs: {
    id: number;
    assistant_message_id: number | null;
    status: string;
    created_at: string;
    updated_at: string;
    events: {
      id: number;
      sequence: number;
      event_type: string;
      created_at: string;
      payload: RunEventPayload;
    }[];
  }[];
}

interface PdfResource {
  pdf_id: number;
  filename: string;
  status: string;
  source: "uploaded" | "fetched";
  source_url?: string | null;
}

interface ToolStep {
  id: string;
  name: string;
  activity: string;
  args: Record<string, unknown>;
  success?: boolean;
  errorMessage?: string;
  finished: boolean;
}

function normalizeRunEvent(payload: RunEventPayload): RunEventPayload {
  return {
    ...payload,
    sequence: payload.sequence ?? 0,
    type: payload.type ?? "unknown",
  };
}

function hydrateRun(detailRun: SessionDetail["runs"][number]): RunRecord {
  return {
    id: detailRun.id,
    assistantMessageId: detailRun.assistant_message_id,
    status: detailRun.status,
    createdAt: detailRun.created_at,
    updatedAt: detailRun.updated_at,
    events: detailRun.events.map((event) => ({
      id: event.id,
      eventType: event.event_type,
      createdAt: event.created_at,
      payload: normalizeRunEvent(event.payload),
    })),
  };
}

function formatArgs(args?: Record<string, unknown>): string {
  if (!args) return "";
  const pairs = Object.entries(args)
    .filter(([, value]) => value !== undefined && value !== null && value !== "")
    .map(([key, value]) => {
      const text = Array.isArray(value) ? value.join(", ") : String(value);
      return `${key}: ${text}`;
    });
  return pairs.join(" · ");
}

function getToolSteps(events: RunEvent[]): ToolStep[] {
  const ordered: ToolStep[] = [];
  const byId = new Map<string, ToolStep>();

  for (const event of events) {
    const payload = event.payload;
    if (payload.type !== "tool.started" && payload.type !== "tool.finished") {
      continue;
    }

    const id = payload.tool_call_id || `event-${payload.sequence}`;
    let step = byId.get(id);
    if (!step) {
      step = {
        id,
        name: payload.tool_display_name || payload.tool_name || "Tool",
        activity:
          payload.tool_activity_label ||
          payload.tool_display_name ||
          payload.tool_name ||
          "Working",
        args: payload.args || {},
        finished: false,
      };
      byId.set(id, step);
      ordered.push(step);
    }

    if (payload.args) {
      step.args = payload.args;
    }
    if (payload.tool_display_name || payload.tool_name) {
      step.name = payload.tool_display_name || payload.tool_name || step.name;
    }
    if (payload.tool_activity_label) {
      step.activity = payload.tool_activity_label;
    }
    if (payload.type === "tool.finished") {
      step.finished = true;
      step.success = payload.success;
      step.errorMessage = payload.error_message;
    }
  }

  return ordered;
}

function getRunHeadline(run: RunRecord): string {
  const lastEvent = [...run.events].reverse().find((event) => event.payload.type === "status");
  const steps = getToolSteps(run.events);
  const activeStep = [...steps].reverse().find((step) => !step.finished);

  if (run.status === "failed") return "Run failed";
  if (activeStep) return activeStep.activity;
  if (run.status === "completed") {
    return steps.length > 0
      ? `${steps.length} tool${steps.length > 1 ? "s" : ""} completed`
      : "Completed";
  }
  if (lastEvent?.payload.label) return lastEvent.payload.label;
  return "Working";
}

function RunCard({ run, live = false }: { run: RunRecord; live?: boolean }) {
  const [expanded, setExpanded] = useState(false);
  const steps = getToolSteps(run.events);
  const headline = getRunHeadline(run);
  const latestStep = steps[steps.length - 1];

  return (
    <div className={`${styles.runCard} ${live ? styles.runCardLive : ""}`}>
      <button
        type="button"
        className={styles.runHeader}
        onClick={() => setExpanded((prev) => !prev)}
        aria-expanded={expanded}
      >
        <span className={styles.runTitleWrap}>
          <span className={styles.runTitle}>{headline}</span>
          <span className={styles.runMeta}>
            {steps.length > 0
              ? `${steps.length} tool${steps.length > 1 ? "s" : ""}`
              : live
                ? "waiting"
                : "no tools"}
            {latestStep ? ` · latest: ${latestStep.name}` : ""}
          </span>
        </span>
        <span className={styles.runHeaderRight}>
          <span className={styles.runState}>{run.status}</span>
          <span className={styles.runToggle}>{expanded ? "Hide" : "Show"}</span>
        </span>
      </button>
      {expanded && steps.length > 0 && (
        <div className={styles.runSteps}>
          {steps.map((step) => (
            <div key={step.id} className={styles.runStep}>
              <div className={styles.runStepTop}>
                <span className={styles.runStepIcon}>
                  {step.finished ? (step.success === false ? "!" : "✓") : "⟳"}
                </span>
                <span className={styles.runStepName}>{step.name}</span>
              </div>
              {formatArgs(step.args) && (
                <div className={styles.runStepArgs}>{formatArgs(step.args)}</div>
              )}
              {step.success === false && step.errorMessage && (
                <div className={styles.runStepError}>{step.errorMessage}</div>
              )}
            </div>
          ))}
        </div>
      )}
      {expanded && steps.length === 0 && (
        <div className={styles.runEmpty}>
          {live ? "Waiting for the first tool call…" : "No tool calls recorded."}
        </div>
      )}
    </div>
  );
}

export default function ChatPage() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null);
  const [messages, setMessages] = useState<StoredMessage[]>([]);
  const [runs, setRuns] = useState<RunRecord[]>([]);
  const [streamingRun, setStreamingRun] = useState<RunRecord | null>(null);
  const [streamingAssistant, setStreamingAssistant] = useState("");
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

  const applyRunEvent = useCallback(
    (payload: RunEventPayload) => {
      const event = { payload: normalizeRunEvent(payload) };

      setStreamingRun((prev) => {
        const runId = payload.run_id ?? (typeof prev?.id === "number" ? prev.id : prev?.id);
        const base: RunRecord = prev || {
          id: runId || `pending-${Date.now()}`,
          status: payload.status || "running",
          events: [],
        };

        let nextStatus = base.status;
        if (payload.type === "run.started") nextStatus = payload.status || "running";
        if (payload.type === "status" && payload.status) nextStatus = payload.status;
        if (payload.type === "run.completed") nextStatus = payload.status || "completed";
        if (payload.type === "error") nextStatus = "failed";

        return {
          ...base,
          id: runId || base.id,
          status: nextStatus,
          assistantMessageId: payload.assistant_message_id ?? base.assistantMessageId,
          events: [...base.events, event],
        };
      });

      if (payload.resource?.pdf_id && payload.resource.filename) {
        upsertPdfResource({
          pdf_id: payload.resource.pdf_id,
          filename: payload.resource.filename,
          status: payload.resource.status || "processed",
          source: "fetched",
          source_url: payload.resource.source_url,
        });
      }
    },
    [upsertPdfResource]
  );

  useEffect(() => {
    scrollToBottom();
  }, [messages, runs, streamingRun, streamingAssistant, scrollToBottom]);

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
        detail.messages.map((message) => ({
          id: message.id,
          role: message.role as "user" | "assistant",
          content: message.content,
          createdAt: message.created_at,
        }))
      );
      setRuns(detail.runs.map(hydrateRun));
      setStreamingRun(null);
      setStreamingAssistant("");
      setPdfResources(resources);
      setError(null);
    } catch {
      setError("Failed to load session");
    }
  }

  function handleNewChat() {
    setActiveSessionId(null);
    setMessages([]);
    setRuns([]);
    setStreamingRun(null);
    setStreamingAssistant("");
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

    const userMsg: StoredMessage = { role: "user", content: text };
    const allMessages = [...messages, userMsg];
    setMessages(allMessages);
    setStreamingRun({ id: `pending-${Date.now()}`, status: "thinking", events: [] });
    setStreamingAssistant("");
    setStreaming(true);

    let streamedSessionId = activeSessionId;

    try {
      const res = await fetch(`${config.apiBaseUrl}/chat/`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: activeSessionId,
          messages: allMessages.map((message) => ({
            role: message.role,
            content: message.content,
          })),
          pdf_ids: pdfResources.map((pdf) => pdf.pdf_id),
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
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const eventBlocks = buffer.split("\n\n");
        buffer = eventBlocks.pop() || "";

        for (const block of eventBlocks) {
          const payload = block
            .split("\n")
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trimStart())
            .join("\n")
            .trim();

          if (!payload || payload === "[DONE]") continue;

          const data = JSON.parse(payload) as RunEventPayload & { session_id?: number; error?: string };
          if (data.error) throw new Error(data.error);

          if (data.session_id) {
            streamedSessionId = data.session_id;
            setActiveSessionId(data.session_id);
            continue;
          }

          if (data.type === "answer.delta") {
            setStreamingAssistant((prev) => prev + (data.delta || ""));
            continue;
          }

          if (data.type === "answer.completed") {
            setStreamingAssistant(data.content || "");
            continue;
          }

          if (data.type === "error") {
            setError(data.message || "Something went wrong");
          }

          applyRunEvent(data);
        }
      }

      if (buffer.trim()) {
        const payload = buffer
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart())
          .join("\n")
          .trim();
        if (payload && payload !== "[DONE]") {
          const data = JSON.parse(payload) as RunEventPayload & {
            session_id?: number;
            error?: string;
          };
          if (data.type === "answer.completed") {
            setStreamingAssistant(data.content || "");
          } else if (data.type === "error") {
            setError(data.message || "Something went wrong");
            applyRunEvent(data);
          } else if (!data.session_id) {
            applyRunEvent(data);
          }
        }
      }

      if (streamedSessionId) {
        await loadSession(streamedSessionId);
      } else {
        await loadSessions();
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : "Something went wrong";
      setError(msg);
      setStreamingRun((prev) =>
        prev
          ? {
              ...prev,
              status: "failed",
              events: [
                ...prev.events,
                {
                  payload: {
                    sequence: prev.events.length + 1,
                    type: "error",
                    message: msg,
                  },
                },
              ],
            }
          : null
      );
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

  const runsByAssistantMessageId = new Map<number, RunRecord>();
  const orphanRuns: RunRecord[] = [];
  for (const run of runs) {
    if (run.assistantMessageId) {
      runsByAssistantMessageId.set(run.assistantMessageId, run);
    } else {
      orphanRuns.push(run);
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
                onClick={(event) => {
                  event.stopPropagation();
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
        onDragOver={(event) => {
          event.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={(event) => {
          event.preventDefault();
          setDragOver(false);
        }}
        onDrop={async (event) => {
          event.preventDefault();
          setDragOver(false);
          const file = event.dataTransfer.files?.[0];
          if (!file) return;
          await uploadPdfFile(file);
        }}
      >
        <div className={styles.header}>
          <h1 className={styles.heading}>Study Chat</h1>
        </div>

        <div className={styles.chatArea}>
          {messages.length === 0 && !streamingRun && !streamingAssistant ? (
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
                ].map((suggestion) => (
                  <button
                    key={suggestion}
                    className={styles.suggestion}
                    onClick={() => setInput(suggestion)}
                  >
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            <div className={styles.messages}>
              {messages.map((message, index) => {
                const run = message.id ? runsByAssistantMessageId.get(message.id) : undefined;
                return (
                  <Fragment key={message.id || `local-${index}`}>
                    {message.role === "assistant" && run && <RunCard run={run} />}
                    <div
                      className={`${styles.message} ${
                        message.role === "user" ? styles.userMsg : styles.assistantMsg
                      }`}
                    >
                      <div className={styles.msgAvatar}>
                        {message.role === "user" ? "You" : "解"}
                      </div>
                      <div className={styles.msgContent}>
                        {message.content || (
                          <span className={styles.thinking}>Thinking…</span>
                        )}
                      </div>
                    </div>
                  </Fragment>
                );
              })}

              {orphanRuns.map((run) => (
                <Fragment key={`orphan-run-${run.id}`}>
                  <RunCard run={run} />
                </Fragment>
              ))}

              {streamingRun && <RunCard run={streamingRun} live />}

              {(streaming || streamingAssistant) && (
                <div className={`${styles.message} ${styles.assistantMsg}`}>
                  <div className={styles.msgAvatar}>解</div>
                  <div className={styles.msgContent}>
                    {streamingAssistant || (
                      <span className={styles.thinking}>
                        {streamingRun ? "Processing…" : "Thinking…"}
                      </span>
                    )}
                  </div>
                </div>
              )}

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
            onChange={(event) => setInput(event.target.value)}
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
