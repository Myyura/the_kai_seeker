import styles from "./page.module.css";

export default function PracticePage() {
  return (
    <div className={styles.container}>
      <h1 className={styles.heading}>Practice</h1>
      <p className={styles.description}>
        Practice past exam questions organized by school, subject, and year.
        Track your answers and build understanding through repetition.
      </p>

      {/* TODO: Implement practice interface
          - Question filter panel (school, subject, year, tags)
          - Question display with answer toggle
          - Answer submission and self-grading
          - Practice session tracking
          - Progress indicators */}

      <div className={`glass-card ${styles.placeholder}`}>
        <p className={styles.placeholderText}>
          Practice mode coming soon. Questions will be loaded from The Kai
          Project content artifacts.
        </p>
      </div>
    </div>
  );
}
