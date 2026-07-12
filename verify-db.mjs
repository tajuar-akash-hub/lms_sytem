import fs from "node:fs";
import { neon } from "@neondatabase/serverless";

const env = fs.readFileSync(".env.local", "utf8");
const match = env.match(/DATABASE_URL="([^"]+)"/);

if (!match) {
  throw new Error("DATABASE_URL not found in .env.local");
}

const sql = neon(match[1]);
const result = await sql`SELECT 1 AS connected`;

console.log("Database connection verified:", result);
