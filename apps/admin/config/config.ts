import { defineConfig } from "@umijs/max";
import proxy from "./proxy";
import routes from "./routes";

export default defineConfig({
  title: "Pinjie Console",
  favicons: ["/favicon.ico"],
  plugins: ["./config/html-accessibility"],
  ...(process.env.E2E_DISABLE_MFSU === "1" ? { mfsu: false } : {}),
  antd: {},
  access: {},
  model: {},
  initialState: {},
  layout: {},
  routes,
  history: { type: "browser" },
  hash: false,
  esbuildMinifyIIFE: true,
  npmClient: "pnpm",
  proxy: proxy.dev,
  define: {
    "process.env.APP_ENV": process.env.APP_ENV ?? "development",
    "process.env.VITE_API_URL": process.env.VITE_API_URL ?? "",
  },
});
