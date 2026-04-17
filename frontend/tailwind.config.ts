import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0f172a",
        slate: "#334155",
        steel: "#475569",
        cloud: "#e2e8f0",
        frost: "#f8fafc",
        linen: "#f8fafc",
        ember: "#2563eb",
        pine: "#1d4ed8",
        mist: "#dbeafe",
      },
      boxShadow: {
        panel: "0 18px 44px rgba(15, 23, 42, 0.08)",
        soft: "0 10px 24px rgba(15, 23, 42, 0.06)",
      },
      fontFamily: {
        sans: ["\"Space Grotesk\"", "\"Segoe UI\"", "sans-serif"],
        mono: ["\"IBM Plex Mono\"", "\"Consolas\"", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
