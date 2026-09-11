import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow dev access from these IPs (development only)
  // Add your IP here if accessing from a different machine
  allowedDevOrigins: [
    "http://10.124.144.23:3000",
    "http://10.124.144.23",
    "10.124.144.23",
  ],
};

export default nextConfig;
