import styles from "./page.module.css";

export default function SchoolsPage() {
  return (
    <div className={styles.container}>
      <h1 className={styles.heading}>Schools</h1>
      <p className={styles.description}>
        Explore Japanese universities, graduate programs, and exam information.
        Compare schools and find the right fit for your goals.
      </p>

      {/* TODO: Implement school browser
          - School list with search and filters
          - School profile view (programs, exams, links)
          - Comparison view
          - Load data from /api/content/schools */}

      <div className={`glass-card ${styles.placeholder}`}>
        <p className={styles.placeholderText}>
          School explorer coming soon. Content artifacts will be loaded from The
          Kai Project.
        </p>
      </div>
    </div>
  );
}
