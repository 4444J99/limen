/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  rewrites: async () => [
    {
      source: "/api/:path*",
      destination: `${process.env.API_URL || "http://localhost:8000"}/api/:path*`,
    },
  ],
};

module.exports = nextConfig;
