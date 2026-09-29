export {};

declare module "@umijs/max" {
  import type { ComponentType, ReactNode } from "react";
  export const history: {
    location: { pathname: string; search: string; hash: string; state?: unknown };
    replace: (path: string, state?: unknown) => void;
    push: (path: string) => void;
  };
  export const Link: ComponentType<{ to: string; children?: ReactNode }>;
  export function useParams<T extends Record<string, string | undefined>>(): T;
}
