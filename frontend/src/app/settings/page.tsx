"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "./page.module.css";

interface Provider {
  id: number;
  provider: string;
  base_url: string | null;
  model: string | null;
  is_active: boolean;
}

interface ContentStats {
  loaded: boolean;
  schools_count: number;
  questions_count: number;
  domain_id: string;
  domain_name: string;
  sources_count: number;
}

interface ExtTool {
  name: string;
  description: string;
  type: "tool";
}

interface ExtSkill {
  name: string;
  description: string;
  type: "skill";
  source: string;
  trigger: string;
  allowed_tools: string[];
}

interface ExtensionsData {
  tools: ExtTool[];
  skills: ExtSkill[];
}

const PROVIDER_PRESETS: Record<string, { base_url: string; model: string }> = {
  openai: { base_url: "https://api.openai.com/v1", model: "gpt-4o-mini" },
  deepseek: { base_url: "https://api.deepseek.com/v1", model: "deepseek-chat" },
  gemini: { base_url: "https://generativelanguage.googleapis.com/v1beta", model: "gemini-2.5-flash" },
  "openai-compatible": { base_url: "", model: "" },
};

export default function SettingsPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(true);
  const [testResult, setTestResult] = useState<Record<number, boolean | null>>({});

  const [form, setForm] = useState({
    provider: "openai",
    api_key: "",
    base_url: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [contentStats, setContentStats] = useState<ContentStats | null>(null);
  const [syncing, setSyncing] = useState(false);
  const [syncMessage, setSyncMessage] = useState<string | null>(null);

  const [extensions, setExtensions] = useState<ExtensionsData | null>(null);
  const [reloading, setReloading] = useState(false);
  const [reloadMessage, setReloadMessage] = useState<string | null>(null);

  useEffect(() => {
    loadProviders();
    loadContentStats();
    loadExtensions();
  }, []);

  async function loadProviders() {
    try {
      const data = await api.get<Provider[]>("/providers/");
      setProviders(data);
    } catch {
      /* backend may not be running */
    } finally {
      setLoading(false);
    }
  }

  function onPresetChange(provider: string) {
    const preset = PROVIDER_PRESETS[provider];
    setForm((f) => ({
      ...f,
      provider,
      base_url: preset?.base_url ?? f.base_url,
      model: preset?.model ?? f.model,
    }));
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSaving(true);
    try {
      await api.post("/providers/", {
        provider: form.provider,
        api_key: form.api_key,
        base_url: form.base_url || null,
        model: form.model || null,
      });
      setForm((f) => ({ ...f, api_key: "" }));
      await loadProviders();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save");
    } finally {
      setSaving(false);
    }
  }

  async function handleTest(id: number) {
    setTestResult((prev) => ({ ...prev, [id]: null }));
    try {
      const res = await api.post<{ success: boolean }>(`/providers/${id}/test`);
      setTestResult((prev) => ({ ...prev, [id]: res.success }));
    } catch {
      setTestResult((prev) => ({ ...prev, [id]: false }));
    }
  }

  async function handleDelete(id: number) {
    try {
      await api.delete(`/providers/${id}`);
      await loadProviders();
    } catch {
      /* ignore */
    }
  }

  async function loadContentStats() {
    try {
      const data = await api.get<ContentStats>("/content/stats");
      setContentStats(data);
    } catch {
      /* backend may not be running */
    }
  }

  async function handleSync() {
    setSyncing(true);
    setSyncMessage(null);
    try {
      const result = await api.post<{ message: string }>("/content/sync");
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

  async function loadExtensions() {
    try {
      const data = await api.get<ExtensionsData>("/settings/extensions");
      setExtensions(data);
    } catch {
      /* backend may not be running */
    }
  }

  async function handleReloadExtensions() {
    setReloading(true);
    setReloadMessage(null);
    try {
      const result = await api.post<{ message: string }>(
        "/settings/extensions/reload"
      );
      setReloadMessage(result.message);
      await loadExtensions();
    } catch (err) {
      setReloadMessage(
        err instanceof Error
          ? `Reload failed: ${err.message}`
          : "Reload failed"
      );
    } finally {
      setReloading(false);
    }
  }

  async function handleSetActive(id: number) {
    for (const p of providers) {
      if (p.is_active && p.id !== id) {
        await api.patch(`/providers/${p.id}`, { is_active: false });
      }
    }
    await api.patch(`/providers/${id}`, { is_active: true });
    await loadProviders();
  }

  return (
    <div className={styles.container}>
      <h1 className={styles.heading}>Settings</h1>
      <p className={styles.description}>
        Configure your LLM provider to enable the study assistant. Your API keys
        are stored locally and never leave your machine.
      </p>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Add Provider</h2>
        <form onSubmit={handleSave} className={`glass-card ${styles.form}`}>
          <div className={styles.field}>
            <label className={styles.label}>Provider</label>
            <select
              className={styles.select}
              value={form.provider}
              onChange={(e) => onPresetChange(e.target.value)}
            >
              <option value="openai">OpenAI</option>
              <option value="deepseek">DeepSeek</option>
              <option value="gemini">Google Gemini</option>
              <option value="openai-compatible">OpenAI Compatible</option>
            </select>
          </div>

          <div className={styles.field}>
            <label className={styles.label}>API Key</label>
            <input
              className={styles.input}
              type="password"
              placeholder="sk-..."
              value={form.api_key}
              onChange={(e) => setForm((f) => ({ ...f, api_key: e.target.value }))}
              required
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label}>Base URL</label>
            <input
              className={styles.input}
              type="url"
              placeholder="https://api.openai.com/v1"
              value={form.base_url}
              onChange={(e) => setForm((f) => ({ ...f, base_url: e.target.value }))}
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label}>Model</label>
            <input
              className={styles.input}
              type="text"
              placeholder="gpt-4o-mini"
              value={form.model}
              onChange={(e) => setForm((f) => ({ ...f, model: e.target.value }))}
            />
          </div>

          {error && <p className={styles.error}>{error}</p>}

          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? "Saving…" : "Save Provider"}
          </button>
        </form>
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Configured Providers</h2>
        {loading ? (
          <p className={styles.muted}>Loading…</p>
        ) : providers.length === 0 ? (
          <p className={styles.muted}>
            No providers configured yet. Add one above to get started.
          </p>
        ) : (
          <div className={styles.providerList}>
            {providers.map((p) => (
              <div key={p.id} className={`glass-card ${styles.providerCard}`}>
                <div className={styles.providerInfo}>
                  <span className={styles.providerName}>
                    {p.provider}
                    {p.is_active && (
                      <span className={styles.activeBadge}>Active</span>
                    )}
                  </span>
                  <span className={styles.providerMeta}>
                    {p.model ?? "default model"}
                    {p.base_url ? ` · ${p.base_url}` : ""}
                  </span>
                </div>
                <div className={styles.providerActions}>
                  {!p.is_active && (
                    <button
                      className={styles.btnSmall}
                      onClick={() => handleSetActive(p.id)}
                    >
                      Set Active
                    </button>
                  )}
                  <button
                    className={styles.btnSmall}
                    onClick={() => handleTest(p.id)}
                  >
                    {testResult[p.id] === null
                      ? "Testing…"
                      : testResult[p.id] === true
                        ? "Connected"
                        : testResult[p.id] === false
                          ? "Failed"
                          : "Test"}
                  </button>
                  <button
                    className={`${styles.btnSmall} ${styles.btnDanger}`}
                    onClick={() => handleDelete(p.id)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Content Database</h2>
        <div className={`glass-card ${styles.syncCard}`}>
          <div className={styles.syncInfo}>
            {contentStats && (
              <p className={styles.syncDescription}>
                <strong>{contentStats.domain_name}</strong> — Exam question index from{" "}
                <a
                  href="https://github.com/Myyura/the_kai_project"
                  target="_blank"
                  rel="noopener noreferrer"
                  className={styles.link}
                >
                  The Kai Project
                </a>
                . Sync to get the latest questions.
              </p>
            )}
            {contentStats && (
              <p className={styles.syncStats}>
                {contentStats.schools_count} schools · {contentStats.questions_count} questions · {contentStats.sources_count} predefined sources
              </p>
            )}
            {!contentStats && (
              <p className={styles.muted}>Loading stats…</p>
            )}
          </div>
          <div className={styles.syncActions}>
            <button
              className="btn-primary"
              onClick={handleSync}
              disabled={syncing}
            >
              {syncing ? "Syncing…" : "Sync from GitHub"}
            </button>
          </div>
          {syncMessage && (
            <p
              className={
                syncMessage.startsWith("Sync failed")
                  ? styles.error
                  : styles.syncSuccess
              }
            >
              {syncMessage}
            </p>
          )}
        </div>
      </section>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <h2 className={styles.sectionTitle}>Extensions</h2>
            <p className={styles.description}>
              Tools execute code (fetch pages, search database). Skills inject
              domain knowledge into the assistant&apos;s reasoning. Add your own
              in <code className={styles.code}>user_extensions/</code>.
            </p>
          </div>
          <button
            className="btn-primary"
            onClick={handleReloadExtensions}
            disabled={reloading}
          >
            {reloading ? "Reloading…" : "Reload"}
          </button>
        </div>
        {reloadMessage && (
          <p
            className={
              reloadMessage.startsWith("Reload failed")
                ? styles.error
                : styles.syncSuccess
            }
          >
            {reloadMessage}
          </p>
        )}

        {extensions ? (
          <div className={styles.extensionGrid}>
            {extensions.tools.map((t) => (
              <div key={t.name} className={`glass-card ${styles.extCard}`}>
                <div className={styles.extHeader}>
                  <span className={styles.extName}>{t.name}</span>
                  <span className={`${styles.extBadge} ${styles.extBadgeTool}`}>
                    Tool
                  </span>
                </div>
                <p className={styles.extDesc}>{t.description}</p>
              </div>
            ))}
            {extensions.skills.map((s) => (
              <div key={s.name} className={`glass-card ${styles.extCard}`}>
                <div className={styles.extHeader}>
                  <span className={styles.extName}>{s.name}</span>
                  <span className={`${styles.extBadge} ${styles.extBadgeSkill}`}>
                    Skill
                  </span>
                  <span className={`${styles.extBadge} ${styles.extBadgeSource}`}>
                    {s.source}
                  </span>
                </div>
                <p className={styles.extDesc}>{s.description}</p>
                {s.trigger && (
                  <p className={styles.extMeta}>
                    Triggers: {s.trigger}
                  </p>
                )}
                {s.allowed_tools.length > 0 && (
                  <p className={styles.extMeta}>
                    Uses: {s.allowed_tools.join(", ")}
                  </p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <p className={styles.muted}>Loading extensions…</p>
        )}
      </section>
    </div>
  );
}
