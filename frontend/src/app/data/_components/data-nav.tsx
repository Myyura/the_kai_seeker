"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "../layout.module.css";

const items = [
  { href: "/data/", label: "Overview", available: true },
  { href: "/data/pdfs/", label: "PDFs", available: true },
  { href: "/data/conversations/", label: "Conversations", available: true },
  { href: "/data/providers/", label: "Providers", available: true },
  { href: "/data/study-targets/", label: "Study Targets", available: true },
];

export function DataNav() {
  const pathname = usePathname();

  return (
    <nav className={styles.navCard}>
      <div className={styles.navHeader}>Resources</div>
      <div className={styles.navList}>
        {items.map((item) => {
          const isActive =
            item.href === "/data/"
              ? pathname === "/data" || pathname === "/data/"
              : pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`${styles.navLink} ${
                item.available ? "" : styles.navLinkPlanned
              } ${isActive ? styles.navLinkActive : ""}`}
            >
              {item.label}
              {!item.available && <span className={styles.navSoon}>Soon</span>}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
