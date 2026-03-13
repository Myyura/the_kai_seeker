/**
 * The Kai Seeker (解を求める者)
 * Application configuration
 * https://github.com/Myyura/the_kai_seeker — AGPL-3.0
 */

export const config = {
  apiBaseUrl:
    process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000/api",
  appTitle: process.env.NEXT_PUBLIC_APP_TITLE || "The Kai Seeker",
  appDescription:
    "Local-first open-source study agent for Japanese graduate entrance exam preparation",
  projectName: "the-kai-seeker",
  projectUrl: "https://github.com/Myyura/the_kai_seeker",
  version: "0.1.0",
  license: "AGPL-3.0",
} as const;
