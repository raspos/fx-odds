export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: { extend: { colors: {
    bg: "var(--bg)", surface: "var(--surface)", surface2: "var(--surface-2)", line: "var(--line)",
    ink: "var(--ink)", ink2: "var(--ink-2)", ink3: "var(--ink-3)", up: "var(--up)", down: "var(--down)", accent: "var(--accent)",
    warnbg: "var(--warn-bg)", warnink: "var(--warn-ink)", warnline: "var(--warn-line)",
  }, fontFamily: { sans: ["Pretendard", "Noto Sans KR", "system-ui", "sans-serif"] } } },
};
