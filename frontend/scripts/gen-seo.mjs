/**
 * Regenerate public/robots.txt and public/sitemap.xml from the canonical URL.
 *
 * Runs in `prebuild` next to gen-api.mjs so the crawler-facing files can never
 * drift from the URL the app advertises. Override the base with VITE_SITE_URL.
 *
 *   frontend: npm run seo:gen
 */
import { writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const frontendDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SITE_URL = (
  process.env.VITE_SITE_URL || "https://status-monitor-alpha.vercel.app"
).replace(/\/+$/, "");

// Public, indexable routes — keep in sync with src/router/index.js.
const PAGES = [
  { path: "/", changefreq: "weekly", priority: "1.0" },
  { path: "/status", changefreq: "hourly", priority: "0.8" },
  { path: "/terms", changefreq: "yearly", priority: "0.3" },
  { path: "/privacy", changefreq: "yearly", priority: "0.3" },
];

// App and credential routes: reachable, never crawled.
const PRIVATE = [
  "/dashboard",
  "/account",
  "/security",
  "/notifications",
  "/status-pages",
  "/maintenance",
  "/login",
  "/register",
  "/verify-email",
  "/reset-password",
];

const lastmod = new Date().toISOString().slice(0, 10);

const sitemap = `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
${PAGES.map(
  (page) => `  <url>
    <loc>${SITE_URL}${page.path}</loc>
    <lastmod>${lastmod}</lastmod>
    <changefreq>${page.changefreq}</changefreq>
    <priority>${page.priority}</priority>
  </url>`,
).join("\n")}
</urlset>
`;

const robots = `# ${SITE_URL}
User-agent: *
Allow: /
${PRIVATE.map((path) => `Disallow: ${path}`).join("\n")}

Sitemap: ${SITE_URL}/sitemap.xml
`;

writeFileSync(resolve(frontendDir, "public/sitemap.xml"), sitemap);
writeFileSync(resolve(frontendDir, "public/robots.txt"), robots);
console.log(`[seo:gen] wrote robots.txt + sitemap.xml for ${SITE_URL}`);
