/**
 * A deliberately small YAML sanity check for the workflow editor.
 *
 * This is NOT a YAML parser and must never become one: the API validates the workflow
 * and its errors are the ones that count. This exists so the editor can
 * refuse the three mistakes that are certain to be wrong before a round trip — a tab
 * character (illegal in YAML indentation), no `steps:` block, and a step without an
 * `endpoint:` — and so the "validate" button says something on a machine with no API yet.
 *
 * Everything it reports is prefixed as a local check in the UI, and a clean result here
 * never means the API accepted the workflow.
 */

export interface LocalValidation {
  valid: boolean;
  errors: string[];
}

export function validateWorkflowYaml(yaml: string): LocalValidation {
  const errors: string[] = [];
  const lines = yaml.split(/\r?\n/);

  if (yaml.trim() === '') errors.push('empty');

  lines.forEach((line, i) => {
    if (/^\s*\t/.test(line)) errors.push(`line ${i + 1}: tab character in indentation (YAML forbids tabs)`);
  });

  if (!/^\s*steps\s*:/m.test(yaml)) errors.push("missing top-level `steps:` block");
  if (!/^\s*name\s*:/m.test(yaml)) errors.push("missing top-level `name:`");

  // Count `- ` step items and how many of them carry a path.
  const stepItems = lines.filter((l) => /^\s*-\s+\S/.test(l)).length;
  const paths = lines.filter((l) => /^\s*-?\s*path\s*:/.test(l)).length;
  if (stepItems > 0 && paths === 0) errors.push('no step declares a `path:`');

  return { valid: errors.length === 0, errors };
}

/** Cron presets offered next to the schedule field; the API is the one that parses cron. */
export const CRON_PRESETS: { label: string; cron: string }[] = [
  { label: '08:00 daily', cron: '0 8 * * *' },
  { label: '08:00 Monday', cron: '0 8 * * 1' },
  { label: 'Day 1, 09:00', cron: '0 9 1 * *' },
  { label: 'Day 17, 09:00', cron: '0 9 17 * *' },
  { label: 'Every hour', cron: '0 * * * *' },
];
