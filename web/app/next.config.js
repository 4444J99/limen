/** @type {import('next').NextConfig} */
const path = require("path");

const nextConfig = {
  output: "export",
  images: { unoptimized: true },
  outputFileTracingRoot: path.join(__dirname),
};

module.exports = nextConfig;
