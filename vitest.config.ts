import { defineConfig } from "vitest/config";
import path from "node:path";

export default defineConfig({
  esbuild: {
    jsx: "automatic",
  },
  test: {
    environment: "node",
    include: ["tests/dashboard/**/*.test.ts", "tests/dashboard/**/*.test.tsx"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      // Next.js modules are mocked for static markup assertions in unit tests.
      "next/link": path.resolve(__dirname, "./tests/dashboard/mocks/next-link.tsx"),
      "next/navigation": path.resolve(
        __dirname,
        "./tests/dashboard/mocks/next-navigation.ts",
      ),
    },
  },
});
