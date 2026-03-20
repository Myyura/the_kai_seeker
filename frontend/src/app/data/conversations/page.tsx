"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import styles from "../page.module.css";

interface AdminConversationListItem {
  id: number;
  title: string;
  message_count: number;
  run_count: number;
  pdf_count: number;
  created_at: string;
  updated_at: string;
}

interface AdminConversationListResponse {
  items: AdminConversationListItem[];
  count: number;
}

interface AdminConversationMessage {
  id: number;
  role: string;
  content: string;
  model?: string | null;
  created_at: string;
}

interface AdminConversationRunEvent {
  id: number;
  sequence: number;
  event_type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

interface AdminConversationRun {
  id: number;
  assistant_message_id?: number | null;
  status: string;
  event_count: number;
  latest_event_type?: string | null;
  created_at: string;
  updated_at: string;
  events: AdminConversationRunEvent[];
}

interface AdminConversationPdf {
  pdf_id: number;
  filename: string;
  status: string;
  source: string;
  source_url?: string | null;
}

interface AdminConversationDetail {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  messages: AdminConversationMessage[];
  runs: AdminConversationRun[];
  pdf_resources: AdminConversationPdf[];
  state: Record<string, unknown>;
}

type ConversationTab = "overview" | "state" | "timeline" | "messages";

const CONVERSATION_TABS: { id: ConversationTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "state", label: "State" },
  { id: "timeline", label: "Timeline" },
  { id: "messages", label: "Messages" },
];

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

function statusClass(status: string): string {
  if (status === "running") return styles.statusProcessing;
  if (status === "failed") return styles.statusUploaded;
  return styles.statusProcessed;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringifyJson(value: unknown): string {
  return JSON.stringify(value, null, 2) ?? "";
}

function previewText(value: string, limit = 280): string {
  const text = value.trim();
  if (text.length <= limit) return text;
  return `${text.slice(0, limit)}...`;
}

function asString(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return "";
}

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.filter((item): item is string => typeof item === "string" && item.trim().length > 0);
}

function asRecordList(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value.filter(isRecord);
}

function summarizeRecordTitle(record: Record<string, unknown>, fallback: string): string {
  const titleKeys = [
    "label",
    "title",
    "url",
    "filename",
    "query",
    "key",
    "user_request",
    "source_url",
  ];
  for (const key of titleKeys) {
    const value = asString(record[key]);
    if (value) return value;
  }
  return fallback;
}

function summarizeRecordMeta(record: Record<string, unknown>): string {
  const metaKeys = [
    "status",
    "category",
    "source",
    "school_id",
    "program_id",
    "pdf_id",
    "page_number",
    "tool_name",
  ];
  const items = metaKeys
    .map((key) => {
      const value = record[key];
      if (typeof value === "string" && value.trim()) return `${key}: ${value}`;
      if (typeof value === "number" || typeof value === "boolean") return `${key}: ${value}`;
      return "";
    })
    .filter(Boolean);
  return items.join(" | ");
}

function summarizeRecordBody(record: Record<string, unknown>): string {
  const bodyKeys = [
    "summary",
    "assistant_summary",
    "value",
    "content_preview",
    "note",
    "description",
    "question",
  ];
  for (const key of bodyKeys) {
    const value = asString(record[key]);
    if (value) return previewText(value);
  }
  return previewText(stringifyJson(record), 320);
}

function eventLabel(event: AdminConversationRunEvent): string {
  const toolDisplayName = asString(event.payload.tool_display_name);
  const toolName = asString(event.payload.tool_name);
  if (toolDisplayName) return `${event.event_type} · ${toolDisplayName}`;
  if (toolName) return `${event.event_type} · ${toolName}`;
  return event.event_type;
}

function eventSummary(event: AdminConversationRunEvent): string {
  const summaryKeys = [
    "detail",
    "message",
    "tool_result_preview",
    "content",
    "delta",
    "error_message",
  ];
  for (const key of summaryKeys) {
    const value = asString(event.payload[key]);
    if (value) return previewText(value);
  }
  return "";
}

function sessionRunLabel(index: number): string {
  return `Run ${index + 1}`;
}

