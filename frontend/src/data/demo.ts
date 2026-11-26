import type {
  ApprovalCard,
  Article,
  Conversation,
  Customer,
  Message,
} from "../api/types";

const now = new Date();
const ago = (minutes: number) => new Date(now.getTime() - minutes * 60_000).toISOString();

export const demoCustomers: Customer[] = [
  { id: "00000000-0000-4000-8000-000000000001", handle: "alex", display_name: "Alex" },
  { id: "00000000-0000-4000-8000-000000000002", handle: "taylor", display_name: "Taylor" },
];

export const demoConversations: Conversation[] = [
  { id: "00000000-0000-4000-8000-000000000010", title: "Refund policy", created_at: ago(90), updated_at: ago(3) },
  { id: "00000000-0000-4000-8000-000000000011", title: "My subscription", created_at: ago(220), updated_at: ago(35) },
  { id: "00000000-0000-4000-8000-000000000012", title: "Reset my password", created_at: ago(1440), updated_at: ago(1440) },
];

const pendingApproval: ApprovalCard = {
  action_id: "00000000-0000-4000-8000-000000000020",
  action_type: "request_password_reset",
  status: "pending",
  account_display_name: "Alex",
  created_at: ago(3),
  decided_at: null,
  result: null,
};

export function createInitialMessages(customer: Customer): Message[] {
  const isTaylor = customer.handle === "taylor";
  const conversationId = "00000000-0000-4000-8000-000000000010";
  const userQuestion = isTaylor
    ? "My payment failed. What should I do? Can I also reset my password?"
    : "What is your refund policy? Can I also reset my password?";
  const articleId = isTaylor
    ? "00000000-0000-4000-8000-000000000051"
    : "00000000-0000-4000-8000-000000000050";
  const answer = isTaylor
    ? "Your latest $39.00 USD Business renewal failed because of insufficient funds. Check your balance or contact your provider; this demo cannot retry it."
    : "Successful initial payments may qualify within 14 days; renewals and payments already refunded or requested are excluded.";

  return [
    {
      id: "00000000-0000-4000-8000-000000000030",
      conversation_id: conversationId,
      run_id: "00000000-0000-4000-8000-000000000040",
      role: "user",
      content: userQuestion,
      created_at: ago(12),
      citations: [],
      approval: null,
      feedback: null,
    },
    {
      id: "00000000-0000-4000-8000-000000000031",
      conversation_id: conversationId,
      run_id: "00000000-0000-4000-8000-000000000040",
      role: "assistant",
      content: answer,
      created_at: ago(11),
      citations: [
        {
          article_id: articleId,
          chunk_id: isTaylor
            ? "00000000-0000-4000-8000-000000000061"
            : "00000000-0000-4000-8000-000000000060",
          article_title: isTaylor ? "Failed payment troubleshooting" : "Refund policy",
          section: isTaylor ? "Safe next steps" : "Eligibility",
        },
      ],
      approval: null,
      feedback: { rating: "positive", comment: null, updated_at: ago(8) },
    },
    {
      id: "00000000-0000-4000-8000-000000000033",
      conversation_id: conversationId,
      run_id: "00000000-0000-4000-8000-000000000040",
      role: "action",
      content: null,
      created_at: ago(3),
      citations: [],
      approval: isTaylor ? { ...pendingApproval, action_id: "00000000-0000-4000-8000-000000000021", account_display_name: customer.display_name } : pendingApproval,
      feedback: null,
    },
  ];
}

