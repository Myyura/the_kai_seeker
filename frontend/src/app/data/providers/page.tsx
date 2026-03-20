"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import styles from "../page.module.css";

interface AdminProviderListItem {
  id: number;
  provider: string;
  model?: string | null;
  is_active: boolean;
  api_key_preview: string;
  created_at: string;
  updated_at: string;
}

interface AdminProviderListResponse {
  items: AdminProviderListItem[];
  count: number;
}

interface AdminProviderDetail extends AdminProviderListItem {}

function formatDate(value: string): string {
  return new Date(value).toLocaleString();
}

export default function DataProvidersPage() {
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [providers, setProviders] = useState<AdminProviderListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedProviderId, setSelectedProviderId] = useState<number | null>(null);
  const [detail, setDetail] = useState<AdminProviderDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mutating, setMutating] = useState(false);

  useEffect(() => {
    void loadProviders();
  }, [query]);

  useEffect(() => {
    if (selectedProviderId == null) {
      setDetail(null);
      return;
    }
    void loadDetail(selectedProviderId);
  }, [selectedProviderId]);

  const selectedListItem = useMemo(
    () => providers.find((item) => item.id === selectedProviderId) ?? null,
    [providers, selectedProviderId]
  );

  async function loadProviders(preferredId?: number | null) {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (query) params.set("query", query);
      params.set("limit", "100");
      const suffix = params.toString() ? `?${params.toString()}` : "";
      const data = await api.get<AdminProviderListResponse>(`/admin/providers${suffix}`);
      setProviders(data.items);
      setSelectedProviderId((current) => {
        const candidate = preferredId ?? current;
        if (candidate && data.items.some((item) => item.id === candidate)) {
          return candidate;
        }
        return data.items[0]?.id ?? null;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load providers");
    } finally {
      setLoading(false);
    }
  }

  async function loadDetail(providerId: number) {
    setDetailLoading(true);
    setError(null);
    try {
      const data = await api.get<AdminProviderDetail>(`/admin/providers/${providerId}`);
      setDetail(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load provider detail");
    } finally {
      setDetailLoading(false);
    }
  }

  async function handleRefresh() {
    await loadProviders(selectedProviderId);
  }

  async function handleDelete() {
    if (selectedProviderId == null || !selectedListItem) return;
    const confirmed = window.confirm(
      `Delete provider "${selectedListItem.provider}" and remove this saved key record?`
    );
    if (!confirmed) return;

    setMutating(true);
    setError(null);
    try {
      await api.delete(`/admin/providers/${selectedProviderId}`);
      setDetail(null);
      await loadProviders(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete provider");
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
        <h2 className={styles.pageTitle}>Providers</h2>
        <p className={styles.description}>
          Review saved provider records and remove obsolete API configurations in
          one place.
        </p>
      </div>

      <form className={styles.toolbar} onSubmit={handleFilterSubmit}>
        <div className={styles.toolbarGroup}>
          <input
            className={styles.searchInput}
            type="search"
            placeholder="Search provider, model, or base URL"
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
            <h3 className={styles.listTitle}>Provider Records</h3>
            <span className={styles.listCount}>
              {loading ? "Loading…" : `${providers.length} item${providers.length === 1 ? "" : "s"}`}
            </span>
          </div>

          {loading ? (
            <p className={styles.muted}>Loading providers…</p>
          ) : providers.length === 0 ? (
            <div className={styles.emptyState}>No providers match the current filters.</div>
          ) : (
            <div className={styles.pdfList}>
              {providers.map((provider) => (
                <button
                  key={provider.id}
                  type="button"
                  className={`${styles.pdfItem} ${
                    selectedProviderId === provider.id ? styles.pdfItemActive : ""
                  }`}
                  onClick={() => setSelectedProviderId(provider.id)}
                >
                  <div className={styles.pdfItemTop}>
                    <div className={styles.pdfName}>{provider.provider}</div>
                    {provider.is_active && (
                      <span className={`${styles.statusBadge} ${styles.statusProcessed}`}>
                        active
                      </span>
                    )}
                  </div>
                  <div className={styles.pdfMeta}>
                    <span>ID {provider.id}</span>
                    <span>{provider.model ?? "default model"}</span>
                    <span>updated {formatDate(provider.updated_at)}</span>
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
              <span className={styles.listCount}>Provider #{selectedListItem.id}</span>
            )}
          </div>

          {selectedProviderId == null ? (
            <div className={styles.emptyState}>Select a provider record to inspect it.</div>
          ) : detailLoading && !detail ? (
            <p className={styles.muted}>Loading detail…</p>
          ) : detail ? (
            <>
              <div className={styles.detailActions}>
                <Link
                  href="/settings/providers/"
                  className={`${styles.btnSmall} ${styles.detailLink}`}
                >
                  Open Provider Settings
                </Link>
                <button
                  type="button"
                  className={`${styles.btnSmall} ${styles.btnDanger}`}
                  onClick={handleDelete}
                  disabled={mutating}
                >
                  {mutating ? "Deleting…" : "Delete Provider"}
                </button>
              </div>

              <div className={styles.detailMeta}>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>Provider:</span> {detail.provider}
                </div>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>Model:</span>{" "}
                  {detail.model ?? "default model"}
                </div>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>Active:</span>{" "}
                  {detail.is_active ? "yes" : "no"}
                </div>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>ID:</span> {detail.id}
                </div>
                <div className={styles.detailMetaRow}>
                  <span className={styles.detailMetaLabel}>API Key Preview:</span>{" "}
                  {detail.api_key_preview}
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
                <div className={styles.detailSectionTitle}>Notes</div>
                <div className={styles.detailBox}>
                  Full API keys remain hidden here on purpose. Use settings if you
                  need to replace or test a provider, and use this page for broad
                  cleanup.
                </div>
              </div>
            </>
          ) : (
            <div className={styles.emptyState}>Unable to load the selected provider.</div>
          )}
        </div>
      </div>
    </div>
  );
}
