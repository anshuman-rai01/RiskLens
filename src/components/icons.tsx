import type { ReactNode } from "react";

const paths: Record<string, ReactNode> = {
  grid: (
    <>
      <rect x="3.5" y="3.5" width="7" height="7" rx="1.6" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="1.6" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="1.6" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="1.6" />
    </>
  ),
  wallet: (
    <>
      <path d="M3 7.5A2.5 2.5 0 0 1 5.5 5h11A2.5 2.5 0 0 1 19 7.5V9" />
      <path d="M3 7.5V17a2.5 2.5 0 0 0 2.5 2.5h13A2.5 2.5 0 0 0 21 17v-5.5A2.5 2.5 0 0 0 18.5 9H5.5A2.5 2.5 0 0 1 3 7.5Z" />
      <circle cx="16.4" cy="14.2" r="1.1" fill="currentColor" stroke="none" />
    </>
  ),
  vault: (
    <>
      <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
      <circle cx="12" cy="12" r="3.4" />
      <path d="M12 8.6V6.8M12 17.2v-1.8M15.4 12h1.8M6.8 12h1.8M14.4 9.6l1.3-1.3M8.3 15.7l1.3-1.3M14.4 14.4l1.3 1.3M8.3 8.3l1.3 1.3" />
    </>
  ),
  book: (
    <>
      <path d="M12 6.5C10.5 5 8.4 4.5 5.5 4.5c-.8 0-1.5.1-2 .2V18c.5-.1 1.2-.2 2-.2 2.9 0 5 .6 6.5 2 1.5-1.4 3.6-2 6.5-2 .8 0 1.5.1 2 .2V4.7c-.5-.1-1.2-.2-2-.2-2.9 0-5 .5-6.5 1.8Z" />
      <path d="M12 6.5v13.3" />
    </>
  ),
  gradcap: (
    <>
      <path d="m12 4 9.5 4.5L12 13 2.5 8.5 12 4Z" />
      <path d="M6.5 10.8V15c0 1.4 2.5 2.8 5.5 2.8s5.5-1.4 5.5-2.8v-4.2" />
      <path d="M21.5 8.5v5.2" />
    </>
  ),
  pulse: (
    <>
      <path d="M3 12.5h3.4l2-5.3 3.6 10.2 2.4-7 1.5 2.1H21" />
    </>
  ),
  check: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="m8.4 12.3 2.4 2.4 4.8-5.2" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4.4" />
      <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
    </>
  ),
  user: (
    <>
      <circle cx="12" cy="8.2" r="3.6" />
      <path d="M4.8 19.6c.9-3.4 3.8-5.2 7.2-5.2s6.3 1.8 7.2 5.2" />
    </>
  ),
  logout: (
    <>
      <path d="M14 4.5H7A2.5 2.5 0 0 0 4.5 7v10A2.5 2.5 0 0 0 7 19.5h7" />
      <path d="M16.5 8.5 20 12l-3.5 3.5" />
      <path d="M20 12H9.5" />
    </>
  ),
  plus: <path d="M12 5v14M5 12h14" />,
  x: <path d="m6 6 12 12M18 6 6 18" />,
  pencil: (
    <>
      <path d="M4 20l.9-3.6L16.4 4.9a1.8 1.8 0 0 1 2.6 0l.1.1a1.8 1.8 0 0 1 0 2.6L7.6 19.1 4 20Z" />
      <path d="m14.5 6.8 2.7 2.7" />
    </>
  ),
  trash: (
    <>
      <path d="M4.5 6.5h15" />
      <path d="M8 6.5V5A1.5 1.5 0 0 1 9.5 3.5h5A1.5 1.5 0 0 1 16 5v1.5" />
      <path d="M6.5 6.5 7.3 19a1.8 1.8 0 0 0 1.8 1.7h5.8A1.8 1.8 0 0 0 16.7 19l.8-12.5" />
      <path d="M10 10.5v6M14 10.5v6" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 12a8 8 0 1 1-2.3-5.6" />
      <path d="M20 3.6V8h-4.4" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3.5 5 6v5.3c0 4.6 3 7.7 7 9.2 4-1.5 7-4.6 7-9.2V6l-7-2.5Z" />
      <path d="m9 11.6 2.2 2.2 3.8-4.2" />
    </>
  ),
  eye: (
    <>
      <path d="M2.5 12S6 5.8 12 5.8 21.5 12 21.5 12 18 18.2 12 18.2 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="2.8" />
    </>
  ),
  eyeoff: (
    <>
      <path d="m4 4 16 16" />
      <path d="M9.9 5.3A9.9 9.9 0 0 1 12 5.1c6 0 9.5 6.9 9.5 6.9a17.3 17.3 0 0 1-3.1 4M6.1 6.6A16.5 16.5 0 0 0 2.5 12S6 18.9 12 18.9a9.6 9.6 0 0 0 4.1-1" />
      <path d="M9.5 9.9a2.8 2.8 0 0 0 3.9 4" />
    </>
  ),
  menu: <path d="M4 7h16M4 12h16M4 17h10" />,
  chevron: <path d="m9 5 7 7-7 7" />,
  alert: (
    <>
      <path d="M12 4 2.8 19.5h18.4L12 4Z" />
      <path d="M12 10.2v4" />
      <circle cx="12" cy="16.6" r="0.9" fill="currentColor" stroke="none" />
    </>
  ),
  spark: (
    <path d="M12 3.5c.6 3.8 2 6.2 3.3 7.2 1 .8 2.7 1.2 5.2 1.3-2.5.1-4.2.5-5.2 1.3-1.3 1-2.7 3.4-3.3 7.2-.6-3.8-2-6.2-3.3-7.2-1-.8-2.7-1.2-5.2-1.3 2.5-.1 4.2-.5 5.2-1.3 1.3-1 2.7-3.4 3.3-7.2Z" />
  ),
  key: (
    <>
      <circle cx="8" cy="14.5" r="4.5" />
      <path d="m11.5 11.5 8-8M17 6l2.5 2.5M14 9l2 2" />
    </>
  ),
  arrow: (
    <>
      <path d="M4 12h15" />
      <path d="m13.5 6.5 5.5 5.5-5.5 5.5" />
    </>
  ),
  calendar: (
    <>
      <rect x="3.5" y="5" width="17" height="15.5" rx="2" />
      <path d="M3.5 9.5h17M8 3v4M16 3v4" />
    </>
  ),
  history: (
    <>
      <path d="M4.6 17.4A7.6 7.6 0 1 1 4.4 12" />
      <path d="M4.4 12l-2-2.2M4.4 12l3-.7" />
      <path d="M12 8.2v4.1l2.8 1.9" />
    </>
  ),
  info: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 11v5" />
      <circle cx="12" cy="8" r="0.9" fill="currentColor" stroke="none" />
    </>
  ),
};

