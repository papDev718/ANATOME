// The Z-Anatomy GLB swaps these two labels relative to the meshes' positions
// (see MODEL_LABEL_FIXES in back_end/ml/anatomy.py). Display only.
const MODEL_LABEL_FIXES = {
  "Descending part of trapezius muscle": "Ascending part of trapezius muscle",
  "Ascending part of trapezius muscle": "Descending part of trapezius muscle",
};

// Blender object names carry a ".l" / ".r" side suffix. Display only:
// the raw name is still what selection and saved pain data key on.
export function displayAnatomyName(name) {
  if (!name) return "";
  const match = /^(.*)\.(l|r)$/i.exec(name.trim());
  if (!match) return MODEL_LABEL_FIXES[name.trim()] || name;
  const base = MODEL_LABEL_FIXES[match[1]] || match[1];
  return `${base} (${match[2].toLowerCase() === "l" ? "left" : "right"})`;
}
