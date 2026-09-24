import { pinjieConfig } from "@pinjie/eslint-config";

export default [
  { ignores: ["coverage/**", "dist/**", "**/.umi/**", "**/.umi-production/**"] },
  ...pinjieConfig,
  {
    files: ["src/**/*.ts", "src/**/*.tsx"],
    rules: {
      "no-restricted-imports": ["error", {
        paths: [{
          name: "antd",
          importNames: ["message", "notification"],
          message: "使用 App.useApp() 获取反馈实例，保持主题和语言上下文。",
        }],
      }],
    },
  },
  {
    languageOptions: {
      globals: {
        document: "readonly",
        fetch: "readonly",
        Headers: "readonly",
        process: "readonly",
        RequestInit: "readonly",
        Response: "readonly",
        URLSearchParams: "readonly",
        window: "readonly",
      },
    },
  },
];