export function I({
  name,
  size = 18,
  className = "",
  sw = 1.7,
}: {
  name: string;
  size?: number;
  className?: string;
  sw?: number;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={sw}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {paths[name] ?? null}
    </svg>
  );
}

/** Animated radar mark — the brand glyph. */
export function LogoMark({ size = 34, animate = true, className = "" }: { size?: number; animate?: boolean; className?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 40 40" fill="none" className={className} aria-hidden="true">
      <circle cx="20" cy="20" r="16" stroke="currentColor" strokeOpacity="0.55" strokeWidth="1.6" />
      <circle cx="20" cy="20" r="10" stroke="currentColor" strokeOpacity="0.3" strokeWidth="1.2" />
      <circle cx="20" cy="20" r="4.5" stroke="currentColor" strokeOpacity="0.55" strokeWidth="1.2" />
      <g style={animate ? { animation: "rl-sweep 5s linear infinite", transformOrigin: "20px 20px" } : undefined}>
        <path d="M20 20 L20 4 A16 16 0 0 1 31.3 8.7 Z" fill="currentColor" fillOpacity="0.16" />
        <line x1="20" y1="20" x2="20" y2="4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      </g>
      <circle cx="27" cy="13" r="2" fill="#e0a63c" />
      <circle cx="12.5" cy="26.5" r="1.7" fill="#c2473a" />
      <circle cx="20" cy="20" r="1.6" fill="currentColor" />
    </svg>
  );
}
