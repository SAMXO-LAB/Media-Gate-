import type { Config } from "tailwindcss";

export default {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { DEFAULT: "#0B1B3A", soft: "#3B4A6B", mute: "#6B7894" },
        brand: {
          50: "#F2F6FF",
          100: "#E3ECFF",
          200: "#C6D7FF",
          300: "#9CB9FF",
          400: "#6B93FF",
          500: "#3D6DFF",
          600: "#1F4FF0",
          700: "#173CC4",
          800: "#15329B",
          900: "#132B78",
        },
        line: "#E3E8F2",
        canvas: "#FAFBFE",
      },
      fontFamily: {
        display: ["var(--font-display)", "ui-sans-serif", "system-ui"],
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(11,27,58,0.04), 0 8px 24px -12px rgba(11,27,58,0.12)",
        lift: "0 2px 4px rgba(11,27,58,0.04), 0 24px 48px -24px rgba(23,60,196,0.28)",
        ring: "0 0 0 4px rgba(61,109,255,0.18)",
      },
      borderRadius: { xl2: "1.25rem" },
      keyframes: {
        shimmer: { "100%": { transform: "translateX(100%)" } },
        indeterminate: { "0%": { transform: "translateX(-100%)" }, "100%": { transform: "translateX(250%)" } },
      },
      animation: {
        shimmer: "shimmer 1.6s infinite",
        indeterminate: "indeterminate 1.4s ease-in-out infinite",
      },
    },
  },
  plugins: [],
} satisfies Config;
