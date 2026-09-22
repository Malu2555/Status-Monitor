/**
 * Regenerate src/api/types.ts from the backend's exported OpenAPI schema.
 *
 * Tolerates a missing backend/openapi.json (fresh clone without a database
 * ready): it warns and exits 0 instead of failing `npm install`/`npm run build`.
 *
 *  1. backend:  python manage.py export_openapi --output openapi.json
 *  2. frontend: npm run api:gen
 */
import { execSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const frontendDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const schema = resolve(frontendDir, "../backend/openapi.json");
const output = resolve(frontendDir, "src/api/types.ts");

if (!existsSync(schema)) {
  console.warn(
    "[api:gen] backend/openapi.json not found — skipping generation.",
    "\n          Generate it with: python manage.py export_openapi",
  );
  process.exit(0);
}

execSync(`openapi-typescript "${schema}" -o "${output}"`, { stdio: "inherit" });
