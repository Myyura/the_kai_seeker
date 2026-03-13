import styles from "./page.module.css";

export default function ReviewPage() {
  return (
    <div className={styles.container}>
      <h1 className={styles.heading}>Review</h1>
      <p className={styles.description}>
        Review your mistakes, identify weak areas, and track your study
        progress over time.
      </p>

      {/* TODO: Implement review interface
          - Mistake list with filters
          - Weak area analysis
          - Progress charts / statistics
          - Spaced repetition suggestions
          - Re-practice from mistakes */}

      <div className={`glass-card ${styles.placeholder}`}>
        <p className={styles.placeholderText}>
          Review dashboard coming soon. Complete practice sessions to start
          building your review data.
        </p>
      </div>
    </div>
  );
}
