import axios from "axios";

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || "",
  timeout: 20_000,
});

// Resource generation may include one or more model calls. Keep the default
// timeout short for ordinary API requests and opt into this budget only for
// operations that synchronously generate learning materials.
export const RESOURCE_GENERATION_TIMEOUT_MS = 180_000;
export const PLATFORM_RUN_TIMEOUT_MS = 180_000;

export async function withRetry<T>(
  request: () => Promise<T>,
  retries = 2,
): Promise<T> {
  let lastError: unknown;
  for (let attempt = 0; attempt <= retries; attempt += 1) {
    try {
      return await request();
    } catch (error) {
      lastError = error;
      if (attempt < retries) await new Promise((resolve) => setTimeout(resolve, 400 * (attempt + 1)));
    }
  }
  throw lastError;
}
