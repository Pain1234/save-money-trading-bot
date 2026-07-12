import bcrypt from "bcryptjs";

export function getAuthUsername(): string {
  const username = process.env.AUTH_USERNAME;
  if (!username) {
    throw new Error("AUTH_USERNAME is required");
  }
  return username;
}

export function getAuthPasswordHash(): string {
  const hash = process.env.AUTH_PASSWORD_HASH;
  if (!hash) {
    throw new Error("AUTH_PASSWORD_HASH is required");
  }
  return hash;
}

export async function verifyCredentials(
  username: string,
  password: string,
): Promise<boolean> {
  const expectedUser = getAuthUsername();
  const hash = getAuthPasswordHash();
  if (username !== expectedUser) {
    return false;
  }
  return bcrypt.compare(password, hash);
}
