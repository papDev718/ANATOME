// Body areas the patient mentioned in their description, so the body map can
// suggest where to tap. Plain word lists: every suggestion can show the words
// it came from. Sides come from "left"/"right"/"both" in the same clause.
import { areaGroupKey, areaLabel } from "./bodyAreas";
import BODY_AREAS from "../data/bodyAreas.json";

// Order matters: more specific phrases first ("shoulder blade" before "shoulder").
const AREA_WORDS = [
  ["upper_back", /\b(upper back|mid(dle)?[- ]back|between (my )?shoulder ?blades|shoulder ?blades?)\b/g],
  ["lower_back", /\b(lower back|low back|lumbar|tail ?bone|coccyx|sciatica|back pain|my back|the back)\b/g],
  ["head", /\b(head(ache)?s?|migraines?|forehead|temples?|scalp|skull)\b/g],
  ["face_jaw", /\b(jaw|face|cheeks?|chewing|tmj|teeth|tooth|chin)\b/g],
  ["neck", /\b(neck|nape)\b/g],
  ["shoulder", /\b(shoulders?|rotator cuff|collar ?bone|clavicle)\b/g],
  ["chest", /\b(chest|ribs?|rib ?cage|sternum|breast ?bone|pecs?)\b/g],
  ["abdomen", /\b(stomach|belly|tummy|abdomen|abdominal|abs|gut|navel|belly ?button|period|menstrual|appendix|side stitch)\b/g],
  ["upper_arm", /\b(upper arm|biceps?|triceps?|elbows?|arms?)\b/g],
  ["forearm_hand", /\b(forearms?|wrists?|hands?|fingers?|thumbs?|palms?|knuckles?|carpal)\b/g],
  ["hip", /\b(hips?|buttocks?|butt|glutes?|groin|pelvis|pelvic|bum)\b/g],
  ["thigh", /\b(thighs?|quads?|quadriceps|hamstrings?)\b/g],
  ["knee", /\b(knees?|knee ?caps?|patella)\b/g],
  ["lower_leg", /\b(calf|calves|shins?|lower legs?)\b/g],
  ["ankle_foot", /\b(ankles?|feet|foot|heels?|toes?|arch|achilles|soles?)\b/g],
  // "leg" alone: only used when nothing more specific about the leg was said.
  ["leg", /\b(legs?)\b/g],
];

const NEGATION = /\b(no|not|without|never|don'?t|doesn'?t|didn'?t|isn'?t|aren'?t|wasn'?t|haven'?t|hasn'?t|nor)\b/;
const LEG_AREAS = ["thigh", "knee", "lower_leg", "ankle_foot"];

function clauseAround(text, index) {
  const before = text.slice(0, index).split(/[.;!?\n]|\bbut\b|\band\b/);
  const after = text.slice(index).split(/[.;!?\n]|\bbut\b/);
  return { before: before[before.length - 1], after: after[0] };
}

function sidesFor(text, index, word) {
  // Nearest side word wins: up to 3 words before ("my left knee"), else up
  // to 4 words after within the same phrase ("knee on the right").
  const before = text.slice(0, index).split(/[.;!?,\n]|\band\b|\bbut\b/).pop().trim().split(/\s+/).slice(-3).join(" ");
  const after = text.slice(index + word.length).split(/[.;!?,\n]|\band\b|\bbut\b/)[0].trim().split(/\s+/).slice(0, 4).join(" ");
  for (const near of [before, after]) {
    if (/\b(both|bilateral)\b/.test(near)) return ["left", "right"];
    const sides = [...near.matchAll(/\b(left|right)\b/g)].map((m) => m[1]);
    if (sides.length) return near === before ? [sides[sides.length - 1]] : [sides[0]];
  }
  // A plural with no side ("my knees") means both.
  if (/(s|feet|calves)$/.test(word) && !/(chest|ribs|abs|glutes|bicep|tricep|biceps|triceps)$/.test(word)) return ["left", "right"];
  return [];
}

export function suggestAreas(description) {
  const text = (description || "").toLowerCase();
  if (!text.trim()) return [];
  const found = new Map(); // area -> { sides:Set, words:Set, unsided:boolean, firstIndex }
  const taken = []; // character spans already claimed by a more specific phrase

  for (const [area, pattern] of AREA_WORDS) {
    pattern.lastIndex = 0;
    for (const match of text.matchAll(pattern)) {
      const word = match[0];
      const end = match.index + word.length;
      if (taken.some(([a, b]) => match.index < b && end > a)) continue;
      taken.push([match.index, end]);
      const { before } = clauseAround(text, match.index);
      // "my knee doesn't hurt" / "no pain in my neck"
      const window = `${before.split(/\s+/).slice(-5).join(" ")} ${text.slice(match.index, match.index + 40)}`;
      if (NEGATION.test(before.split(/\s+/).slice(-5).join(" ")) || /^\S+ (doesn'?t|does not|isn'?t|is not) (hurt|bother)/.test(window.slice(window.indexOf(word)))) continue;
      const entry = found.get(area) || { sides: new Set(), words: new Set(), unsided: false, firstIndex: match.index };
      entry.words.add(word);
      const sides = sidesFor(text, match.index, word);
      if (sides.length) sides.forEach((side) => entry.sides.add(side));
      else entry.unsided = true;
      found.set(area, entry);
    }
  }

  // Generic "leg": suggest thigh and calf only if no specific leg part was named.
  const leg = found.get("leg");
  found.delete("leg");
  if (leg && !LEG_AREAS.some((area) => found.has(area))) {
    found.set("thigh", leg);
    found.set("lower_leg", { ...leg, sides: new Set(leg.sides), words: new Set(leg.words) });
  }

  const suggestions = [];
  [...found.entries()]
    .sort((a, b) => a[1].firstIndex - b[1].firstIndex)
    .forEach(([area, entry]) => {
      const words = [...entry.words];
      if (!BODY_AREAS.areas[area]?.sided) {
        suggestions.push({ key: areaGroupKey(area, "midline"), area, side: "midline", label: areaLabel(area, "midline"), words });
        return;
      }
      // No side mentioned: offer both and let the patient pick.
      const sideUnknown = entry.sides.size === 0;
      const sides = sideUnknown ? ["left", "right"] : [...entry.sides];
      sides.forEach((side) => {
        suggestions.push({ key: areaGroupKey(area, side), area, side, label: areaLabel(area, side), words, sideUnknown });
      });
    });
  return suggestions;
}
