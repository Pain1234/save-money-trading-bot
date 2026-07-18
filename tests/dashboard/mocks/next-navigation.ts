export function notFound(): never {
  throw new Error("NEXT_NOT_FOUND");
}

let mockPathname = "/dashboard";

/** Test helper: set the pathname returned by usePathname(). */
export function __setMockPathname(pathname: string): void {
  mockPathname = pathname;
}

export function usePathname(): string {
  return mockPathname;
}

export function useRouter() {
  return {
    push: () => undefined,
    replace: () => undefined,
    refresh: () => undefined,
  };
}
