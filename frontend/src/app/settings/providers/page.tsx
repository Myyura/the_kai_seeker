"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "../page.module.css";

interface Provider {
  id: number;
  provider: string;
  base_url: string | null;
  model: string | null;
  is_active: boolean;
}

const PROVIDER_PRESETS: Record<string, { base_url: string; model: string }> = {
  openai: { base_url: "https://api.openai.com/v1", model: "gpt-4o-mini" },
  deepseek: { base_url: "https://api.deepseek.com/v1", model: "deepseek-chat" },
  gemini: {
    base_url: "https://generativelanguage.googleapis.com/v1beta",
    model: "gemini-2.5-flash",
  },
  "openai-compatible": { base_url: "", model: "" },
};

export default function SettingsProvidersPage() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Record<number, boolean | null>>({});
  const [form, setForm] = useState({
    provider: "openai",
    api_key: "",
    base_url: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
  });

  useEffect(() => {
    loadProviders();
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
    setForm((current) => ({
      ...current,
      provider,
      base_url: preset?.base_url ?? current.base_url,
      model: preset?.model ?? current.model,
    }));
  }

  async function handleSave(event: React.FormEvent) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await api.post("/providers/", {
        provider: form.provider,
        api_key: form.api_key,
        base_url: form.base_url || null,
        model: form.model || null,
      });
      setForm((current) => ({ ...current, api_key: "" }));
      await loadProviders();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save provider");
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

  async function handleSetActive(id: number) {
    for (const provider of providers) {
      if (provider.is_active && provider.id !== id) {
        await api.patch(`/providers/${provider.id}`, { is_active: false });
      }
    }
    await api.patch(`/providers/${id}`, { is_active: true });
    await loadProviders();
  }

  return (
    <div className={styles.container}>
      <div className={styles.pageIntro}>
        <h2 className={styles.pageTitle}>Providers</h2>
        <p className={styles.description}>
          Manage BYOK model backends and keep one provider marked as active for the
          assistant runtime.
        </p>
      </div>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Add Provider</h3>
        <form onSubmit={handleSave} className={`glass-card ${styles.form}`}>
          <div className={styles.field}>
            <label className={styles.label}>Provider</label>
            <select
              className={styles.select}
              value={form.provider}
              onChange={(event) => onPresetChange(event.target.value)}
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
              onChange={(event) =>
                setForm((current) => ({ ...current, api_key: event.target.value }))
              }
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
              onChange={(event) =>
                setForm((current) => ({ ...current, base_url: event.target.value }))
              }
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label}>Model</label>
            <input
              className={styles.input}
              type="text"
              placeholder="gpt-4o-mini"
              value={form.model}
              onChange={(event) =>
                setForm((current) => ({ ...current, model: event.target.value }))
              }
            />
          </div>

          {error && <p className={styles.error}>{error}</p>}

          <button type="submit" className="btn-primary" disabled={saving}>
            {saving ? "Saving…" : "Save Provider"}
          </button>
        </form>
      </section>

      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Configured Providers</h3>
        {loading ? (
          <p className={styles.muted}>Loading…</p>
        ) : providers.length === 0 ? (
          <p className={styles.muted}>
            No providers configured yet. Add one above to get started.
          </p>
        ) : (
          <div className={styles.providerList}>
            {providers.map((provider) => (
              <div key={provider.id} className={`glass-card ${styles.providerCard}`}>
                <div className={styles.providerInfo}>
                  <span className={styles.providerName}>
                    {provider.provider}
                    {provider.is_active && (
                      <span className={styles.activeBadge}>Active</span>
                    )}
                  </span>
                  <span className={styles.providerMeta}>
                    {provider.model ?? "default model"}
                  </span>
                </div>
                <div className={styles.providerActions}>
                  {!provider.is_active && (
                    <button
                      className={styles.btnSmall}
                      onClick={() => handleSetActive(provider.id)}
                    >
                      Set Active
                    </button>
                  )}
                  <button
                    className={styles.btnSmall}
                    onClick={() => handleTest(provider.id)}
                  >
                    {testResult[provider.id] === null
                      ? "Testing…"
                      : testResult[provider.id] === true
                        ? "Connected"
                        : testResult[provider.id] === false
                          ? "Failed"
                          : "Test"}
                  </button>
                  <button
                    className={`${styles.btnSmall} ${styles.btnDanger}`}
                    onClick={() => handleDelete(provider.id)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
