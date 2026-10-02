import { dirname } from 'path';
import { fileURLToPath } from 'url';
import { FlatCompat } from '@eslint/eslintrc';
import jsxA11y from 'eslint-plugin-jsx-a11y';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const compat = new FlatCompat({ baseDirectory: __dirname });

const eslintConfig = [
  { ignores: ['out/**', '.next/**', 'node_modules/**', 'next-env.d.ts'] },
  ...compat.extends('next/core-web-vitals', 'next/typescript'),
  // Accessibility is a product requirement here (every screen is a form over money), so the
  // full jsx-a11y recommended set runs, not just the handful next/core-web-vitals enables.
  { rules: jsxA11y.flatConfigs.recommended.rules },
];

export default eslintConfig;
