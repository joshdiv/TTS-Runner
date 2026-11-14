import { orderItems } from "./script";

const csvCell = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;

export const downloadFile = (name, text, type) => {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url; a.download = name;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1500);
};

// CSV follows the export grouping (by scene or by character).
export function exportCsv({ items, done, by, baseName, say }) {
  const rows = [["id", "segment", "character", "original_text", "text", "edited", "saved"]];
  orderItems(items, by).forEach((i) =>
    rows.push([i.id, i.segment, i.character, i.orig, i.text, i.text !== i.orig ? "yes" : "", done[i.id] ? "yes" : ""]));
  downloadFile(`${baseName}.by-${by}.csv`, "\ufeff" + rows.map((r) => r.map(csvCell).join(",")).join("\r\n"), "text/csv");
  say(`Exported ${items.length} lines to CSV, sorted by ${by}.`);
}
