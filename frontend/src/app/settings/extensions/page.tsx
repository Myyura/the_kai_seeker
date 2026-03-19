"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import styles from "../page.module.css";

interface ExtTool {
  name: string;
  display_name: string;
  description: string;
  activity_label: string;
  usage_guidelines: string[];
  type: "tool";
}

interface ExtSkill {
  name: string;
  display_name: string;
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

export default function SettingsExtensionsPage() {
  const [extensions, setExtensions] = useState<ExtensionsData | null>(null);
  const [reloading, setReloading] = useState(false);
  const [reloadMessage, setReloadMessage] = useState<string | null>(null);

  useEffect(() => {
    loadExtensions();
  }, []);

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
      const result = await api.post<{ message: string }>("/settings/extensions/reload");
      setReloadMessage(result.message);
      await loadExtensions();
    } catch (err) {
      setReloadMessage(
        err instanceof Error ? `Reload failed: ${err.message}` : "Reload failed"
      );
    } finally {
      setReloading(false);
    }
  }

  return (
    <div className={styles.container}>
      <div className={styles.pageIntro}>
        <h2 className={styles.pageTitle}>Extensions</h2>
        <p className={styles.description}>
          Inspect the loaded tools and skills with their display names, then reload
          metadata from disk when extension files change.
        </p>
      </div>

      <section className={styles.section}>
        <div className={styles.sectionHeader}>
          <div>
            <h3 className={styles.sectionTitle}>Loaded Extensions</h3>
            <p className={styles.description}>
              Tools execute code. Skills inject domain guidance. User files still live
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
              reloadMessage.startsWith("Reload failed") ? styles.error : styles.syncSuccess
            }
          >
            {reloadMessage}
          </p>
        )}

        {extensions ? (
          <div className={styles.extensionGrid}>
            {extensions.tools.map((tool) => (
              <div key={tool.name} className={`glass-card ${styles.extCard}`}>
                <div className={styles.extHeader}>
                  <span className={styles.extName}>{tool.display_name}</span>
                  <span className={`${styles.extBadge} ${styles.extBadgeTool}`}>Tool</span>
                </div>
                <p className={styles.extMeta}>Internal: {tool.name}</p>
                <p className={styles.extMeta}>Activity: {tool.activity_label}</p>
                <p className={styles.extDesc}>{tool.description}</p>
                {tool.usage_guidelines.length > 0 && (
                  <p className={styles.extMeta}>
                    Rules: {tool.usage_guidelines.join(" ")}
                  </p>
                )}
              </div>
            ))}
            {extensions.skills.map((skill) => (
              <div key={skill.name} className={`glass-card ${styles.extCard}`}>
                <div className={styles.extHeader}>
                  <span className={styles.extName}>{skill.display_name}</span>
                  <span className={`${styles.extBadge} ${styles.extBadgeSkill}`}>Skill</span>
                  <span className={`${styles.extBadge} ${styles.extBadgeSource}`}>
                    {skill.source}
                  </span>
                </div>
                <p className={styles.extMeta}>Internal: {skill.name}</p>
                <p className={styles.extDesc}>{skill.description}</p>
                {skill.trigger && <p className={styles.extMeta}>Triggers: {skill.trigger}</p>}
                {skill.allowed_tools.length > 0 && (
                  <p className={styles.extMeta}>
                    Uses: {skill.allowed_tools.join(", ")}
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
