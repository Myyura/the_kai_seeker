"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import styles from "../page.module.css";

interface AdminStudyTargetListItem {
  id: number;
  school_id: string;
  program_id?: string | null;
  label: string;
  has_notes: boolean;
  created_at: string;
}

interface AdminStudyTargetListResponse {
  items: AdminStudyTargetListItem[];
  count: number;
}

interface AdminStudyTargetDetail {
  id: number;
  school_id: string;
  program_id?: string | null;
  label: string;
  notes?: string | null;
  created_at: string;
}

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

export default function DataStudyTargetsPage() {
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [targets, setTargets] = useState<AdminStudyTargetListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedTargetId, setSelectedTargetId] = useState<number | null>(null);
  const [detail, setDetail] = useState<AdminStudyTargetDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mutating, setMutating] = useState(false);

  useEffect(() => {
    void loadTargets();
  }, [query]);

  useEffect(() => {
    if (selectedTargetId == null) {
      setDetail(null);
      return;
    }
    void loadDetail(selectedTargetId);
  }, [selectedTargetId]);

  const selectedListItem = useMemo(
    () => targets.find((item) => item.id === selectedTargetId) ?? null,
    [targets, selectedTargetId]
  );

  async function loadTargets(preferredId?: number | null) {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (query) params.set("query", query);
      params.set("limit", "100");
      const suffix = params.toString() ? `?${params.toString()}` : "";
      const data = await api.get<AdminStudyTargetListResponse>(
        `/admin/study-targets${suffix}`
      );
      setTargets(data.items);
      setSelectedTargetId((current) => {
        const candidate = preferredId ?? current;
        if (candidate && data.items.some((item) => item.id === candidate)) {
          return candidate;
        }
        return data.items[0]?.id ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load study targets");
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(targetId: number) {
    setDetailLoading(true);
    setError(null);
    try {
      const data = await api.get<AdminStudyTargetDetail>(
        `/admin/study-targets/${targetId}`
      );
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load study target detail");
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleRefresh() {
    await loadTargets(selectedTargetId);
  }

  async function handleDelete() {
    if (selectedTargetId == null || !selectedListItem) return;
    const confirmed = window.confirm(
      `Delete study target "${selectedListItem.label}" and its saved notes?`
    );
    if (!confirmed) return;

    setMutating(true);
    setError(null);
    try {
      await api.delete(`/admin/study-targets/${selectedTargetId}`);
      setDetail(null);
      await loadTargets(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete study target");
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
        <h2 className={styles.pageTitle}>Study Targets</h2>
        <p className={styles.description}>
          Review saved targets and remove obsolete goal records in one pass.
        </p>
      </div>

      <form className={styles.toolbar} onSubmit={handleFilterSubmit}>
        <div className={styles.toolbarGroup}>
          <input
            className={styles.searchInput}
            type="search"
            placeholder="Search label, school, or program"
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
            <h3 className={styles.listTitle}>Saved Targets</h3>
            <span className={styles.listCount}>
              {loading ? "Loading…" : `${targets.length} item${targets.length === 1 ? "" : "s"}`}
            </span>
          </div>

          {loading ? (
            <p className={styles.muted}>Loading study targets…</p>
          ) : targets.length === 0 ? (
            <div className={styles.emptyState}>No study targets match the current filters.</div>
          ) : (
            <div className={styles.pdfList}>
              {targets.map((target) => (
                <button
                  key={target.id}
                  type="button"
                  className={`${styles.pdfItem} ${
                    selectedTargetId === target.id ? styles.pdfItemActive : ""
                  }`}
                  onClick={() => setSelectedTargetId(target.id)}
                >
                  <div className={styles.pdfItemTop}>
                    <div className={styles.pdfName}>{target.label}</div>
                  </div>
                  <div className={styles.pdfMeta}>
                    <span>ID {target.id}</span>
                    <span>{target.school_id}</span>
                    <span>{target.program_id ?? "no program id"}</span>
                    <span>{target.has_notes ? "notes saved" : "no notes"}</span>
                    <span>created {formatDate(target.created_at)}</span>
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
              <span className={styles.listCount}>Target #{selectedListItem.id}</span>
            )}
          </div>

          {selectedTargetId == null ? (
            <div className={styles.emptyState}>Select a study target to inspect it.</div>
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
                  {mutating ? "Deleting…" : "Delete Study Target"}
                </button>
              </div>

              <div className={styles.detailMeta}>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>Label:</span> {detail.label}
                </div>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>School ID:</span>{" "}
                  {detail.school_id}
                </div>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>Program ID:</span>{" "}
                  {detail.program_id ?? "none"}
                </div>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>Created:</span>{" "}
                  {formatDate(detail.created_at)}
                </div>
              </div>

              <div className={styles.detailSection}>
                <div className={styles.detailSectionTitle}>Notes</div>
                <div className={styles.detailBox}>{detail.notes || "No notes saved."}</div>
              </div>
            </>
          ) : (
            <div className={styles.emptyState}>Unable to load the selected study target.</div>
          )}
        </div>
      </div>
    </div>
  );
}
