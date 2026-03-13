import styles from "./page.module.css";
import Link from "next/link";

const features = [
  {
    title: "School Explorer",
    description: "Browse schools, graduate programs, and exam differences",
    href: "/schools/",
    icon: "🏫",
  },
  {
    title: "Practice",
    description:
      "Practice past exam questions by school, subject, and year",
    href: "/practice/",
    icon: "📝",
  },
  {
    title: "Study Chat",
    description:
      "Chat with your local AI study assistant for guidance and explanations",
    href: "/chat/",
    icon: "💬",
  },
  {
    title: "Review",
    description: "Track mistakes, review weak areas, and measure progress",
    href: "/review/",
    icon: "📊",
  },
];

export default function HomePage() {
  return (
    <div className={styles.container}>
      <section className={styles.hero}>
        <h1 className={styles.title}>
          <span className={styles.kai}>Kai</span> The Kai Seeker
        </h1>
        <p className={styles.tagline}>
          Countless questions without, one Kai within — a local-first study
          agent for Japanese graduate entrance exam preparation.
        </p>
        <div className={styles.heroActions}>
          <Link href="/chat/" className="btn-primary">
            Start Studying
          </Link>
          <Link href="/schools/" className={styles.btnSecondary}>
            Browse Schools
          </Link>
        </div>
      </section>

      <section className={styles.features}>
        {features.map((f) => (
          <Link key={f.href} href={f.href} className={`glass-card ${styles.featureCard}`}>
            <span className={styles.featureIcon}>{f.icon}</span>
            <h3 className={styles.featureTitle}>{f.title}</h3>
            <p className={styles.featureDesc}>{f.description}</p>
          </Link>
        ))}
      </section>

      <section className={styles.about}>
        <p>
          The Kai Seeker is part of{" "}
          <a
            href="https://runjp.com"
            target="_blank"
            rel="noopener noreferrer"
          >
            The Kai Project
          </a>{" "}
          ecosystem. Everything runs locally on your machine — your data, your
          API keys, your study journey.
        </p>
      </section>

      <footer className={styles.brandFooter}>
        <span className={styles.brandMark}>Kai</span>
        <span className={styles.brandLabel}>
          The Kai Seeker (解を求める者) ·{" "}
          <a
            href="https://github.com/Myyura/the_kai_seeker"
            target="_blank"
            rel="noopener noreferrer"
          >
            Open Source
          </a>{" "}
          under AGPL-3.0
        </span>
      </footer>
    </div>
  );
}
