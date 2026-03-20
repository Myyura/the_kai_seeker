"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import styles from "../page.module.css";

interface AdminPdfListItem {
  id: number;
  filename: string;
  status: string;
  summary_available: boolean;
  extracted_text_length: number;
  chunk_count: number;
  referenced_session_count: number;
  created_at: string;
  updated_at: string;
}

interface AdminPdfListResponse {
  items: AdminPdfListItem[];
  count: number;
}

interface AdminPdfReference {
  session_id: number;
  session_title: string;
  source_type: string;
  source_url?: string | null;
  attached_at: string;
}

interface AdminPdfDetail {
  id: number;
  filename: string;
  status: string;
  storage_path: string;
  storage_exists: boolean;
  summary_markdown?: string | null;
  extracted_text_preview?: string | null;
  extracted_text_length: number;
  chunk_count: number;
  referenced_sessions: AdminPdfReference[];
  created_at: string;
  updated_at: string;
}

interface AdminPdfChunk {
  id: number;
  page_number: number;
  content_preview: string;
  content_length: number;
}

interface AdminPdfChunksResponse {
  pdf_id: number;
  chunks: AdminPdfChunk[];
  count: number;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

function statusClass(status: string): string {
  if (status === "uploaded") return styles.statusUploaded;
  if (status === "processing") return styles.statusProcessing;
  return styles.statusProcessed;
}

export default function DataPdfsPage() {
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [pdfs, setPdfs] = useState<AdminPdfListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedPdfId, setSelectedPdfId] = useState<number | null>(null);
  const [detail, setDetail] = useState<AdminPdfDetail | null>(null);
  const [chunks, setChunks] = useState<AdminPdfChunk[]>([]);
  const [totalChunks, setTotalChunks] = useState(0);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mutating, setMutating] = useState(false);

  useEffect(() => {
    void loadPdfs();
  }, [query, statusFilter]);

  useEffect(() => {
    if (selectedPdfId == null) {
      setDetail(null);
      setChunks([]);
      setTotalChunks(0);
      return;
    }
    void loadPdfDetail(selectedPdfId);
  }, [selectedPdfId]);

  const selectedListItem = useMemo(
    () => pdfs.find((item) => item.id === selectedPdfId) ?? null,
    [pdfs, selectedPdfId]
  );

  async function loadPdfs(preferredId?: number | null) {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (query) params.set("query", query);
      if (statusFilter) params.set("status", statusFilter);
      params.set("limit", "100");
      const suffix = params.toString() ? `?${params.toString()}` : "";
      const data = await api.get<AdminPdfListResponse>(`/admin/pdfs${suffix}`);
      setPdfs(data.items);
      setSelectedPdfId((current) => {
        const candidate = preferredId ?? current;
        if (candidate && data.items.some((item) => item.id === candidate)) {
          return candidate;
        }
        return data.items[0]?.id ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load PDFs");
    } finally {
      setLoading(false);
    }
  }

  async function loadPdfDetail(pdfId: number) {
    setDetailLoading(true);
    setError(null);
    try {
      const [detailData, chunkData] = await Promise.all([
        api.get<AdminPdfDetail>(`/admin/pdfs/${pdfId}`),
        api.get<AdminPdfChunksResponse>(`/admin/pdfs/${pdfId}/chunks?limit=20`),
      ]);
      setDetail(detailData);
      setChunks(chunkData.chunks);
      setTotalChunks(chunkData.count);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load PDF detail");
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleRefresh() {
    await loadPdfs(selectedPdfId);
  }

  async function handleReprocess() {
    if (selectedPdfId == null) return;
    setMutating(true);
    setError(null);
    try {
      await api.post(`/admin/pdfs/${selectedPdfId}/reprocess`, {});
      await loadPdfs(selectedPdfId);
      await loadPdfDetail(selectedPdfId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reprocess PDF");
    } finally {
      setMutating(false);
    }
  }

  async function handleDelete() {
    if (selectedPdfId == null || !selectedListItem) return;
    const confirmed = window.confirm(
      `Delete PDF "${selectedListItem.filename}" and its processed data?`
    );
    if (!confirmed) return;

    setMutating(true);
    setError(null);
    try {
      await api.delete(`/admin/pdfs/${selectedPdfId}`);
      setDetail(null);
      setChunks([]);
      setTotalChunks(0);
      await loadPdfs(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete PDF");
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
        <h2 className={styles.pageTitle}>PDFs</h2>
        <p className={styles.description}>
          Review uploaded and fetched PDFs, inspect processed output, and clean up
          stale documents without touching the database manually.
        </p>
      </div>

      <form className={styles.toolbar} onSubmit={handleFilterSubmit}>
        <div className={styles.toolbarGroup}>
          <input
            className={styles.searchInput}
            type="search"
            placeholder="Search by filename"
            value={queryInput}
            onChange={(event) => setQueryInput(event.target.value)}
          />
          <select
            className={styles.select}
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
          >
            <option value="">All statuses</option>
            <option value="uploaded">Uploaded</option>
            <option value="processing">Processing</option>
            <option value="processed">Processed</option>
          </select>
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
            <h3 className={styles.listTitle}>Documents</h3>
            <span className={styles.listCount}>
              {loading ? "Loading…" : `${pdfs.length} item${pdfs.length === 1 ? "" : "s"}`}
            </span>
          </div>

          {loading ? (
            <p className={styles.muted}>Loading PDFs…</p>
          ) : pdfs.length === 0 ? (
            <div className={styles.emptyState}>No PDFs match the current filters.</div>
          ) : (
            <div className={styles.pdfList}>
              {pdfs.map((pdf) => (
                <button
                  key={pdf.id}
                  type="button"
                  className={`${styles.pdfItem} ${
                    selectedPdfId === pdf.id ? styles.pdfItemActive : ""
                  }`}
                  onClick={() => setSelectedPdfId(pdf.id)}
                >
                  <div className={styles.pdfItemTop}>
                    <div className={styles.pdfName}>{pdf.filename}</div>
                    <span className={`${styles.statusBadge} ${statusClass(pdf.status)}`}>
                      {pdf.status}
                    </span>
                  </div>
                  <div className={styles.pdfMeta}>
                    <span>ID {pdf.id}</span>
                    <span>{pdf.chunk_count} chunks</span>
                    <span>{pdf.referenced_session_count} sessions</span>
                    <span>{pdf.summary_available ? "summary ready" : "no summary"}</span>
                    <span>updated {formatDate(pdf.updated_at)}</span>
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
              <span className={styles.listCount}>PDF #{selectedListItem.id}</span>
            )}
          </div>

          {selectedPdfId == null ? (
            <div className={styles.emptyState}>Select a PDF to inspect its data.</div>
          ) : detailLoading && !detail ? (
            <p className={styles.muted}>Loading detail…</p>
          ) : detail ? (
            <>
              <div className={styles.detailActions}>
                <button
                  type="button"
                  className={styles.btnSmall}
                  onClick={handleReprocess}
                  disabled={mutating}
                >
                  {mutating ? "Working…" : "Reprocess"}
                </button>
                <button
                  type="button"
                  className={`${styles.btnSmall} ${styles.btnDanger}`}
                  onClick={handleDelete}
                  disabled={mutating}
                >
                  Delete
                </button>
              </div>

              <div className={styles.detailMeta}>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>Filename:</span> {detail.filename}
                </div>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>Storage:</span> {detail.storage_path}
                </div>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>File present:</span>{" "}
                  {detail.storage_exists ? "yes" : "missing"}
                </div>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>Updated:</span>{" "}
                  {formatDate(detail.updated_at)}
                </div>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>Extracted text:</span>{" "}
                  {detail.extracted_text_length.toLocaleString()} chars
                </div>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>Chunks:</span> {detail.chunk_count}
                </div>
              </div>

              <div className={styles.detailSection}>
                <div className={styles.detailSectionTitle}>Session References</div>
                {detail.referenced_sessions.length === 0 ? (
                  <div className={styles.emptyState}>Not attached to any chat session.</div>
                ) : (
                  <div className={styles.referenceList}>
                    {detail.referenced_sessions.map((reference) => (
                      <div key={`${reference.session_id}-${reference.attached_at}`} className={styles.referenceItem}>
                        <div className={styles.referenceTitle}>{reference.session_title}</div>
                        <div className={styles.referenceMeta}>
                          Session #{reference.session_id} · {reference.source_type} ·{" "}
                          {formatDate(reference.attached_at)}
                          {reference.source_url ? ` · ${reference.source_url}` : ""}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div className={styles.detailSection}>
                <div className={styles.detailSectionTitle}>Summary</div>
                <div className={styles.detailBox}>
                  {detail.summary_markdown || "No summary stored."}
                </div>
              </div>

              <div className={styles.detailSection}>
                <div className={styles.detailSectionTitle}>Extracted Text Preview</div>
                <div className={styles.detailBox}>
                  {detail.extracted_text_preview || "No extracted text stored."}
                </div>
              </div>

              <div className={styles.detailSection}>
                <div className={styles.detailSectionTitle}>
                  Chunk Preview ({chunks.length}/{totalChunks})
                </div>
                {chunks.length === 0 ? (
                  <div className={styles.emptyState}>No chunks stored yet.</div>
                ) : (
                  <div className={styles.chunkList}>
                    {chunks.map((chunk) => (
                      <div key={chunk.id} className={styles.chunkItem}>
                        <div className={styles.chunkTitle}>Page {chunk.page_number}</div>
                        <div className={styles.chunkMeta}>
                          {chunk.content_length} chars
                        </div>
                        <div className={styles.detailBox}>{chunk.content_preview}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className={styles.emptyState}>Unable to load the selected PDF.</div>
          )}
        </div>
      </div>
    </div>
  );
}
