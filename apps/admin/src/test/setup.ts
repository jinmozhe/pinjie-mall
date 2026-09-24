import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";
import { setupServer } from "msw/node";

import { handlers } from "./server";

export const server = setupServer(...handlers);

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => undefined,
    removeListener: () => undefined,
    addEventListener: () => undefined,
    removeEventListener: () => undefined,
    dispatchEvent: () => false,
  }),
});

class TestResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

Object.defineProperty(window, "ResizeObserver", { writable: true, value: TestResizeObserver });
Object.defineProperty(globalThis, "ResizeObserver", { writable: true, value: TestResizeObserver });

const getComputedStyle = window.getComputedStyle.bind(window);
Object.defineProperty(window, "getComputedStyle", {
  writable: true,
  value: (element: Parameters<typeof getComputedStyle>[0]) => getComputedStyle(element),
});

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  // App 上下文中的通知随组件树卸载，不保留静态消息实例。
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
