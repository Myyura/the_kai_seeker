/*
 * The Kai Seeker (解を求める者)
 * Root layout — https://github.com/Myyura/the_kai_seeker
 * Licensed under AGPL-3.0
 */

import type { Metadata } from "next";
import { config } from "@/lib/config";
import "@/styles/globals.css";
import styles from "./layout.module.css";
import { Sidebar } from "@/components/sidebar";

export const metadata: Metadata = {
  title: config.appTitle,
  description: config.appDescription,
  icons: {
    icon: "/favicon.svg",
  },
  other: {
    "application-name": "The Kai Seeker",
    generator: "The Kai Seeker v0.1.0",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-Hans" data-kai-seeker="v0.1.0">
      <head>
        {/* The Kai Seeker (解を求める者) — AGPL-3.0 — https://github.com/Myyura/the_kai_seeker */}
        <meta name="author" content="The Kai Project Contributors" />
        <meta name="project" content="the-kai-seeker" />
      </head>
      <body>
        <div className={styles.appShell}>
          <Sidebar />
          <main className={styles.main}>{children}</main>
        </div>
      </body>
    </html>
  );
}
