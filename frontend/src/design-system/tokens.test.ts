import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * Guards WCAG 2.1 AA contrast for every text/background token pair the components
 * use, in both standard and high-contrast themes, by parsing theme.css directly.
 */
const css = readFileSync(resolve(__dirname, "../styles/theme.css"), "utf8");

function tokens(block: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const m of block.matchAll(/--color-([a-z-]+):\s*(#[0-9a-f]{6})/gi)) out[m[1]!] = m[2]!.toLowerCase();
  return out;
}
const standard = tokens(css.match(/@theme\s*\{([\s\S]*?)\n\}/)![1]!);
const high = { ...standard, ...tokens(css.match(/\[data-contrast="high"\]\s*\{([\s\S]*?)\n\}/)![1]!) };

function luminance(hex: string): number {
  const [r, g, b] = [1, 3, 5].map((i) => {
    const v = parseInt(hex.slice(i, i + 2), 16) / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r! + 0.7152 * g! + 0.0722 * b!;
}
export function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x! + 0.05) / (y! + 0.05);
}

// [foreground, background, minimum ratio]; 4.5 = normal text, 3 = UI components/focus.
const PAIRS: Array<[string, string, number]> = [
  ["ink", "surface", 4.5],
  ["ink", "page", 4.5],
  ["ink", "surface-muted", 4.5],
  ["ink-muted", "surface", 4.5],
  ["ink-muted", "page", 4.5],
  ["ink-muted", "surface-muted", 4.5],
  ["link", "surface", 4.5],
  ["link", "page", 4.5],
  ["on-brand", "brand", 4.5],
  ["on-brand", "brand-hover", 4.5],
  ["on-brand", "brand-deep", 4.5],
  ["on-brand-muted", "brand", 4.5],
  ["on-brand-muted", "brand-deep", 4.5],
  ["on-brand", "danger", 4.5],
  ["brand", "surface", 4.5],
  ["brand", "brand-soft", 4.5],
  ["ink", "brand-soft", 4.5],
  ["success", "success-soft", 4.5],
  ["danger", "danger-soft", 4.5],
  ["danger", "surface", 4.5],
  ["warning", "warning-soft", 4.5],
  ["accent-ink", "accent-soft", 4.5],
  ["ink", "danger-soft", 4.5],
  ["ink", "warning-soft", 4.5],
  ["ink", "success-soft", 4.5],
  ["ink-muted", "brand-soft", 4.5],
  ["line-strong", "surface", 3],
  ["focus", "surface", 3],
  ["focus", "page", 3],
  ["focus-on-dark", "brand", 3],
  ["focus-on-dark", "brand-deep", 3],
  ["accent", "brand", 3],
  ["accent", "brand-deep", 3],
  ["brand", "brand-soft", 3],
];

describe.each([
  ["standard", standard],
  ["high contrast", high],
])("%s theme", (_name, theme) => {
  it.each(PAIRS)("%s on %s meets %s:1", (fg, bg, min) => {
    expect(theme[fg], `missing token ${fg}`).toBeDefined();
    expect(theme[bg], `missing token ${bg}`).toBeDefined();
    expect(contrast(theme[fg]!, theme[bg]!)).toBeGreaterThanOrEqual(min);
  });
});
