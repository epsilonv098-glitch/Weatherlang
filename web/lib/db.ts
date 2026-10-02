import { neon } from "@neondatabase/serverless";

/** Neon HTTP client. DATABASE_URL comes from the environment only. */
export function getSql() {
  const url = process.env.DATABASE_URL;
  if (!url) throw new Error("DATABASE_URL is not set");
  return neon(url);
}

/** Postgres numeric columns arrive as strings; convert (null stays null). */
export const num = (v: unknown): number | null =>
  v === null || v === undefined ? null : Number(v);
