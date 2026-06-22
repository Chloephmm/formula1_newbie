// Flat ESLint config for Next.js 16 + ESLint 9.
// Uses eslint-config-next's native flat configs directly (no @eslint/eslintrc
// FlatCompat bridge, which crashed on load with a circular-config error).
import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

const eslintConfig = [
  { ignores: ["node_modules/**", ".next/**", "out/**", "next-env.d.ts"] },
  ...nextCoreWebVitals,
  ...nextTypescript,
];

export default eslintConfig;
