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

interface AdminConversationToolArtifact {
  id: number;
  kind: string;
  label?: string | null;
  summary: string;
  summary_format: string;
  locator: Record<string, unknown>;
  replay?: Record<string, unknown> | null;
  is_primary: boolean;
  created_at: string;
}

interface AdminConversationToolCall {
  id: number;
  sequence: number;
  call_id: string;
  tool_name: string;
  display_name?: string | null;
  activity_label?: string | null;
  arguments: Record<string, unknown>;
  output: Record<string, unknown>;
  success: boolean;
  status: string;
  error_text?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  artifacts: AdminConversationToolArtifact[];
  created_at: string;
}

interface AdminConversationRun {
  id: number;
  assistant_message_id?: number | null;
  status: string;
  tool_call_count: number;
  artifact_count: number;
  created_at: string;
  updated_at: string;
  tool_calls: AdminConversationToolCall[];
  snapshot: Record<string, unknown>;
}

interface AdminConversationPdf {
  pdf_id: number;
  filename: string;
  status: string;
  source: string;
  source_url?: string | null;
}

interface AdminConversationRuntimeSnapshot {
  id: number;
  created_at: string;
  payload: Record<string, unknown>;
}

interface AdminConversationLongTermMemory {
  id: number;
  memory_type: string;
  scope: string;
  content: string;
  summary?: string | null;
  importance: number;
  confidence: number;
  related_target_id?: number | null;
  source_session_id?: number | null;
  source_run_id?: number | null;
  tags: string[];
  status: string;
  created_at: string;
  updated_at: string;
}

interface AdminConversationDetail {
  id: number;
  title: string;
  created_at: string;
  updated_at: string;
  messages: AdminConversationMessage[];
  runs: AdminConversationRun[];
  pdf_resources: AdminConversationPdf[];
  runtime_link: Record<string, unknown>;
  runtime_snapshots: AdminConversationRuntimeSnapshot[];
  long_term_memory_records: AdminConversationLongTermMemory[];
  short_term_memory: Record<string, unknown>;
}

type ConversationTab =
  | "overview"
  | "runInspector"
  | "longTermMemory"
  | "shortTermMemory"
  | "timeline"
  | "messages";

const CONVERSATION_TABS: { id: ConversationTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "runInspector", label: "Run Inspector" },
  { id: "longTermMemory", label: "Long-Term Memory" },
  { id: "shortTermMemory", label: "Short-Term Memory" },
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

function asNumber(value: unknown): number | null {
  return typeof value === "number" ? value : null;
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
    "name",
    "memory_type",
    "url",
    "filename",
    "query",
    "key",
    "user_request",
    "source_url",
    "school_id",
    "resource_id",
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
    "scope",
    "source_run_id",
    "importance",
    "confidence",
    "resource_type",
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
    "turn_summary",
    "summary",
    "assistant_summary",
    "value",
    "content",
    "content_preview",
    "note",
    "description",
    "question",
    "prompt_block",
  ];
  for (const key of bodyKeys) {
    const value = asString(record[key]);
    if (value) return previewText(value);
  }
  return previewText(stringifyJson(record), 320);
}

function toolCallLabel(toolCall: AdminConversationToolCall): string {
  return toolCall.display_name || toolCall.tool_name;
}

