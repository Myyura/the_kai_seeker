import { DataNav } from "./_components/data-nav";
import styles from "./layout.module.css";

export default function DataLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className={styles.shell}>
      <div className={styles.hero}>
        <h1 className={styles.heading}>Data Admin</h1>
        <p className={styles.description}>
          Inspect local runtime data and clean up artifacts without dropping into
          SQLite or filesystem tooling.
        </p>
      </div>
      <div className={styles.body}>
        <DataNav />
        <div className={styles.content}>{children}</div>
      </div>
    </div>
  );
}
