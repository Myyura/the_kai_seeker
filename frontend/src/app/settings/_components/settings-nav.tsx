"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "../layout.module.css";

const items = [
  { href: "/settings/", label: "Overview" },
  { href: "/settings/providers/", label: "Providers" },
  { href: "/settings/content/", label: "Content" },
  { href: "/settings/extensions/", label: "Extensions" },
];

export function SettingsNav() {
  const pathname = usePathname();

  return (
    <nav className={styles.navCard}>
      <div className={styles.navHeader}>Sections</div>
      <div className={styles.navList}>
        {items.map((item) => {
          const isActive =
            item.href === "/settings/"
              ? pathname === "/settings" || pathname === "/settings/"
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`${styles.navLink} ${isActive ? styles.navLinkActive : ""}`}
            >
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
