"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import styles from "./sidebar.module.css";

const navItems = [
  { href: "/", label: "Home", icon: "🏠" },
  { href: "/chat/", label: "Chat", icon: "💬" },
  { href: "/schools/", label: "Schools", icon: "🏫" },
  { href: "/practice/", label: "Practice", icon: "📝" },
  { href: "/review/", label: "Review", icon: "📊" },
  { href: "/settings/", label: "Settings", icon: "⚙️" },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className={styles.sidebar}>
      <div className={styles.brand}>
        <Link href="/" className={styles.brandLink}>
          <span className={styles.brandIcon}>Kai</span>
          <span className={styles.brandText}>The Kai Seeker</span>
        </Link>
      </div>

      <nav className={styles.nav}>
        {navItems.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/" || pathname === ""
              : pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`${styles.navItem} ${isActive ? styles.active : ""}`}
            >
              <span className={styles.navIcon}>{item.icon}</span>
              <span className={styles.navLabel}>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className={styles.footer}>
        <a
          href="https://github.com/Myyura/the_kai_seeker"
          target="_blank"
          rel="noopener noreferrer"
          className={styles.footerLink}
          title="The Kai Seeker — Open Source under AGPL-3.0"
        >
          <span className={styles.footerBrand}>Kai</span>
          <span className={styles.footerText}>
            The Kai Seeker v0.1.0
          </span>
        </a>
        <span className={styles.footerSub}>AGPL-3.0 · Local Mode</span>
      </div>
    </aside>
  );
}
