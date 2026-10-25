// Pre-answers a new spot's questions from what the patient already said in
// the intake ("started 3 days ago", "comes and goes", "sharp"). Every
// prefilled answer is shown as such in the form and can be changed.

const NUMBER_WORDS = { a: 1, an: 1, one: 1, two: 2, three: 3, four: 4, five: 5, six: 6, seven: 7, eight: 8, nine: 9, ten: 10, couple: 2, few: 3, several: 5 };

const PAIN_WORDS = [
  ["Sharp", /\b(sharp|stabbing|knife)/],
  ["Dull", /\bdull\b/],
  ["Aching", /\b(ach(e|es|ing|y)|sore)\b/],
  ["Burning", /\bburn(s|ing)?\b/],
  ["Throbbing", /\b(throb(s|bing)?|pounding|pulsing)\b/],
  ["Shooting", /\b(shoot(s|ing)?|radiat(es|ing))\b/],
  ["Cramping", /\bcramp(s|ing|y)?\b/],
  ["Pressure", /\b(pressure|tight(ness)?|squeez(e|ing))\b/],
  ["Tingling", /\b(tingl(e|es|ing|y)|pins and needles)\b/],
  ["Numb", /\bnumb(ness)?\b/],
];

function toNumber(word) {
  return /^\d+$/.test(word) ? Number(word) : NUMBER_WORDS[word] ?? null;
}

function onsetFrom(text) {
  if (/\b(just now|minutes? ago|an hour ago|half an hour|last hour)\b/.test(text)) return "Within the last hour";
  if (/\b(today|this (morning|afternoon|evening)|tonight)\b/.test(text)) return "Today";
  if (/\b(yesterday|last night)\b/.test(text)) return "1–3 days ago";
  if (/\blast week\b/.test(text)) return "4–7 days ago";
  if (/\b(last|past) (few )?months?\b|\b(months?|years?) ago\b|\bfor (months|years)\b/.test(text)) return "More than one month ago";

  const match = /\b(\d+|an?|one|two|three|four|five|six|seven|eight|nine|ten|couple|few|several)\s+(?:of\s+)?(hours?|days?|weeks?|months?|years?)\b/.exec(text);
  if (!match) return "";
  const count = toNumber(match[1]);
  if (count === null) return "";
  const unit = match[2];
  if (unit.startsWith("hour")) return count <= 1 ? "Within the last hour" : "Today";
  if (unit.startsWith("day")) return count <= 3 ? "1–3 days ago" : count <= 7 ? "4–7 days ago" : count <= 30 ? "1–4 weeks ago" : "More than one month ago";
  if (unit.startsWith("week")) return count <= 1 ? "4–7 days ago" : count <= 4 ? "1–4 weeks ago" : "More than one month ago";
  return "More than one month ago";
}

function frequencyFrom(text) {
  if (/\b(comes and goes|on and off|off and on|now and then|sometimes|every so often)\b/.test(text)) return "Comes and goes";
  if (/\b(constant(ly)?|all the time|nonstop|non-stop|never stops|always)\b/.test(text)) return "Constant";
  // "Hurts when I walk" means movement; "worse when I bend" doesn't mean only then.
  if (/\b(only (hurts )?when|hurts when) i (walk|move|bend|lift|run|stand|climb|turn|twist|reach|squat|kneel|use)/.test(text)) return "Only when I move it";
  return "";
}

function painTypeFrom(text) {
  const found = PAIN_WORDS.filter(([, pattern]) => pattern.test(text)).map(([label]) => label);
  // Several words could each describe a different spot; don't guess.
  return found.length === 1 ? found[0] : "";
}

export function prefillFromText(description) {
  const text = (description || "").toLowerCase();
  if (!text.trim()) return {};
  const values = { onset: onsetFrom(text), frequency: frequencyFrom(text), painType: painTypeFrom(text) };
  return Object.fromEntries(Object.entries(values).filter(([, value]) => value));
}
