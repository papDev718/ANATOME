// Blender object names carry a ".l" / ".r" side suffix. Display only:
// the raw name is still what selection and saved pain data key on.
export function displayAnatomyName(name) {
  if (!name) return "";
  const match = /^(.*)\.(l|r)$/i.exec(name.trim());
  if (!match) return name;
  return `${match[1]} (${match[2].toLowerCase() === "l" ? "left" : "right"})`;
}