export function createConversationMessages(customer: Customer, conversationId: string, title: string): Message[] {
  if (conversationId === demoConversations[0].id) return createInitialMessages(customer);

  if (conversationId === demoConversations[1].id) {
    const taylor = customer.handle === "taylor";
    return [
      {
        id: "00000000-0000-4000-8000-000000000034",
        conversation_id: conversationId,
        run_id: "00000000-0000-4000-8000-000000000042",
        role: "user",
        content: "What plan am I on right now?",
        created_at: ago(38),
        citations: [],
        approval: null,
        feedback: null,
      },
      {
        id: "00000000-0000-4000-8000-000000000035",
        conversation_id: conversationId,
        run_id: "00000000-0000-4000-8000-000000000042",
        role: "assistant",
        content: taylor
          ? "You’re on the Business plan, active at $39.00 per month."
          : "You’re on the Pro plan, active at $15.00 per month.",
        created_at: ago(37),
        citations: [],
        approval: null,
        feedback: null,
      },
    ];
  }

  if (conversationId === demoConversations[2].id) {
    const rejectedApproval: ApprovalCard = {
      ...pendingApproval,
      action_id: "00000000-0000-4000-8000-000000000022",
      status: "rejected",
      account_display_name: customer.display_name,
      decided_at: ago(1430),
    };
    return [
      {
        id: "00000000-0000-4000-8000-000000000036",
        conversation_id: conversationId,
        run_id: "00000000-0000-4000-8000-000000000043",
        role: "user",
        content: "Could you reset my password?",
        created_at: ago(1440),
        citations: [],
        approval: null,
        feedback: null,
      },
      {
        id: "00000000-0000-4000-8000-000000000037",
        conversation_id: conversationId,
        run_id: "00000000-0000-4000-8000-000000000043",
        role: "action",
        content: null,
        created_at: ago(1435),
        citations: [],
        approval: rejectedApproval,
        feedback: null,
      },
      {
        id: "00000000-0000-4000-8000-000000000038",
        conversation_id: conversationId,
        run_id: "00000000-0000-4000-8000-000000000043",
        role: "assistant",
        content: "The request was cancelled. No password changed and no reset request was created.",
        created_at: ago(1434),
        citations: [],
        approval: null,
        feedback: null,
      },
    ];
  }

  return emptyMessages(conversationId, title);
}

export const demoArticles: Article[] = [
  {
    id: "00000000-0000-4000-8000-000000000050",
    title: "Refund policy",
    category: "Billing",
    created_at: ago(30_000),
    updated_at: ago(30_000),
    body: "## Eligibility\nSuccessful initial payments may be eligible for a refund request within 14 days. Renewals are excluded. Payments already refunded or requested are excluded.\n\n## How to ask\nContact support with the payment date and the reason for your request. This article describes public policy and does not determine customer-specific eligibility.",
  },
  {
    id: "00000000-0000-4000-8000-000000000051",
    title: "Failed payment troubleshooting",
    category: "Billing",
    created_at: ago(28_000),
    updated_at: ago(28_000),
    body: "## Common causes\nA payment can fail because of insufficient funds, an expired payment method, or a temporary issue with the payment provider.\n\n## Safe next steps\nCheck with your bank or payment provider and make sure funds are available. Support cannot retry a payment or change payment details in this demo.",
  },
  {
    id: "00000000-0000-4000-8000-000000000052",
    title: "Password reset",
    category: "Account access",
    created_at: ago(25_000),
    updated_at: ago(25_000),
    body: "## Requesting a reset\nSupport can prepare a simulated password-reset request after you explicitly confirm it.\n\n## What to expect\nThe demo returns a non-operational example.invalid link. No email is sent and no password changes.",
  },
  {
    id: "00000000-0000-4000-8000-000000000053",
    title: "Plans and subscriptions",
    category: "Subscriptions",
    created_at: ago(22_000),
    updated_at: ago(22_000),
    body: "## Monthly plans\nFree is $0 per month, Pro is $15 per month, and Business is $39 per month.\n\n## Subscription status\nYour current plan and status are available from your account summary. This demo does not change plans.",
  },
];

export function emptyMessages(conversationId: string, title = "New conversation"): Message[] {
  return [
    {
      id: crypto.randomUUID(),
      conversation_id: conversationId,
      run_id: null,
      role: "assistant",
      content: title === "New conversation"
        ? "Hi! I can help with your subscription, payments, refund policy, and account access. What would you like to know?"
        : `This is the preview history for “${title}”. Ask a question to continue this conversation.`,
      created_at: new Date().toISOString(),
      citations: [],
      approval: null,
      feedback: null,
    },
  ];
}
