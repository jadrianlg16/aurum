/**
 * Runs before every test file (vitest `setupFiles`). The timezone is pinned FIRST so every
 * `new Date()` in the code under test is a Mexico City clock: the local-date rules ("today" is the
 * local date, never `toISOString`) only mean something in a fixed, non-UTC zone.
 */
process.env.TZ = 'America/Mexico_City';

// Next's inlined env: the client reads these at module load.
process.env.NEXT_PUBLIC_API_URL = process.env.NEXT_PUBLIC_API_URL ?? '/api';
process.env.NEXT_PUBLIC_MOCK = process.env.NEXT_PUBLIC_MOCK ?? '0';