function toolCallSummary(toolCall: AdminConversationToolCall): string {
  const artifactSummary = toolCall.artifacts
    .map((artifact) => artifact.summary)
    .find((summary) => typeof summary === "string" && summary.trim().length > 0);
  if (artifactSummary) return previewText(artifactSummary);
  if (toolCall.error_text) return previewText(toolCall.error_text);
  return previewText(stringifyJson(toolCall.output), 320);
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
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
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
      setSelectedRunId(null);
      return;
    }
    void loadDetail(selectedSessionId);
  }, [selectedSessionId]);

  useEffect(() => {
    if (!detail) {
      setSelectedRunId(null);
      return;
    }
    setSelectedRunId((current) => {
      if (current && detail.runs.some((run) => run.id === current)) return current;
      return detail.runs[detail.runs.length - 1]?.id ?? null;
    });
  }, [detail]);

  const selectedListItem = useMemo(
    () => sessions.find((item) => item.id === selectedSessionId) ?? null,
    [sessions, selectedSessionId]
  );

  const selectedRun = useMemo(() => {
    if (!detail) return null;
    return (
      detail.runs.find((run) => run.id === selectedRunId) ??
      detail.runs[detail.runs.length - 1] ??
      null
    );
  }, [detail, selectedRunId]);

  const selectedRunIndex = useMemo(() => {
    if (!detail || !selectedRun) return -1;
    return detail.runs.findIndex((run) => run.id === selectedRun.id);
  }, [detail, selectedRun]);

  const selectedSnapshot = isRecord(selectedRun?.snapshot) ? selectedRun.snapshot : {};
  const selectedHostContextState = isRecord(selectedSnapshot.host_context_state)
    ? selectedSnapshot.host_context_state
    : {};
  const selectedTurnInput = isRecord(selectedSnapshot.turn_input)
    ? selectedSnapshot.turn_input
    : {};
  const selectedContextSync = isRecord(selectedSnapshot.context_sync)
    ? selectedSnapshot.context_sync
    : {};
  const selectedOpaqueState = isRecord(selectedSnapshot.opaque_state)
    ? selectedSnapshot.opaque_state
    : {};
  const selectedRuntimeSnapshot = isRecord(selectedSnapshot.opaque_state)
    ? {
        turn_summary: selectedSnapshot.turn_summary ?? selectedSnapshot.summary,
        short_term_memory: selectedSnapshot.short_term_memory,
        opaque_state: selectedOpaqueState,
        captured_at: selectedSnapshot.captured_at,
      }
    : {};
  const selectedProvider = isRecord(selectedSnapshot.provider) ? selectedSnapshot.provider : {};
  const selectedRuntimeLink = isRecord(selectedSnapshot.runtime_link)
    ? selectedSnapshot.runtime_link
    : {};
  const selectedError = isRecord(selectedSnapshot.error) ? selectedSnapshot.error : {};
  const selectedArtifacts = selectedRun?.tool_calls.flatMap((toolCall) => toolCall.artifacts) ?? [];
  const selectedUsage = isRecord(selectedSnapshot.usage) ? selectedSnapshot.usage : {};

  const memoryPack = isRecord(selectedHostContextState.memory_pack)
    ? selectedHostContextState.memory_pack
    : {};
  const sessionResourceHandles = asRecordList(selectedHostContextState.session_resource_handles);
  const transientResourceHandles = asRecordList(selectedTurnInput.transient_resource_handles);
  const activeSkills = asRecordList(selectedHostContextState.skill_definitions);
  const availableTools = asRecordList(selectedHostContextState.tool_definitions);
  const toolRecords = asRecordList(selectedSnapshot.tool_calls);
  const longTermMemoryWrites = asRecordList(selectedSnapshot.long_term_memory_writes);

  const shortTermMemoryGoal: Record<string, unknown> = isRecord(detail?.short_term_memory?.goal)
    ? detail.short_term_memory.goal
    : {};
  const shortTermMemoryProgress: Record<string, unknown> = isRecord(detail?.short_term_memory?.progress)
    ? detail.short_term_memory.progress
    : {};
  const shortTermMemoryArtifacts: Record<string, unknown> = isRecord(detail?.short_term_memory?.artifacts)
    ? detail.short_term_memory.artifacts
    : {};

  async function loadSessions(preferredId?: number | null) {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (query) params.set("query", query);
      params.set("limit", "100");
      const suffix = params.toString() ? `?${params.toString()}` : "";
      const data = await api.get<AdminConversationListResponse>(`/admin/conversations${suffix}`);
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
      const data = await api.get<AdminConversationDetail>(`/admin/conversations/${sessionId}`);
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
      `Delete conversation "${selectedListItem.title}" and all of its messages, runs, runtime records, and attached references?`
    );
    if (!confirmed) return;

    setMutating(true);
    setError(null);
    try {
      await api.delete(`/admin/conversations/${selectedSessionId}`);
      setDetail(null);
      setSelectedRunId(null);
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
    emptyText: string,
    rawLabel = "View raw record"
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
                  <summary className={styles.rawSummary}>{rawLabel}</summary>
                  <pre className={styles.rawPre}>{stringifyJson(item)}</pre>
                </details>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  function renderJsonSection(title: string, value: unknown, emptyText: string, rawLabel = "View raw JSON") {
    const isEmptyRecord = isRecord(value) && Object.keys(value).length === 0;
    const isEmptyList = Array.isArray(value) && value.length === 0;
    const isEmptyString = typeof value === "string" && value.trim().length === 0;
    const isEmpty = value == null || isEmptyRecord || isEmptyList || isEmptyString;

    return (
      <div className={styles.detailSection}>
        <div className={styles.detailSectionTitle}>{title}</div>
        {isEmpty ? (
          <div className={styles.emptyState}>{emptyText}</div>
        ) : (
          <details className={styles.rawDetails} open>
            <summary className={styles.rawSummary}>{rawLabel}</summary>
            <pre className={styles.rawPre}>{stringifyJson(value)}</pre>
          </details>
        )}
      </div>
    );
  }

  function renderRunSelector() {
    if (!detail || detail.runs.length === 0) return null;

    return (
      <div className={styles.detailSection}>
        <div className={styles.detailSectionTitle}>Runs</div>
        <div className={styles.recordBadgeRow}>
          {detail.runs.map((run, index) => {
            const active = run.id === selectedRun?.id;
            return (
              <button
                key={run.id}
                type="button"
                className={`${styles.selectorButton} ${active ? styles.selectorButtonActive : ""}`}
                onClick={() => setSelectedRunId(run.id)}
              >
                <span>{sessionRunLabel(index)}</span>
                <span>#{run.id}</span>
                <span>{run.status}</span>
              </button>
            );
          })}
        </div>
      </div>
    );
  }

  function renderOverviewTab() {
    if (!detail) return null;
    const latestRun = detail.runs[detail.runs.length - 1] ?? null;
    const runtimeLink = isRecord(detail.runtime_link) ? detail.runtime_link : {};
    const latestSnapshot = detail.runtime_snapshots[detail.runtime_snapshots.length - 1] ?? null;
    const latestRunPayload = isRecord(latestRun?.snapshot) ? latestRun.snapshot : {};
    const latestHostContext = isRecord(latestRunPayload.host_context_state)
      ? latestRunPayload.host_context_state
      : {};
    const latestSessionResources = asRecordList(latestHostContext.session_resource_handles);

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
            <div className={styles.summaryLabel}>Runtime Snapshots</div>
            <div className={styles.summaryValue}>{detail.runtime_snapshots.length}</div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Long-Term Records</div>
            <div className={styles.summaryValue}>{detail.long_term_memory_records.length}</div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Session Resources</div>
            <div className={styles.summaryValue}>{latestSessionResources.length}</div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Attached PDFs</div>
            <div className={styles.summaryValue}>{detail.pdf_resources.length}</div>
          </div>
        </div>

        <div className={styles.stateGrid}>
          <div className={styles.detailSection}>
            <div className={styles.detailSectionTitle}>Runtime Link</div>
            <div className={styles.detailMeta}>
              <div className={styles.detailMetaRow}>
                <span className={styles.detailMetaLabel}>Runtime:</span>{" "}
                {asString(runtimeLink.runtime_name) || "Not bound"}
              </div>
              <div className={styles.detailMetaRow}>
                <span className={styles.detailMetaLabel}>Runtime Session:</span>{" "}
                {asString(runtimeLink.runtime_session_id) || "Not recorded"}
              </div>
              <div className={styles.detailMetaRow}>
                <span className={styles.detailMetaLabel}>Conversation ID:</span>{" "}
                {asString(runtimeLink.runtime_conversation_id) || "Not recorded"}
              </div>
              <div className={styles.detailMetaRow}>
                <span className={styles.detailMetaLabel}>Status:</span>{" "}
                {asString(runtimeLink.status) || "Unknown"}
              </div>
            </div>
          </div>

          <div className={styles.detailSection}>
            <div className={styles.detailSectionTitle}>Latest Run</div>
            <div className={styles.detailMeta}>
              <div className={styles.detailMetaRow}>
                <span className={styles.detailMetaLabel}>Run:</span>{" "}
                {latestRun ? `${sessionRunLabel(detail.runs.length - 1)} · #${latestRun.id}` : "No runs yet"}
              </div>
              <div className={styles.detailMetaRow}>
                <span className={styles.detailMetaLabel}>Status:</span>{" "}
                {latestRun?.status ?? "Not recorded"}
              </div>
              <div className={styles.detailMetaRow}>
                <span className={styles.detailMetaLabel}>Context Version:</span>{" "}
                {asString(latestHostContext.context_version) || "Not recorded"}
              </div>
              <div className={styles.detailMetaRow}>
                <span className={styles.detailMetaLabel}>Snapshot:</span>{" "}
                {latestSnapshot ? `#${latestSnapshot.id} at ${formatDate(latestSnapshot.created_at)}` : "None"}
              </div>
            </div>
          </div>
        </div>

        <div className={styles.detailSection}>
          <div className={styles.detailSectionTitle}>Base System Prompt</div>
          {asString(runtimeLink.base_system_prompt) ? (
            <div className={styles.detailBox}>{asString(runtimeLink.base_system_prompt)}</div>
          ) : (
            <div className={styles.emptyState}>No base system prompt recorded.</div>
          )}
        </div>

        {renderRecordListSection(
          "Current Session Resources",
          latestSessionResources,
          "No session-level resources recorded."
        )}
        {renderRecordListSection(
          "Attached PDFs",
          detail.pdf_resources.map((resource) => ({
            pdf_id: resource.pdf_id,
            filename: resource.filename,
            status: resource.status,
            source: resource.source,
            source_url: resource.source_url ?? undefined,
          })),
          "No PDFs attached to this session."
        )}
        {renderRecordListSection(
          "Derived Long-Term Memory",
          detail.long_term_memory_records.map((record) => ({
            id: record.id,
            memory_type: record.memory_type,
            scope: record.scope,
            content: record.content,
            summary: record.summary ?? undefined,
            importance: record.importance,
            confidence: record.confidence,
            source_run_id: record.source_run_id ?? undefined,
            status: record.status,
          })),
          "No derived long-term memory records stored for this session."
        )}
        {renderJsonSection("Runtime Link JSON", detail.runtime_link, "No runtime link recorded.")}
      </div>
    );
  }

  function renderRunInspectorTab() {
    if (!detail) return null;

    return (
      <div className={styles.tabPanel}>
        {renderRunSelector()}

        {!selectedRun ? (
          <div className={styles.emptyState}>No runs stored for this session.</div>
        ) : (
          <>
            <div className={styles.summaryGrid}>
              <div className={styles.summaryCard}>
                <div className={styles.summaryLabel}>Run Status</div>
                <div className={styles.summaryValue}>{selectedRun.status}</div>
              </div>
              <div className={styles.summaryCard}>
                <div className={styles.summaryLabel}>Tool Calls</div>
                <div className={styles.summaryValue}>{selectedRun.tool_call_count}</div>
              </div>
              <div className={styles.summaryCard}>
                <div className={styles.summaryLabel}>Artifacts</div>
                <div className={styles.summaryValue}>{selectedRun.artifact_count}</div>
              </div>
              <div className={styles.summaryCard}>
                <div className={styles.summaryLabel}>Memory Writes</div>
                <div className={styles.summaryValue}>{longTermMemoryWrites.length}</div>
              </div>
              <div className={styles.summaryCard}>
                <div className={styles.summaryLabel}>Session Resources</div>
                <div className={styles.summaryValue}>{sessionResourceHandles.length}</div>
              </div>
              <div className={styles.summaryCard}>
                <div className={styles.summaryLabel}>Turn Resources</div>
                <div className={styles.summaryValue}>{transientResourceHandles.length}</div>
              </div>
            </div>

            <div className={styles.stateGrid}>
              <div className={styles.detailSection}>
                <div className={styles.detailSectionTitle}>Run Metadata</div>
                <div className={styles.detailMeta}>
                  <div className={styles.detailMetaRow}>
                    <span className={styles.detailMetaLabel}>Run:</span>{" "}
                    {selectedRunIndex >= 0 ? sessionRunLabel(selectedRunIndex) : "Selected Run"} · #
                    {selectedRun.id}
                  </div>
                  <div className={styles.detailMetaRow}>
                    <span className={styles.detailMetaLabel}>Assistant Message:</span>{" "}
                    {selectedRun.assistant_message_id ? `#${selectedRun.assistant_message_id}` : "None"}
                  </div>
                  <div className={styles.detailMetaRow}>
                    <span className={styles.detailMetaLabel}>Created:</span>{" "}
                    {formatDate(selectedRun.created_at)}
                  </div>
                  <div className={styles.detailMetaRow}>
                    <span className={styles.detailMetaLabel}>Updated:</span>{" "}
                    {formatDate(selectedRun.updated_at)}
                  </div>
                </div>
              </div>

              <div className={styles.detailSection}>
                <div className={styles.detailSectionTitle}>Context Sync</div>
                <div className={styles.detailMeta}>
                  <div className={styles.detailMetaRow}>
                    <span className={styles.detailMetaLabel}>Applied:</span>{" "}
                    {asString(selectedContextSync.applied) || "Unknown"}
                  </div>
                  <div className={styles.detailMetaRow}>
                    <span className={styles.detailMetaLabel}>Context Version:</span>{" "}
                    {asString(selectedContextSync.context_version) || "Not recorded"}
                  </div>
                  <div className={styles.detailMetaRow}>
                    <span className={styles.detailMetaLabel}>Provider:</span>{" "}
                    {asString(selectedProvider.name) || "Unknown"}
                    {asString(selectedProvider.model) ? ` · ${asString(selectedProvider.model)}` : ""}
                  </div>
                  <div className={styles.detailMetaRow}>
                    <span className={styles.detailMetaLabel}>Payload Version:</span>{" "}
                    {asNumber(selectedOpaqueState.version) ?? asNumber(selectedSnapshot.version) ?? "Not recorded"}
                  </div>
                </div>
              </div>
            </div>

            {renderRecordListSection(
              "Turn Messages",
              asRecordList(selectedTurnInput.messages),
              "No turn messages recorded."
            )}
            {renderRecordListSection(
              "Session Resource Handles",
              sessionResourceHandles,
              "No session resources were visible to this run."
            )}
            {renderRecordListSection(
              "Transient Resource Handles",
              transientResourceHandles,
              "No transient resources were attached to this run."
            )}
            {renderRecordListSection(
              "Active Skills",
              activeSkills,
              "No active skills recorded for this run."
            )}
            {renderRecordListSection(
              "Available Tools",
              availableTools,
              "No tool definitions recorded for this run."
            )}
            {renderRecordListSection(
              "Tool Calls",
              toolRecords,
              "No tool calls captured for this run."
            )}
            {renderRecordListSection(
              "Long-Term Memory Writes",
              longTermMemoryWrites,
              "No long-term memory writes were recorded for this run."
            )}
            {renderJsonSection(
              "Memory Pack",
              memoryPack,
              "No memory pack was captured for this run."
            )}
            {renderJsonSection(
              "Runtime Snapshot",
              selectedRuntimeSnapshot,
              "No runtime snapshot was captured for this run."
            )}
            {renderJsonSection(
              "Artifact Summaries",
              selectedArtifacts,
              "No tool artifacts were captured for this run."
            )}
            {renderJsonSection(
              "Usage",
              selectedUsage,
              "No usage payload was captured for this run."
            )}
            {renderJsonSection(
              "Error",
              selectedError,
              "No error payload recorded for this run."
            )}
            {renderJsonSection(
              "Raw Run Snapshot",
              selectedRun.snapshot,
              "No runtime snapshot recorded for this run."
            )}
            {renderJsonSection(
              "Runtime Link During Run",
              selectedRuntimeLink,
              "No runtime link payload captured for this run."
            )}
          </>
        )}
      </div>
    );
  }

  function renderLongTermMemoryTab() {
    if (!detail) return null;

    const typeCounts = detail.long_term_memory_records.reduce<Record<string, number>>((acc, record) => {
      acc[record.memory_type] = (acc[record.memory_type] ?? 0) + 1;
      return acc;
    }, {});

    return (
      <div className={styles.tabPanel}>
        <div className={styles.summaryGrid}>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Persisted Records</div>
            <div className={styles.summaryValue}>{detail.long_term_memory_records.length}</div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Latest Run Writes</div>
            <div className={styles.summaryValue}>{longTermMemoryWrites.length}</div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Preferences</div>
            <div className={styles.summaryValue}>{typeCounts.preference ?? 0}</div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Session Insights</div>
            <div className={styles.summaryValue}>{typeCounts.session_insight ?? 0}</div>
          </div>
        </div>

        {renderRecordListSection(
          "Persisted Long-Term Memory",
          detail.long_term_memory_records.map((record) => ({
            id: record.id,
            memory_type: record.memory_type,
            scope: record.scope,
            content: record.content,
            summary: record.summary ?? undefined,
            importance: record.importance,
            confidence: record.confidence,
            source_run_id: record.source_run_id ?? undefined,
            related_target_id: record.related_target_id ?? undefined,
            status: record.status,
            tags: record.tags,
          })),
          "No long-term memory records stored for this session."
        )}
        {renderJsonSection(
          "Latest Run Memory Writes",
          longTermMemoryWrites,
          "No memory writes were captured for the selected run."
        )}
      </div>
    );
  }

  function renderShortTermMemoryTab() {
    if (!detail) return null;

    return (
      <div className={styles.tabPanel}>
        <div className={styles.summaryGrid}>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Recent Requests</div>
            <div className={styles.summaryValue}>
              {asStringList(shortTermMemoryGoal.recent_user_requests).length}
            </div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Completed Work</div>
            <div className={styles.summaryValue}>
              {asStringList(shortTermMemoryProgress.completed_work).length}
            </div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Artifacts</div>
            <div className={styles.summaryValue}>
              {asRecordList(shortTermMemoryArtifacts.sources).length +
                asRecordList(shortTermMemoryArtifacts.visited_pages).length +
                asRecordList(shortTermMemoryArtifacts.pdfs).length}
            </div>
          </div>
          <div className={styles.summaryCard}>
            <div className={styles.summaryLabel}>Recent Turns</div>
            <div className={styles.summaryValue}>
              {asRecordList(shortTermMemoryProgress.recent_turns).length}
            </div>
          </div>
        </div>

        <div className={styles.stateGrid}>
          <div className={styles.detailSection}>
            <div className={styles.detailSectionTitle}>Core User Need</div>
            <div className={styles.detailBox}>
              {asString(shortTermMemoryGoal.core_user_need) || "No core need recorded."}
            </div>
          </div>
          <div className={styles.detailSection}>
            <div className={styles.detailSectionTitle}>Current Focus</div>
            <div className={styles.detailBox}>
              {asString(shortTermMemoryGoal.current_focus) || "No current focus recorded."}
            </div>
          </div>
        </div>

        {renderStringListSection(
          "Recent User Requests",
          asStringList(shortTermMemoryGoal.recent_user_requests),
          "No recent requests recorded."
        )}
        {renderStringListSection(
          "Completed Work",
          asStringList(shortTermMemoryProgress.completed_work),
          "No completed work recorded."
        )}
        {renderStringListSection(
          "Pending Actions",
          asStringList(shortTermMemoryProgress.pending_actions),
          "No pending actions recorded."
        )}
        {renderStringListSection(
          "Open Questions",
          asStringList(shortTermMemoryProgress.open_questions),
          "No open questions recorded."
        )}

        <div className={styles.detailSection}>
          <div className={styles.detailSectionTitle}>Last Turn Summary</div>
          <div className={styles.detailBox}>
            {asString(shortTermMemoryProgress.last_turn_summary) ||
              asString(shortTermMemoryProgress.last_assistant_summary) ||
              "No turn summary recorded."}
          </div>
        </div>

        {renderRecordListSection(
          "Recent Turns",
          asRecordList(shortTermMemoryProgress.recent_turns),
          "No turns recorded."
        )}
        {renderRecordListSection(
          "Sources",
          asRecordList(shortTermMemoryArtifacts.sources),
          "No sources recorded."
        )}
        {renderRecordListSection(
          "Visited Pages",
          asRecordList(shortTermMemoryArtifacts.visited_pages),
          "No visited pages recorded."
        )}
        {renderRecordListSection(
          "PDFs",
          asRecordList(shortTermMemoryArtifacts.pdfs),
          "No PDFs recorded."
        )}
        {renderRecordListSection(
          "School Searches",
          asRecordList(shortTermMemoryArtifacts.school_searches),
          "No school searches recorded."
        )}
        {renderRecordListSection(
          "Question Searches",
          asRecordList(shortTermMemoryArtifacts.question_searches),
          "No question searches recorded."
        )}
        {renderRecordListSection(
          "Fetched Questions",
          asRecordList(shortTermMemoryArtifacts.fetched_questions),
          "No fetched questions recorded."
        )}
        {renderRecordListSection(
          "PDF Queries",
          asRecordList(shortTermMemoryArtifacts.pdf_queries),
          "No PDF queries recorded."
        )}
        {renderRecordListSection(
          "Notes",
          asRecordList(shortTermMemoryArtifacts.notes),
          "No notes recorded."
        )}
        {renderJsonSection(
          "Raw Short-Term Memory",
          detail.short_term_memory,
          "No short-term memory payload stored."
        )}
      </div>
    );
  }

  function renderTimelineTab() {
    if (!detail) return null;

    return (
      <div className={styles.tabPanel}>
        {renderRunSelector()}

        {!selectedRun ? (
          <div className={styles.emptyState}>No runs stored.</div>
        ) : selectedRun.tool_calls.length === 0 ? (
          <div className={styles.emptyState}>No tool calls recorded for the selected run.</div>
        ) : (
          <div className={styles.eventList}>
            {selectedRun.tool_calls.map((toolCall) => (
              <div key={toolCall.id} className={styles.eventItem}>
                <div className={styles.eventHeader}>
                  <div className={styles.eventTitle}>{toolCallLabel(toolCall)}</div>
                  <div className={styles.eventMeta}>
                    seq {toolCall.sequence} | {formatDate(toolCall.created_at)}
                  </div>
                </div>

                {toolCallSummary(toolCall) && <div className={styles.eventBody}>{toolCallSummary(toolCall)}</div>}

                <div className={styles.eventSubsection}>
                  <div className={styles.eventSubsectionLabel}>Arguments</div>
                  <pre className={styles.rawPre}>{stringifyJson(toolCall.arguments)}</pre>
                </div>

                {toolCall.artifacts.length > 0 && (
                  <div className={styles.eventSubsection}>
                    <div className={styles.eventSubsectionLabel}>Artifacts</div>
                    <pre className={styles.rawPre}>{stringifyJson(toolCall.artifacts)}</pre>
                  </div>
                )}

                <details className={styles.rawDetails}>
                  <summary className={styles.rawSummary}>View raw tool call</summary>
                  <pre className={styles.rawPre}>{stringifyJson(toolCall)}</pre>
                </details>
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
    if (activeTab === "runInspector") return renderRunInspectorTab();
    if (activeTab === "longTermMemory") return renderLongTermMemoryTab();
    if (activeTab === "shortTermMemory") return renderShortTermMemoryTab();
    if (activeTab === "timeline") return renderTimelineTab();
    if (activeTab === "messages") return renderMessagesTab();
    return renderOverviewTab();
  }

  return (
    <div className={styles.container}>
      <div className={styles.pageIntro}>
        <h2 className={styles.pageTitle}>Conversations</h2>
        <p className={styles.description}>
          Inspect chat sessions from the new AgentRuntime architecture: runtime link, structured
          run snapshots, tool calls, artifact summaries, short-term memory, and derived long-term memory.
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
            {selectedListItem && <span className={styles.listCount}>Session #{selectedListItem.id}</span>}
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
                  <span className={styles.detailMetaLabel}>Created:</span> {formatDate(detail.created_at)}
                </div>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>Updated:</span> {formatDate(detail.updated_at)}
                </div>
                {detailLoading && <div className={styles.muted}>Refreshing detail...</div>}
              </div>

              <div className={styles.tabBar}>
                {CONVERSATION_TABS.map((tab) => (
                  <button
                    key={tab.id}
                    type="button"
                    className={`${styles.tabButton} ${activeTab === tab.id ? styles.tabButtonActive : ""}`}
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
