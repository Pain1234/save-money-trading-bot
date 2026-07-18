export function notFound(): never {
  throw new Error("NEXT_NOT_FOUND");
}

export function useRouter() {
  return {
    push: () => undefined,
    replace: () => undefined,
    refresh: () => undefined,
  };
}
