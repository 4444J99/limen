/** @type {import('next').NextConfig} */
const path = require("path");

// The heartbeat's web-refresh beat (scripts/refresh-web.sh) only needs a fast static
// data re-export, not type-correctness — that is CI's job. `next build`'s TypeScript
// typecheck is the slow phase that overran the beat's 90s timeout ("Running TypeScript…"
// → "build failed/timed out — keeping previous export"). When the beat sets
// LIMEN_WEB_SKIP_TYPECHECK=1 we skip it; a normal/CI build (flag unset) still typechecks.
const skipTypecheck = process.env.LIMEN_WEB_SKIP_TYPECHECK === "1";

const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  outputFileTracingRoot: path.join(__dirname),
  ...(skipTypecheck
    ? { typescript: { ignoreBuildErrors: true }, eslint: { ignoreDuringBuilds: true } }
    : {}),
};

module.exports = nextConfig;
