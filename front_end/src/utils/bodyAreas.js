// Everyday body areas ("Stomach / belly") over the model's 659 structures.
// bodyAreas.json is generated from the GLB by back_end/ml/body_map.py so the
// browser and the localizer agree on which structure belongs to which area.
import BODY_AREAS from "../data/bodyAreas.json";

export const AREA_CAVEATS = {
  abdomen: "Belly pain often comes from organs (stomach, bowel, appendix), which this model doesn't show. Mark where it hurts anyway; your doctor will use it.",
  chest: "Chest pain can come from the heart or lungs, which this model doesn't show. If it feels tight, heavy or spreads to your arm or jaw, call 911.",
  head: "Most headaches don't come from one muscle. Mark where it hurts most.",
  lower_back: "Back pain can also come from the spine itself. Mark where it hurts most.",
};

export function sideOf(name = "") {
  const match = /\.(l|r)$/i.exec(name.trim());
  if (!match) return "midline";
  return match[1].toLowerCase() === "l" ? "left" : "right";
}

export function areaOf(name) {
  return BODY_AREAS.structures[name] || null;
}

// Long structures cross area borders (latissimus over the lower back, the
// quadriceps tendon over the knee), so for back and leg structures the area
// of a tap comes from its height. Same rule as area_at() in body_map.py.
export function areaAt(name, point) {
  const area = areaOf(name);
  if (!area || !point) return area;
  const { bands } = BODY_AREAS;
  if (bands.legAreas.includes(area)) return bands.leg.find(([top]) => point.y < top)[1];
  if (bands.backAreas.includes(area)) return point.y < bands.lowBackTop ? "lower_back" : "upper_back";
  return area;
}

export function areaGroupKey(area, side) {
  return BODY_AREAS.areas[area]?.sided && side !== "midline" ? `${area}:${side}` : area;
}

export function areaLabel(area, side) {
  const label = BODY_AREAS.areas[area]?.label || area;
  return BODY_AREAS.areas[area]?.sided && side !== "midline" ? `${label} (${side})` : label;
}

// The identity of a saved spot, matching the canvas target key.
export function spotKey(spot) {
  if (!spot) return null;
  if (spot.mode === "area") return areaGroupKey(spot.areaKey, spot.side);
  return spot.regionName;
}

export function spotLabel(spot) {
  if (!spot) return "";
  return spot.mode === "area" ? spot.areaLabel : spot.regionName;
}
