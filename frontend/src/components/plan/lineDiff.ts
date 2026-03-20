export function buildLineDiff(original: string, latest: string): string {
  const origLines = original.split("\n");
  const newLines = latest.split("\n");
  const maxLen = Math.max(origLines.length, newLines.length);
  const out: string[] = [];

  for (let i = 0; i < maxLen; i++) {
    const o = origLines[i] ?? "";
    const n = newLines[i] ?? "";
    if (o === n) {
      out.push("  " + o);
    } else {
      if (o) out.push("- " + o);
      if (n) out.push("+ " + n);
    }
  }

  return out.join("\n");
}
