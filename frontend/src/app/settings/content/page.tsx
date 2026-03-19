"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "../page.module.css";

interface ContentStats {
  loaded: boolean;
  schools_count: number;
  questions_count: number;
  domain_id: string;
  domain_name: string;
  sources_count: number;
}

interface ContentSyncSource {
  id: string;
  name: string;
  kind: string;
  description: string;
  enabled: boolean;
  is_default: boolean;
}

interface ContentSyncSourcesResponse {
  sources: ContentSyncSource[];
  default_source_id: string | null;
}

interface ContentSyncResponse {
  status: string;
  message: string;
  source_id: string;
  schools_count?: number | null;
  questions_count?: number | null;
}

export default function SettingsContentPage() {
  const [contentStats, setContentStats] = useState<ContentStats | null>(null);
  const [syncSources, setSyncSources] = useState<ContentSyncSource[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState("kai-project");
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  useEffect(() => {
    loadContentStats();
    loadSyncSources();
  }, []);

  async function loadContentStats() {
    try {
      const data = await api.get<ContentStats>("/content/stats");
      setContentStats(data);
    } catch {
      /* backend may not be running */
    }
  }

  async function loadSyncSources() {
    try {
      const data = await api.get<ContentSyncSourcesResponse>("/content/sync/sources");
      setSyncSources(data.sources);
      if (data.default_source_id) {
        setSelectedSourceId(data.default_source_id);
      }
    } catch {
      /* backend may not be running */
    }
  }

  async function handleSync() {
    setSyncing(true);
    setSyncMessage(null);
    try {
      const result = await api.post<ContentSyncResponse>("/content/sync", {
        source_id: selectedSourceId,
        options: {},
      });
      setSyncMessage(result.message);
      await loadContentStats();
    } catch (err) {
      setSyncMessage(
        err instanceof Error ? `Sync failed: ${err.message}` : "Sync failed"
      );
    } finally {
      setSyncing(false);
    }
  }

  const selectedSource =
    syncSources.find((source) => source.id === selectedSourceId) ?? null;

  return (
    <div className={styles.container}>
      <div className={styles.pageIntro}>
        <h2 className={styles.pageTitle}>Content</h2>
        <p className={styles.description}>
          Track the loaded domain index and keep the sync pipeline extensible even
          though Kai Project is still the only active source today.
        </p>
      </div>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Content Database</h3>
        <div className={`glass-card ${styles.syncCard}`}>
          <div className={styles.syncInfo}>
            {contentStats ? (
              <>
                <p className={styles.syncDescription}>
                  <strong>{contentStats.domain_name}</strong> — local content index
                  currently loaded for this domain.
                </p>
                <p className={styles.syncStats}>
                  {contentStats.schools_count} schools · {contentStats.questions_count}{" "}
                  questions · {contentStats.sources_count} predefined sources
                </p>
              </>
            ) : (
              <p className={styles.muted}>Loading stats…</p>
            )}
          </div>

          <div className={styles.field}>
            <label className={styles.label}>Sync Source</label>
            <select
              className={styles.select}
              value={selectedSourceId}
              onChange={(event) => setSelectedSourceId(event.target.value)}
              disabled={syncSources.length === 0 || syncing}
            >
              {syncSources.map((source) => (
                <option key={source.id} value={source.id} disabled={!source.enabled}>
                  {source.name}
                </option>
              ))}
            </select>
            {selectedSource && (
              <p className={styles.inlineMeta}>
                {selectedSource.description} · {selectedSource.kind}
                {selectedSource.is_default ? " · default" : ""}
              </p>
            )}
          </div>

          <div className={styles.syncActions}>
            <button className="btn-primary" onClick={handleSync} disabled={syncing}>
              {syncing ? "Syncing…" : "Run Sync"}
            </button>
          </div>

          {syncMessage && (
            <p
              className={
                syncMessage.startsWith("Sync failed") ? styles.error : styles.syncSuccess
              }
            >
              {syncMessage}
            </p>
          )}
        </div>
      </section>
    </div>
  );
}
