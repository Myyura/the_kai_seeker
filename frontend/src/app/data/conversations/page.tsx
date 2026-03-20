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

interface AdminConversationRun {
  id: number;
  assistant_message_id?: number | null;
  status: string;
  event_count: number;
  latest_event_type?: string | null;
  created_at: string;
  updated_at: string;
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
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

function statusClass(status: string): string {
  if (status === "running") return styles.statusProcessing;
  if (status === "failed") return styles.statusUploaded;
  return styles.statusProcessed;
}

export default function DataConversationsPage() {
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [sessions, setSessions] = useState<AdminConversationListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);
  const [detail, setDetail] = useState<AdminConversationDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
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

  return (
    <div className={styles.container}>
      <div className={styles.pageIntro}>
        <h2 className={styles.pageTitle}>Conversations</h2>
        <p className={styles.description}>
          Inspect stored chat sessions and delete whole sessions when you want to
          clear accumulated history.
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

      <div className={styles.pdfLayout}>
        <div className={`glass-card ${styles.listCard}`}>
          <div className={styles.listHeader}>
            <h3 className={styles.listTitle}>Sessions</h3>
            <span className={styles.listCount}>
              {loading ? "Loading…" : `${sessions.length} item${sessions.length === 1 ? "" : "s"}`}
            </span>
          </div>

          {loading ? (
            <p className={styles.muted}>Loading conversations…</p>
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
            <h3 className={styles.detailTitle}>Detail</h3>
            {selectedListItem && (
              <span className={styles.listCount}>Session #{selectedListItem.id}</span>
            )}
          </div>

          {selectedSessionId == null ? (
            <div className={styles.emptyState}>Select a conversation to inspect it.</div>
          ) : detailLoading && !detail ? (
            <p className={styles.muted}>Loading detail…</p>
          ) : detail ? (
            <>
              <div className={styles.detailActions}>
                <button
                  type="button"
                  className={`${styles.btnSmall} ${styles.btnDanger}`}
                  onClick={handleDelete}
                  disabled={mutating}
                >
                  {mutating ? "Deleting…" : "Delete Conversation"}
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
                          PDF #{resource.pdf_id} · {resource.source} · {resource.status}
                          {resource.source_url ? ` · ${resource.source_url}` : ""}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

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
                            #{message.id} · {formatDate(message.created_at)}
                            {message.model ? ` · ${message.model}` : ""}
                          </span>
                        </div>
                        <div className={styles.messageBody}>{message.content}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className={styles.detailSection}>
                <div className={styles.detailSectionTitle}>Runs ({detail.runs.length})</div>
                {detail.runs.length === 0 ? (
                  <div className={styles.emptyState}>No runs stored.</div>
                ) : (
                  <div className={styles.runList}>
                    {detail.runs.map((run) => (
                      <div key={run.id} className={styles.runItem}>
                        <div className={styles.runHeader}>
                          <span className={styles.runTitle}>Run #{run.id}</span>
                          <span className={`${styles.statusBadge} ${statusClass(run.status)}`}>
                            {run.status}
                          </span>
                        </div>
                        <div className={styles.runMeta}>
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
            </>
          ) : (
            <div className={styles.emptyState}>Unable to load the selected conversation.</div>
          )}
        </div>
      </div>
    </div>
  );
}
