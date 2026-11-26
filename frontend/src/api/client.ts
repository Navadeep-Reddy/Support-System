import type {
  ApiErrorEnvelope,
  Article,
  ArticleInput,
  ArticleSummary,
  Conversation,
  Customer,
  Feedback,
  HistoryResponse,
  TurnResponse,
} from "./types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class ApiClientError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly retryable: boolean,
  ) {
    super(message);
    this.name = "ApiClientError";
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    credentials: "include",
    headers: {
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...init.headers,
    },
  });

  if (response.status === 204) return undefined as T;

  const body: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const envelope = body as ApiErrorEnvelope | null;
    const error = envelope && "error" in envelope ? envelope.error : null;
    throw new ApiClientError(
      error?.message ?? "Something went wrong. Please try again.",
      response.status,
      error?.code ?? "UNKNOWN_ERROR",
      error?.retryable ?? false,
    );
  }
  return body as T;
}

type ChatStreamEvent =
  | { type: "started"; run_id: string }
  | { type: "reset" | "delta"; text: string }
  | { type: "done"; turn: TurnResponse }
  | { type: "error"; message: string };

async function streamChat(id: string, message: string, onEvent: (event: ChatStreamEvent) => void): Promise<TurnResponse> {
  const response = await fetch(`${API_BASE_URL}/conversations/${id}/chat/stream`, {
    method: "POST", credentials: "include", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null) as ApiErrorEnvelope | null;
    throw new ApiClientError(body?.error?.message ?? "Unable to send the message.", response.status,
      body?.error?.code ?? "UNKNOWN_ERROR", body?.error?.retryable ?? false);
  }
  if (!response.body) throw new Error("Streaming is unavailable.");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const lines = buffer.split("\n");
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        if (!line) continue;
        const event = JSON.parse(line) as ChatStreamEvent;
        onEvent(event);
        if (event.type === "done") return event.turn;
        if (event.type === "error") throw new Error(event.message);
      }
      if (done) throw new Error("The response was interrupted. Refresh history.");
    }
  } finally { reader.releaseLock(); }
}

export const api = {
  customers: async () => request<{ items: Customer[] }>("/customers"),
  login: (customer_id: string) =>
    request<Customer>("/sessions", {
      method: "POST",
      body: JSON.stringify({ customer_id }),
    }),
  logout: () => request<void>("/sessions/current", { method: "DELETE" }),
  enterKnowledge: () => request<{ role: "knowledge_admin" }>("/knowledge/session", { method: "POST" }),
  knowledgeSession: () => request<{ role: "knowledge_admin" }>("/knowledge/session"),
  me: () => request<Customer>("/me"),
  conversations: async () =>
    request<{ items: Conversation[] }>("/conversations"),
  createConversation: (title?: string) =>
    request<Conversation>("/conversations", {
      method: "POST",
      body: JSON.stringify(title ? { title } : {}),
    }),
  history: (id: string) =>
    request<HistoryResponse>(`/conversations/${id}/messages`),
  chat: (id: string, message: string) =>
    request<TurnResponse>(`/conversations/${id}/chat`, {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
  streamChat,
  decideApproval: (id: string, approved: boolean) =>
    request<TurnResponse>(`/approvals/${id}`, {
      method: "POST",
      body: JSON.stringify({ approved }),
    }),
  feedback: (id: string, rating: "positive" | "negative", comment: string | null) =>
    request<Feedback>(
      `/messages/${id}/feedback`,
      {
        method: "PUT",
        body: JSON.stringify({ rating, comment }),
      },
    ),
  articles: async () => request<{ items: ArticleSummary[] }>("/knowledge/articles"),
  article: (id: string) => request<Article>(`/knowledge/articles/${id}`),
  createArticle: (article: ArticleInput) =>
    request<Article>("/knowledge/articles", {
      method: "POST",
      body: JSON.stringify(article),
    }),
  updateArticle: (id: string, article: ArticleInput) =>
    request<Article>(`/knowledge/articles/${id}`, {
      method: "PUT",
      body: JSON.stringify(article),
    }),
  deleteArticle: (id: string) =>
    request<void>(`/knowledge/articles/${id}`, { method: "DELETE" }),
};
