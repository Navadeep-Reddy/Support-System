export type UUID = string;
export type Timestamp = string;
export type DecimalString = string;

export type Customer = {
  id: UUID;
  handle: string;
  display_name: string;
};

export type Conversation = {
  id: UUID;
  title: string;
  created_at: Timestamp;
  updated_at: Timestamp;
};

export type Citation = {
  article_id: UUID;
  chunk_id: UUID;
  article_title: string;
  section: string;
};

export type Feedback = {
  rating: "positive" | "negative";
  comment: string | null;
  updated_at: Timestamp;
};

export type RunStatus =
  | "running"
  | "waiting_for_approval"
  | "completed"
  | "failed";

export type ApprovalStatus =
  | "pending"
  | "approved"
  | "rejected"
  | "executed"
  | "failed";

export type ResetResult = {
  request_id: UUID;
  status: "requested";
  reset_url: string;
  simulated: true;
};

export type ApprovalCard = {
  action_id: UUID;
  action_type: "request_password_reset";
  status: ApprovalStatus;
  account_display_name: string;
  created_at: Timestamp;
  decided_at: Timestamp | null;
  result: ResetResult | null;
};

export type Message = {
  id: UUID;
  conversation_id: UUID;
  run_id: UUID | null;
  role: "user" | "assistant" | "action";
  content: string | null;
  created_at: Timestamp;
  citations: Citation[];
  approval: ApprovalCard | null;
  feedback: Feedback | null;
};

export type Run = {
  id: UUID;
  status: RunStatus;
  conversation_id: UUID;
};

export type ApiError = {
  code: string;
  message: string;
  retryable: boolean;
};

export type TurnResponse = {
  run_id: UUID;
  conversation_id: UUID;
  status: "completed" | "waiting_for_approval" | "failed";
  messages: Message[];
  pending_approval: ApprovalCard | null;
  error: ApiError | null;
};

export type HistoryResponse = {
  conversation: Conversation;
  messages: Message[];
  active_run: Run | null;
  pending_approval: ApprovalCard | null;
};

export type ArticleInput = { title: string; category: string; body: string };
export type ArticleSummary = {
  id: UUID;
  title: string;
  category: string;
  created_at: Timestamp;
  updated_at: Timestamp;
};
export type Article = ArticleSummary & { body: string };

export type ApiErrorEnvelope = {
  error: ApiError;
  details?: unknown;
};
