export const EMPTY_VALUES = { severity: null, painType: "", frequency: "", onset: "", notes: "" };

export function validateSpot(values) {
  const errors = {};
  if (!values.severity) errors.severity = "Choose how bad it is, from 1 to 10.";
  if (!values.painType) errors.painType = "Choose what the pain feels like.";
  if (!values.frequency) errors.frequency = "Choose how often it hurts.";
  if (!values.onset) errors.onset = "Choose when it started.";
  return errors;
}
