import path from 'node:path';
import { defineConfig } from 'vitest/config';

/**
 * Unit tests for the client layer. jsdom gives `window`,
 * `localStorage` and React DOM a home; `tests/setup.ts` pins TZ=America/Mexico_City before
 * anything reads the clock so the local-date rules are what is asserted.
 */
export default defineConfig({
  resolve: { alias: { '@': path.resolve(__dirname, 'src') } },
  // tsconfig says `jsx: preserve` (Next compiles it); here esbuild must emit React 19 JSX.
  esbuild: { jsx: 'automatic' },
  test: {
    environment: 'jsdom',
    include: ['tests/**/*.test.{ts,tsx}', 'src/**/*.test.{ts,tsx}'],
    setupFiles: ['tests/setup.ts'],
    globals: false,
    css: false,
  },
});
