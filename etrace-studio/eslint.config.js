import tseslint from "typescript-eslint"

export default tseslint.config(
  {
    ignores: [
      ".output/**",
      ".nitro/**",
      ".tanstack/**",
      ".vinxi/**",
      "dist/**",
      "dist-ssr/**",
      "node_modules/**",
    ],
  },
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parserOptions: {
        projectService: true,
      },
    },
    rules: {
      "@typescript-eslint/no-unused-vars": [
        "warn",
        { argsIgnorePattern: "^_" },
      ],
    },
  }
)
