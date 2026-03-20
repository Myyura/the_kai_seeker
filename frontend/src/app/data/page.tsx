"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "./page.module.css";

interface AdminResource {
  id: string;
  label: string;
  description: string;
  href: string;
  available: boolean;
}

interface AdminResourcesResponse {
  resources: AdminResource[];
}

export default function DataOverviewPage() {
  const [resources, setResources] = useState<AdminResource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void loadResources();
  }, []);

  async function loadResources() {
    setError(null);
    try {
      const data = await api.get<AdminResourcesResponse>("/admin/resources");
      setResources(data.resources);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load admin resources");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={styles.container}>
      <div className={styles.pageIntro}>
        <h2 className={styles.pageTitle}>Overview</h2>
        <p className={styles.description}>
          Start with PDFs in phase one, while keeping a stable resource model for
          future conversation, provider, and study-target admin pages.
        </p>
      </div>

      {loading ? (
        <p className={styles.muted}>Loading resources…</p>
      ) : error ? (
        <div className={styles.emptyState}>
          Unable to load admin resources right now. {error}
        </div>
      ) : resources.length === 0 ? (
        <div className={styles.emptyState}>No admin resources are registered yet.</div>
      ) : (
        <div className={styles.overviewGrid}>
          {resources.map((resource) => (
            <Link
              key={resource.id}
              href={resource.href}
              className={`glass-card ${styles.overviewCard} ${
                resource.available ? "" : styles.overviewCardDisabled
              }`}
            >
              <span className={styles.overviewMeta}>Admin Resource</span>
              <h3 className={styles.overviewTitle}>{resource.label}</h3>
              <p className={styles.overviewDesc}>{resource.description}</p>
              <span
                className={`${styles.overviewBadge} ${
                  resource.available ? "" : styles.overviewBadgeMuted
                }`}
              >
                {resource.available ? "Available" : "Planned"}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
