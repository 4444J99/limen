/** @type {import('next').NextConfig} */
const path = require("path");

// The heartbeat's web-refresh beat (scripts/refresh-web.sh) only needs a fast static
// data re-export, not type-correctness — that is CI's job. `next build`'s TypeScript
// typecheck is the slow phase that overran the beat's 90s timeout ("Running TypeScript…"
// → "build failed/timed out — keeping previous export"). When the beat sets
// LIMEN_WEB_SKIP_TYPECHECK=1 we skip it; a normal/CI build (flag unset) still typechecks.
const skipTypecheck = process.env.LIMEN_WEB_SKIP_TYPECHECK === "1";

// Single source of truth for the backend runtime URL: env override → committed runtime.config.json
// (same resolution as cli/src/limen/doctor.py + generate-static-data.mjs). Embedding it here means the
// static export carries the real Cloudflare Worker URL even when the LIMEN_API_URL repo var is unset.
const runtimeApiUrl =
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.LIMEN_API_URL ||
  (() => {
    try {
      return (
        JSON.parse(
          require("fs").readFileSync(path.join(__dirname, "..", "..", "runtime.config.json"), "utf8")
        ).apiUrl || ""
      );
    } catch {
      return "";
    }
  })();

const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  outputFileTracingRoot: path.join(__dirname),
  ...(runtimeApiUrl ? { env: { NEXT_PUBLIC_API_URL: runtimeApiUrl } } : {}),
  ...(skipTypecheck
    ? { typescript: { ignoreBuildErrors: true }, eslint: { ignoreDuringBuilds: true } }
    : {}),
};

module.exports = nextConfig;
