import styles from "./layout.module.css";
import { SettingsNav } from "./_components/settings-nav";

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className={styles.shell}>
      <div className={styles.hero}>
        <h1 className={styles.heading}>Settings</h1>
        <p className={styles.description}>
          Configure model providers, content sync, and extension metadata without
          mixing them into one control panel.
        </p>
      </div>
      <div className={styles.body}>
        <SettingsNav />
        <div className={styles.content}>{children}</div>
      </div>
    </div>
  );
}
