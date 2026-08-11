import type { NextConfig } from "next";

const apiUpstream = (process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000").replace(
  /\/$/,
  "",
);

const nextConfig: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  async redirects() {
    return [
      {
        source: "/login",
        destination: "/?login=1",
        permanent: false,
      },
    ];
  },
  async rewrites() {
    // Browser → same-origin /api-backend/* → local API (avoids VPN/LAN :8000 blocks).
    return [
      {
        source: "/api-backend/:path*",
        destination: `${apiUpstream}/:path*`,
      },
    ];
  },
};

export default nextConfig;
