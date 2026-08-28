import { api } from "./client";

export const retrievalApi = {
  search: (query: string, topK = 5) =>
    api.post("/api/v1/retrieval/search", { query, top_k: topK }).then((r) => r.data),
};
