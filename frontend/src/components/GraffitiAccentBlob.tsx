import { useId } from "react";

const dots = [
  [82, 54, 3], [111, 45, 2], [144, 58, 4], [179, 43, 2], [214, 61, 3],
  [248, 49, 2], [279, 70, 4], [307, 91, 2], [61, 91, 2], [94, 101, 4],
  [130, 88, 2], [165, 105, 3], [202, 91, 2], [239, 112, 4], [278, 106, 2],
  [321, 126, 3], [54, 132, 4], [88, 143, 2], [123, 130, 3], [157, 151, 2],
  [194, 137, 4], [227, 157, 2], [266, 145, 3], [302, 164, 2], [72, 178, 3],
  [108, 166, 2], [143, 187, 4], [181, 174, 2], [217, 193, 3], [254, 181, 2],
  [287, 204, 4], [94, 218, 2], [132, 207, 3], [168, 225, 2], [206, 214, 4],
  [244, 231, 2], [275, 247, 3], [122, 252, 2], [158, 266, 4], [197, 251, 2],
] as const;

export function GraffitiAccentBlob() {
  const clipId = `blob-${useId().replace(/:/g, "")}`;
  const path = "M45 91C68 42 123 23 177 36C226 8 290 28 309 72C354 91 367 143 337 177C345 224 303 264 257 257C224 292 161 288 134 258C82 267 37 231 49 187C13 159 14 111 45 91Z";
  return (
    <svg className="graffiti-blob" viewBox="0 0 380 300" aria-hidden="true" data-testid="graffiti-blob">
      <defs><clipPath id={clipId}><path d={path} /></clipPath></defs>
      <path className="graffiti-blob__shape" d={path} />
      <g className="graffiti-blob__dots" clipPath={`url(#${clipId})`} data-testid="graffiti-dots">
        {dots.map(([cx, cy, radius]) => <circle cx={cx} cy={cy} key={`${String(cx)}-${String(cy)}`} r={radius} />)}
      </g>
    </svg>
  );
}
