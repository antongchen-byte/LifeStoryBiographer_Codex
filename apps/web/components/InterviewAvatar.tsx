"use client";
import { useId } from "react";
export default function InterviewAvatar({
  kind,
  name,
  level = 0,
  speaking = false,
}: {
  kind: string;
  name: string;
  level?: number;
  speaking?: boolean;
}) {
  const id = useId().replaceAll(":", "");
  const energy = Math.min(1, Math.max(0, level));
  return (
    <div
      className={`interview-avatar ${speaking ? "is-speaking" : ""}`}
      role="img"
      aria-label={`${name}, ${kind === "flame" ? "candle flame" : kind + " face"} avatar`}
      style={
        {
          "--energy": energy,
          "--flicker-speed": `${1.4 - energy * 1.15}s`,
        } as React.CSSProperties
      }
    >
      {kind === "flame" ? (
        <svg viewBox="0 0 200 220" aria-hidden="true">
          <defs>
            <radialGradient id={id}>
              <stop stopColor="#fff2b2" />
              <stop offset=".5" stopColor="#f6b553" />
              <stop offset="1" stopColor="#c96539" />
            </radialGradient>
          </defs>
          <ellipse cx="100" cy="190" rx="53" ry="10" fill="#d5dcca" />
          <rect x="73" y="136" width="54" height="53" rx="8" fill="#eee3c7" />
          <path d="M100 145v-16" stroke="#735344" strokeWidth="3" />
          <path
            className="avatar-flame"
            d="M100 35C118 74 139 83 131 110C124 146 77 145 67 114C55 88 84 70 100 35Z"
            fill={`url(#${id})`}
          />
          <path
            d="M100 85C116 109 113 131 100 137C82 130 85 111 100 85Z"
            fill="#fff5c9"
          />
        </svg>
      ) : (
        <svg viewBox="0 0 200 220" aria-hidden="true">
          <circle cx="100" cy="102" r="78" fill="#e9ecdf" />
          {kind === "female" && (
            <path
              d="M51 91Q43 17 103 27Q158 25 151 151L132 170H65Z"
              fill="#51443e"
            />
          )}
          <path
            d="M42 214Q45 158 100 161Q156 158 160 214"
            fill={kind === "female" ? "#768b74" : "#586f70"}
          />
          <path d="M85 148v26q15 13 30 0v-26" fill="#bc8f73" />
          <ellipse cx="100" cy="101" rx="43" ry="58" fill="#d9ac8d" />
          <path
            d={
              kind === "female"
                ? "M55 98Q47 37 100 34Q154 36 145 96Q118 61 98 58Q75 78 55 98"
                : "M57 85Q51 29 104 34Q153 33 145 87L128 65Q88 78 77 57Z"
            }
            fill="#51443e"
          />
          <path
            d="M73 97q9-5 16 0m23 0q9-5 16 0"
            fill="none"
            stroke="#51443e"
            strokeWidth="3"
            strokeLinecap="round"
          />
          <circle cx="82" cy="102" r="3" fill="#39433b" />
          <circle cx="121" cy="102" r="3" fill="#39433b" />
          <path
            d="M101 106l-4 14 7 1"
            fill="none"
            stroke="#ad7c66"
            strokeWidth="2"
          />
          {speaking ? (
            <ellipse
              cx="101"
              cy="136"
              rx="10"
              ry={3 + energy * 7}
              fill="#8e4b47"
            />
          ) : (
            <path
              d="M89 133q12 10 24 0"
              fill="none"
              stroke="#8e4b47"
              strokeWidth="3"
              strokeLinecap="round"
            />
          )}
        </svg>
      )}
    </div>
  );
}
