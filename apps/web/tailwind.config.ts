import type { Config } from "tailwindcss";

// Tokens taken from the approved mockups (docs/ROADMAP.md, Phase 2).
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ground: "#F4F6F8",
        surface: "#FFFFFF",
        ink: "#0F1B2D",
        text: "#1F2A37",
        muted: "#4B5563",
        line: "#D7DDE4",
        primary: { DEFAULT: "#1D4ED8", tint: "#E8EEFC", dark: "#1E3A8A" },
        flag: { DEFAULT: "#B45309", tint: "#FDF1E4", text: "#7C2D12" },
        success: "#15803D",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "monospace"],
      },
      borderRadius: { card: "12px" },
    },
  },
  plugins: [],
};

export default config;
