// Runner order. "scene": scene by scene (script order inside a scene). "character": one character at a time, scenes in order.
export const orderItems = (list, mode) => {
  const segs = [...new Set(list.map((i) => i.segment))];
  const chars = [...new Set([...list].sort((a, b) => a.n - b.n).map((i) => i.character))];
  const num = (id) => parseInt((id.match(/(\d+)$/) || [])[1] ?? "0", 10);
  const cmp = mode === "character"
    ? (a, b) => chars.indexOf(a.character) - chars.indexOf(b.character) || segs.indexOf(a.segment) - segs.indexOf(b.segment) || num(a.id) - num(b.id) || a.n - b.n
    : (a, b) => segs.indexOf(a.segment) - segs.indexOf(b.segment) || a.n - b.n;
  return [...list].sort(cmp);
};

// Script check: ID series, gaps, duplicates, empty lines. Uses the script's own order (item.n),
// so sorting the runner never changes "last ID".
export function analyzeScript(items) {
  const fileOrder = [...items].sort((a, b) => a.n - b.n);
  const groups = new Map(); const seen = new Set(); const dups = new Set(); const empty = [];
  fileOrder.forEach((it) => {
    if (seen.has(it.id)) dups.add(it.id);
    seen.add(it.id);
    if (!it.orig.trim()) empty.push(it.id);
    const m = it.id.match(/^(.*?)(\d+)$/);
    const prefix = m ? m[1] : it.id;
    const g = groups.get(prefix) || { prefix, nums: new Set(), width: 0 };
    if (m) { g.nums.add(parseInt(m[2], 10)); g.width = Math.max(g.width, m[2].length); }
    groups.set(prefix, g);
  });
  const list = [...groups.values()].map((g) => {
    const nums = [...g.nums].sort((a, b) => a - b);
    const first = nums[0]; const last = nums[nums.length - 1];
    const missing = [];
    for (let n = first; n <= last; n++) if (!g.nums.has(n)) missing.push(n);
    return { ...g, first, last, count: nums.length, missing, fmt: (n) => String(n).padStart(g.width, "0") };
  });
  const missingGroups = list.filter((g) => g.missing.length);
  const missingTotal = list.reduce((a, g) => a + g.missing.length, 0);
  const lastItem = fileOrder[fileOrder.length - 1];
  return {
    total: items.length, groups: list, dups: [...dups], empty,
    missingGroups, missingTotal,
    lastId: lastItem?.id || "",
    problems: missingTotal + dups.size + empty.length,
  };
}