export default function DataConversationsPage() {
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [sessions, setSessions] = useState<AdminConversationListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);
  const [detail, setDetail] = useState<AdminConversationDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<ConversationTab>("overview");
  const [error, setError] = useState<string | null>(null);
  const [mutating, setMutating] = useState(false);

  useEffect(() => {
    void loadSessions();
  }, [query]);

  useEffect(() => {
    if (selectedSessionId == null) {
      setDetail(null);
      return;
    }
    void loadDetail(selectedSessionId);
  }, [selectedSessionId]);

  const selectedListItem = useMemo(
    () => sessions.find((item) => item.id === selectedSessionId) ?? null,
    [sessions, selectedSessionId]
  );

  const stateGoal: Record<string, unknown> = isRecord(detail?.state?.goal)
    ? detail.state.goal
    : {};
  const stateProgress: Record<string, unknown> = isRecord(detail?.state?.progress)
    ? detail.state.progress
    : {};
  const stateArtifacts: Record<string, unknown> = isRecord(detail?.state?.artifacts)
    ? detail.state.artifacts
    : {};

  async function loadSessions(preferredId?: number | null) {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (query) params.set("query", query);
      params.set("limit", "100");
      const suffix = params.toString() ? `?${params.toString()}` : "";
      const data = await api.get<AdminConversationListResponse>(
        `/admin/conversations${suffix}`
      );
      setSessions(data.items);
      setSelectedSessionId((current) => {
        const candidate = preferredId ?? current;
        if (candidate && data.items.some((item) => item.id === candidate)) {
          return candidate;
        }
        return data.items[0]?.id ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load conversations");
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(sessionId: number) {
    setDetailLoading(true);
    setError(null);
    try {
      const data = await api.get<AdminConversationDetail>(
        `/admin/conversations/${sessionId}`
      );
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load conversation detail");
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleRefresh() {
    await loadSessions(selectedSessionId);
  }

  async function handleDelete() {
    if (selectedSessionId == null || !selectedListItem) return;
    const confirmed = window.confirm(
      `Delete conversation "${selectedListItem.title}" and all of its messages, runs, and attached references?`
    );
    if (!confirmed) return;

    setMutating(true);
    setError(null);
    try {
      await api.delete(`/admin/conversations/${selectedSessionId}`);
      setDetail(null);
      await loadSessions(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete conversation");
    } finally {
      setMutating(false);
    }
  }

  function handleFilterSubmit(event: React.FormEvent) {
    event.preventDefault();
    setQuery(queryInput.trim());
  }

  function renderStringListSection(title: string, items: string[], emptyText: string) {
    return (
      <div className={styles.detailSection}>
        <div className={styles.detailSectionTitle}>{title}</div>
        {items.length === 0 ? (
          <div className={styles.emptyState}>{emptyText}</div>
        ) : (
          <div className={styles.referenceList}>
            {items.map((item, index) => (
              <div key={`${title}-${index}`} className={styles.referenceItem}>
                <div className={styles.referenceBody}>{item}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  function renderRecordListSection(
    title: string,
    items: Record<string, unknown>[],
    emptyText: string
  ) {
    return (
      <div className={styles.detailSection}>
        <div className={styles.detailSectionTitle}>{title}</div>
        {items.length === 0 ? (
          <div className={styles.emptyState}>{emptyText}</div>
        ) : (
          <div className={styles.referenceList}>
            {items.map((item, index) => (
              <div key={`${title}-${index}`} className={styles.referenceItem}>
                <div className={styles.referenceTitle}>
                  {summarizeRecordTitle(item, `${title} ${index + 1}`)}
                </div>
                {summarizeRecordMeta(item) && (
                  <div className={styles.referenceMeta}>{summarizeRecordMeta(item)}</div>
                )}
                <div className={styles.referenceBody}>{summarizeRecordBody(item)}</div>
                <details className={styles.rawDetails}>
                  <summary className={styles.rawSummary}>View raw record</summary>
                  <pre className={styles.rawPre}>{stringifyJson(item)}</pre>
                </details>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  function renderOverviewTab() {
    if (!detail) return null;
    const latestRun = detail.runs[detail.runs.length - 1] ?? null;

    return (
      <div className={styles.tabPanel}>
        <div className={styles.summaryGrid}>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Messages</div>
            <div className={styles.summaryValue}>{detail.messages.length}</div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Runs</div>
            <div className={styles.summaryValue}>{detail.runs.length}</div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Run Events</div>
            <div className={styles.summaryValue}>
              {detail.runs.reduce((total, run) => total + run.event_count, 0)}
            </div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Attached PDFs</div>
            <div className={styles.summaryValue}>{detail.pdf_resources.length}</div>
          </div>
        </div>

        <div className={styles.detailSection}>
          <div className={styles.detailSectionTitle}>Quick Session Summary</div>
          <div className={styles.detailMeta}>
            <div className={styles.detailMetaRow}>
              <span className={styles.detailMetaLabel}>Core need:</span>{" "}
              {asString(stateGoal.core_user_need) || "Not captured"}
            </div>
            <div className={styles.detailMetaRow}>
              <span className={styles.detailMetaLabel}>Current focus:</span>{" "}
              {asString(stateGoal.current_focus) || "Not captured"}
            </div>
            <div className={styles.detailMetaRow}>
              <span className={styles.detailMetaLabel}>Last assistant summary:</span>{" "}
              {asString(stateProgress.last_assistant_summary) || "Not captured"}
            </div>
            <div className={styles.detailMetaRow}>
              <span className={styles.detailMetaLabel}>Pending actions:</span>{" "}
              {asStringList(stateProgress.pending_actions).length}
            </div>
            <div className={styles.detailMetaRow}>
              <span className={styles.detailMetaLabel}>Open questions:</span>{" "}
              {asStringList(stateProgress.open_questions).length}
            </div>
            <div className={styles.detailMetaRow}>
              <span className={styles.detailMetaLabel}>Latest run:</span>{" "}
              {latestRun
                ? `${sessionRunLabel(detail.runs.length - 1)} · DB #${latestRun.id} · ${latestRun.status}`
                : "No runs yet"}
            </div>
          </div>
        </div>

        <div className={styles.detailSection}>
          <div className={styles.detailSectionTitle}>Attached PDFs</div>
          {detail.pdf_resources.length === 0 ? (
            <div className={styles.emptyState}>No PDFs attached to this session.</div>
          ) : (
            <div className={styles.referenceList}>
              {detail.pdf_resources.map((resource) => (
                <div key={resource.pdf_id} className={styles.referenceItem}>
                  <div className={styles.referenceTitle}>{resource.filename}</div>
                  <div className={styles.referenceMeta}>
                    PDF #{resource.pdf_id} | {resource.source} | {resource.status}
                  </div>
                  {resource.source_url && (
                    <div className={styles.referenceBody}>{resource.source_url}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className={styles.detailSection}>
          <div className={styles.detailSectionTitle}>Runs</div>
          {detail.runs.length === 0 ? (
            <div className={styles.emptyState}>No runs stored.</div>
          ) : (
            <div className={styles.runList}>
              {detail.runs.map((run, index) => (
                <div key={run.id} className={styles.runItem}>
                  <div className={styles.runHeader}>
                    <span className={styles.runTitle}>
                      {sessionRunLabel(index)}
                    </span>
                    <span className={`${styles.statusBadge} ${statusClass(run.status)}`}>
                      {run.status}
                    </span>
                  </div>
                  <div className={styles.runMeta}>
                    <span>DB #{run.id}</span>
                    <span>{run.event_count} events</span>
                    <span>
                      assistant message{" "}
                      {run.assistant_message_id ? `#${run.assistant_message_id}` : "none"}
                    </span>
                    <span>
                      latest {run.latest_event_type ? run.latest_event_type : "no events"}
                    </span>
                    <span>updated {formatDate(run.updated_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  function renderStateTab() {
    if (!detail) return null;

    return (
      <div className={styles.tabPanel}>
        <div className={styles.summaryGrid}>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Recent Requests</div>
            <div className={styles.summaryValue}>
              {asStringList(stateGoal.recent_user_requests).length}
            </div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Completed Work</div>
            <div className={styles.summaryValue}>
              {asStringList(stateProgress.completed_work).length}
            </div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Artifacts</div>
            <div className={styles.summaryValue}>
              {asRecordList(stateArtifacts.sources).length +
                asRecordList(stateArtifacts.visited_pages).length +
                asRecordList(stateArtifacts.pdfs).length}
            </div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Recent Turns</div>
            <div className={styles.summaryValue}>
              {asRecordList(stateProgress.recent_turns).length}
            </div>
          </div>
        </div>

        <div className={styles.stateGrid}>
          <div className={styles.detailSection}>
            <div className={styles.detailSectionTitle}>Core User Need</div>
            <div className={styles.detailBox}>
              {asString(stateGoal.core_user_need) || "No core need recorded."}
            </div>
          </div>
          <div className={styles.detailSection}>
            <div className={styles.detailSectionTitle}>Current Focus</div>
            <div className={styles.detailBox}>
              {asString(stateGoal.current_focus) || "No current focus recorded."}
            </div>
          </div>
        </div>

        {renderStringListSection(
          "Recent User Requests",
          asStringList(stateGoal.recent_user_requests),
          "No recent requests recorded."
        )}
        {renderStringListSection(
          "Completed Work",
          asStringList(stateProgress.completed_work),
          "No completed work recorded."
        )}
        {renderStringListSection(
          "Pending Actions",
          asStringList(stateProgress.pending_actions),
          "No pending actions recorded."
        )}
        {renderStringListSection(
          "Open Questions",
          asStringList(stateProgress.open_questions),
          "No open questions recorded."
        )}

        <div className={styles.detailSection}>
          <div className={styles.detailSectionTitle}>Last Assistant Summary</div>
          <div className={styles.detailBox}>
            {asString(stateProgress.last_assistant_summary) || "No assistant summary recorded."}
          </div>
        </div>

        {renderRecordListSection(
          "Recent Turns",
          asRecordList(stateProgress.recent_turns),
          "No turns recorded."
        )}
        {renderRecordListSection(
          "Sources",
          asRecordList(stateArtifacts.sources),
          "No sources recorded."
        )}
        {renderRecordListSection(
          "Visited Pages",
          asRecordList(stateArtifacts.visited_pages),
          "No visited pages recorded."
        )}
        {renderRecordListSection(
          "PDFs",
          asRecordList(stateArtifacts.pdfs),
          "No PDFs recorded."
        )}
        {renderRecordListSection(
          "School Searches",
          asRecordList(stateArtifacts.school_searches),
          "No school searches recorded."
        )}
        {renderRecordListSection(
          "Question Searches",
          asRecordList(stateArtifacts.question_searches),
          "No question searches recorded."
        )}
        {renderRecordListSection(
          "Fetched Questions",
          asRecordList(stateArtifacts.fetched_questions),
          "No fetched questions recorded."
        )}
        {renderRecordListSection(
          "PDF Queries",
          asRecordList(stateArtifacts.pdf_queries),
          "No PDF queries recorded."
        )}
        {renderRecordListSection(
          "Notes",
          asRecordList(stateArtifacts.notes),
          "No notes recorded."
        )}

        <details className={styles.rawDetails}>
          <summary className={styles.rawSummary}>View raw session state JSON</summary>
          <pre className={styles.rawPre}>{stringifyJson(detail.state)}</pre>
        </details>
      </div>
    );
  }

  function renderTimelineTab() {
    if (!detail) return null;

    return (
      <div className={styles.tabPanel}>
        {detail.runs.length === 0 ? (
          <div className={styles.emptyState}>No runs stored.</div>
        ) : (
          <div className={styles.runList}>
            {detail.runs.map((run, index) => (
              <div key={run.id} className={styles.runItem}>
                <div className={styles.runHeader}>
                  <span className={styles.runTitle}>{sessionRunLabel(index)}</span>
                  <span className={`${styles.statusBadge} ${statusClass(run.status)}`}>
                    {run.status}
                  </span>
                </div>
                <div className={styles.runMeta}>
                  <span>DB #{run.id}</span>
                  <span>{run.event_count} events</span>
                  <span>created {formatDate(run.created_at)}</span>
                  <span>updated {formatDate(run.updated_at)}</span>
                </div>

                {run.events.length === 0 ? (
                  <div className={styles.emptyState}>No events recorded for this run.</div>
                ) : (
                  <div className={styles.eventList}>
                    {run.events.map((event) => (
                      <div key={event.id} className={styles.eventItem}>
                        <div className={styles.eventHeader}>
                          <div className={styles.eventTitle}>{eventLabel(event)}</div>
                          <div className={styles.eventMeta}>
                            seq {event.sequence} | {formatDate(event.created_at)}
                          </div>
                        </div>

                        {eventSummary(event) && (
                          <div className={styles.eventBody}>{eventSummary(event)}</div>
                        )}

                        {isRecord(event.payload.args) && (
                          <div className={styles.eventSubsection}>
                            <div className={styles.eventSubsectionLabel}>Args</div>
                            <pre className={styles.rawPre}>
                              {stringifyJson(event.payload.args)}
                            </pre>
                          </div>
                        )}

                        {isRecord(event.payload.resource) && (
                          <div className={styles.eventSubsection}>
                            <div className={styles.eventSubsectionLabel}>Resource</div>
                            <pre className={styles.rawPre}>
                              {stringifyJson(event.payload.resource)}
                            </pre>
                          </div>
                        )}

                        <details className={styles.rawDetails}>
                          <summary className={styles.rawSummary}>View raw payload</summary>
                          <pre className={styles.rawPre}>{stringifyJson(event.payload)}</pre>
                        </details>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  function renderMessagesTab() {
    if (!detail) return null;

    return (
      <div className={styles.tabPanel}>
        <div className={styles.detailSection}>
          <div className={styles.detailSectionTitle}>Messages ({detail.messages.length})</div>
          {detail.messages.length === 0 ? (
            <div className={styles.emptyState}>No messages stored.</div>
          ) : (
            <div className={styles.messageList}>
              {detail.messages.map((message) => (
                <div key={message.id} className={styles.messageItem}>
                  <div className={styles.messageHeader}>
                    <span className={styles.messageRole}>{message.role}</span>
                    <span className={styles.messageMeta}>
                      #{message.id} | {formatDate(message.created_at)}
                      {message.model ? ` | ${message.model}` : ""}
                    </span>
                  </div>
                  <div className={styles.messageBody}>{message.content}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  function renderActiveTab() {
    if (activeTab === "state") return renderStateTab();
    if (activeTab === "timeline") return renderTimelineTab();
    if (activeTab === "messages") return renderMessagesTab();
    return renderOverviewTab();
  }

  return (
    <div className={styles.container}>
      <div className={styles.pageIntro}>
        <h2 className={styles.pageTitle}>Conversations</h2>
        <p className={styles.description}>
          Inspect stored chat sessions, session state, and tool timelines so this page can work as
          both a cleanup surface and a debugging console.
        </p>
      </div>

      <form className={styles.toolbar} onSubmit={handleFilterSubmit}>
        <div className={styles.toolbarGroup}>
          <input
            className={styles.searchInput}
            type="search"
            placeholder="Search by session title"
            value={queryInput}
            onChange={(event) => setQueryInput(event.target.value)}
          />
        </div>
        <div className={styles.toolbarGroup}>
          <button type="submit" className={styles.btnSmall}>
            Apply Filters
          </button>
          <button type="button" className={styles.btnSmall} onClick={handleRefresh}>
            Refresh
          </button>
        </div>
      </form>

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.conversationLayout}>
        <div className={`glass-card ${styles.listCard}`}>
          <div className={styles.listHeader}>
            <h3 className={styles.listTitle}>Sessions</h3>
            <span className={styles.listCount}>
              {loading ? "Loading..." : `${sessions.length} item${sessions.length === 1 ? "" : "s"}`}
            </span>
          </div>

          {loading ? (
            <p className={styles.muted}>Loading conversations...</p>
          ) : sessions.length === 0 ? (
            <div className={styles.emptyState}>No conversations match the current filters.</div>
          ) : (
            <div className={styles.pdfList}>
              {sessions.map((session) => (
                <button
                  key={session.id}
                  type="button"
                  className={`${styles.pdfItem} ${
                    selectedSessionId === session.id ? styles.pdfItemActive : ""
                  }`}
                  onClick={() => setSelectedSessionId(session.id)}
                >
                  <div className={styles.pdfItemTop}>
                    <div className={styles.pdfName}>{session.title}</div>
                  </div>
                  <div className={styles.pdfMeta}>
                    <span>ID {session.id}</span>
                    <span>{session.message_count} messages</span>
                    <span>{session.run_count} runs</span>
                    <span>{session.pdf_count} PDFs</span>
                    <span>updated {formatDate(session.updated_at)}</span>
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className={`glass-card ${styles.detailCard}`}>
          <div className={styles.listHeader}>
            <h3 className={styles.detailTitle}>Conversation Inspector</h3>
            {selectedListItem && (
              <span className={styles.listCount}>Session #{selectedListItem.id}</span>
            )}
          </div>

          {selectedSessionId == null ? (
            <div className={styles.emptyState}>Select a conversation to inspect it.</div>
          ) : detailLoading && !detail ? (
            <p className={styles.muted}>Loading detail...</p>
          ) : detail ? (
            <>
              <div className={styles.detailActions}>
                <button
                  type="button"
                  className={`${styles.btnSmall} ${styles.btnDanger}`}
                  onClick={handleDelete}
                  disabled={mutating}
                >
                  {mutating ? "Deleting..." : "Delete Conversation"}
                </button>
              </div>

              <div className={styles.detailMeta}>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>Title:</span> {detail.title}
                </div>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>Created:</span>{" "}
                  {formatDate(detail.created_at)}
                </div>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>Updated:</span>{" "}
                  {formatDate(detail.updated_at)}
                </div>
                {detailLoading && <div className={styles.muted}>Refreshing detail...</div>}
              </div>

              <div className={styles.tabBar}>
                {CONVERSATION_TABS.map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    className={`${styles.tabButton} ${
                      activeTab === tab.id ? styles.tabButtonActive : ""
                    }`}
                    onClick={() => setActiveTab(tab.id)}
                  >
                    {tab.label}
                  </button>
                ))}
              </div>

              {renderActiveTab()}
            </>
          ) : (
            <div className={styles.emptyState}>Unable to load the selected conversation.</div>
          )}
        </div>
      </div>
    </div>
  );
}
