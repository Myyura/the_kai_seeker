import Link from "next/link";
import styles from "../page.module.css";

interface ComingSoonPanelProps {
  title: string;
  description: string;
  nextItems: string[];
}

export function ComingSoonPanel({
  title,
  description,
  nextItems,
}: ComingSoonPanelProps) {
  return (
    <div className={styles.container}>
      <div className={styles.pageIntro}>
        <h2 className={styles.pageTitle}>{title}</h2>
        <p className={styles.description}>{description}</p>
      </div>

      <div className={`glass-card ${styles.placeholderCard}`}>
        <div className={styles.placeholderMeta}>Phase Two Foundation</div>
        <h3 className={styles.placeholderTitle}>This resource is not live yet.</h3>
        <p className={styles.placeholderText}>
          The route and navigation slot already exist so the data admin area can
          grow without another information architecture reset.
        </p>

        <div className={styles.placeholderSection}>
          <div className={styles.placeholderSectionTitle}>Planned Scope</div>
          <ul className={styles.placeholderList}>
            {nextItems.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>

        <div className={styles.placeholderActions}>
          <Link href="/data/" className={styles.btnSmall}>
            Back to Overview
          </Link>
          <Link href="/data/pdfs/" className={styles.btnSmall}>
            Open PDFs
          </Link>
        </div>
      </div>
    </div>
  );
}
