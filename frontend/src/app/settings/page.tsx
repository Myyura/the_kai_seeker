import Link from "next/link";
import styles from "./page.module.css";

const sections = [
  {
    href: "/settings/providers/",
    title: "Providers",
    description:
      "Add model providers, switch the active backend, and test credentials.",
    meta: "LLM configuration",
  },
  {
    href: "/settings/content/",
    title: "Content",
    description:
      "Check content index stats and run sync from an available content source.",
    meta: "Domain data",
  },
  {
    href: "/settings/extensions/",
    title: "Extensions",
    description:
      "Inspect loaded tools and skills, then reload extensions from disk.",
    meta: "Tooling and skills",
  },
];

export default function SettingsOverviewPage() {
  return (
    <div className={styles.container}>
      <div className={styles.pageIntro}>
        <h2 className={styles.pageTitle}>Overview</h2>
        <p className={styles.description}>
          Split settings by responsibility so provider setup, content sync, and
          extension metadata stay easy to reason about.
        </p>
      </div>

      <div className={styles.overviewGrid}>
        {sections.map((section) => (
          <Link key={section.href} href={section.href} className={`glass-card ${styles.overviewCard}`}>
            <span className={styles.overviewMeta}>{section.meta}</span>
            <h3 className={styles.overviewTitle}>{section.title}</h3>
            <p className={styles.overviewDesc}>{section.description}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
