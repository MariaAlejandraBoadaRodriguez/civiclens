import type { Config } from "tailwindcss";

// Every value maps to a CSS variable in styles/tokens.css (source: approved mockups).
const v = (name: string) => `var(--${name})`;

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ground: v("color-ground"),
        surface: v("color-surface"),
        subtle: v("color-subtle"),
        track: v("color-track"),
        ink: {
          DEFAULT: v("color-ink"),
          raised: v("color-ink-raised"),
          text: v("color-ink-text"),
          line: v("color-ink-line"),
          dim: v("color-ink-dim"),
          accent: v("color-ink-accent"),
        },
        text: v("color-text"),
        muted: v("color-muted"),
        neutral: v("color-neutral-text"),
        line: { DEFAULT: v("color-line"), strong: v("color-line-strong"), dropzone: v("color-dropzone") },
        primary: {
          DEFAULT: v("color-primary"),
          dark: v("color-primary-dark"),
          tint: v("color-primary-tint"),
          soft: v("color-primary-soft"),
          border: v("color-primary-border"),
        },
        flag: {
          DEFAULT: v("color-flag"),
          tint: v("color-flag-tint"),
          text: v("color-flag-text"),
          border: v("color-flag-border"),
          strong: v("color-flag-border-strong"),
          hover: v("color-flag-hover"),
        },
        success: { DEFAULT: v("color-success"), tint: v("color-success-tint"), text: v("color-success-text") },
        code: { DEFAULT: v("color-code"), text: v("color-code-text") },
      },
      fontFamily: {
        sans: [v("font-sans")],
        mono: [v("font-mono")],
      },
      borderRadius: {
        chip: v("radius-chip"),
        nav: v("radius-nav"),
        control: v("radius-control"),
        panel: v("radius-panel"),
        card: v("radius-card"),
      },
      maxWidth: { container: v("container-max") },
      minHeight: { touch: v("touch-target") },
      minWidth: { touch: v("touch-target") },
    },
  },
  plugins: [],
};

export default config;
