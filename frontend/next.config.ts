import type { NextConfig } from "next";

const backend = process.env.CONTROLIQ_API_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  // The browser only talks to this origin; API calls are proxied so the session cookie stays first-party.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backend}/api/:path*` }];
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "no-referrer" },
        ],
      },
    ];
  },
};

export default nextConfig;
