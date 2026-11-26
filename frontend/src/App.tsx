import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  CircleHelp,
  Clock3,
  CreditCard,
  Copy,
  FileText,
  Headset,
  Info,
  KeyRound,
  LogOut,
  Menu,
  MessageCircle,
  Plus,
  PanelTop,
  Pencil,
  Search,
  Send,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  UserRound,
  X,
} from "lucide-react";
import type {
  ApprovalCard as ApprovalCardType,
  Article,
  Customer,
  Feedback,
  Message,
} from "./api/types";
import { Badge } from "./components/ui/badge";
import { Button } from "./components/ui/button";
import { Input } from "./components/ui/input";
import { Textarea } from "./components/ui/textarea";
import {
  createInitialMessages,
  createConversationMessages,
  demoArticles,
  demoCustomers,
  demoConversations,
  emptyMessages,
} from "./data/demo";

type Section = "chat" | "knowledge" | "account";
type FeedbackDraft = { rating: "positive" | "negative"; comment: string };

const previewMode = true;

function newId() {
  return crypto.randomUUID();
}

function timeLabel(value: string) {
  return new Intl.DateTimeFormat("en", { hour: "numeric", minute: "2-digit" }).format(new Date(value));
}

function conversationTimeLabel(value: string) {
  const date = new Date(value);
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const messageDay = new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
  const dayOffset = Math.floor((today - messageDay) / 86_400_000);
  const day = dayOffset === 0 ? "Today" : dayOffset === 1 ? "Yesterday" : new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(date);
  return `${day} · ${timeLabel(value)}`;
}

function todayLabel() {
  return new Intl.DateTimeFormat("en", { weekday: "long", month: "long", day: "numeric" }).format(new Date());
}

function MarkdownContent({ content }: { content: string }) {
  return <ReactMarkdown className="markdown-content" remarkPlugins={[remarkGfm]} skipHtml>{content}</ReactMarkdown>;
}

function App() {
  const previewQuery = new URLSearchParams(window.location.search);
  const previewView = previewMode ? previewQuery.get("view") : null;
  const previewProfile = previewMode && ["workspace", "knowledge", "account"].includes(previewView ?? "")
    ? demoCustomers.find((profile) => profile.handle === previewQuery.get("profile")) ?? demoCustomers[0]
    : null;
  const [customer, setCustomer] = useState<Customer | null>(previewProfile);
  const [selectedProfile, setSelectedProfile] = useState(previewProfile?.id ?? demoCustomers[0].id);
  const [section, setSection] = useState<Section>(previewView === "knowledge" || previewView === "account" ? previewView : "chat");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [profileMenuOpen, setProfileMenuOpen] = useState(false);
  const [conversations, setConversations] = useState(() => previewProfile?.handle === "taylor"
    ? demoConversations.map((conversation, index) => index === 0 ? { ...conversation, title: "Failed payment" } : conversation)
    : demoConversations);
  const [activeConversationId, setActiveConversationId] = useState(demoConversations[0].id);
  const [messagesByConversation, setMessagesByConversation] = useState<Record<string, Message[]>>({});
  const [composer, setComposer] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [chatNotice, setChatNotice] = useState<string | null>(null);
  const [searchText, setSearchText] = useState("");
  const [articles, setArticles] = useState<Article[]>(demoArticles);
  const [selectedArticleId, setSelectedArticleId] = useState(demoArticles[0].id);
  const [articleQuery, setArticleQuery] = useState("");
  const [articleEditor, setArticleEditor] = useState<"closed" | "create" | "edit">("closed");
  const [articleDraft, setArticleDraft] = useState({ title: "", category: "", body: "" });
  const [articleDeleteId, setArticleDeleteId] = useState<string | null>(null);
  const [articleNotice, setArticleNotice] = useState<string | null>(null);

  function conversationsFor(profile: Customer) {
    return demoConversations.map((conversation, index) => index === 0 && profile.handle === "taylor"
      ? { ...conversation, title: "Failed payment" }
      : conversation);
  }

  const messages = useMemo(() => {
    if (!customer) return [];
    const activeTitle = conversations.find((conversation) => conversation.id === activeConversationId)?.title ?? "New conversation";
    return messagesByConversation[activeConversationId] ??
      createConversationMessages(customer, activeConversationId, activeTitle);
  }, [activeConversationId, conversations, customer, messagesByConversation]);

  const selectedArticle = articles.find((article) => article.id === selectedArticleId) ?? null;
  const activeConversation = conversations.find((conversation) => conversation.id === activeConversationId);

  function setCurrentMessages(update: (current: Message[]) => Message[]) {
    setMessagesByConversation((previous) => {
      const activeTitle = conversations.find((conversation) => conversation.id === activeConversationId)?.title ?? "New conversation";
      const current = previous[activeConversationId] ?? (customer
        ? createConversationMessages(customer, activeConversationId, activeTitle)
        : emptyMessages(activeConversationId, activeTitle));
      return { ...previous, [activeConversationId]: update(current) };
    });
  }

  function login() {
    const nextCustomer = demoCustomers.find((profile) => profile.id === selectedProfile) ?? demoCustomers[0];
    setCustomer(nextCustomer);
    setSection("chat");
    setActiveConversationId(demoConversations[0].id);
    setMessagesByConversation({ [demoConversations[0].id]: createInitialMessages(nextCustomer) });
    setConversations(conversationsFor(nextCustomer));
    setMobileNavOpen(false);
    setProfileMenuOpen(false);
  }

  function switchProfile() {
    setCustomer(null);
    setSelectedProfile(demoCustomers[0].id);
    setMessagesByConversation({});
    setActiveConversationId(demoConversations[0].id);
    setConversations(demoConversations);
    setSection("chat");
    setProfileMenuOpen(false);
  }

  function createConversation() {
    const id = newId();
    const createdAt = new Date().toISOString();
    setConversations((items) => [{ id, title: "New conversation", created_at: createdAt, updated_at: createdAt }, ...items]);
    setActiveConversationId(id);
    setMessagesByConversation((items) => ({ ...items, [id]: emptyMessages(id) }));
    setSection("chat");
    setMobileNavOpen(false);
    setComposer("");
  }

  function chooseConversation(id: string) {
    setActiveConversationId(id);
    setSection("chat");
    setChatNotice(null);
  }

  function makeAssistantMessage(content: string, citations: Message["citations"] = []): Message {
    return {
      id: newId(),
      conversation_id: activeConversationId,
      run_id: newId(),
      role: "assistant",
      content,
      created_at: new Date().toISOString(),
      citations,
      approval: null,
      feedback: null,
    };
  }

  function localAnswer(text: string): { content: string; articleId?: string; section?: string } {
    const normalized = text.toLowerCase();
    if (normalized.includes("refund")) {
      return {
        content: "Successful initial payments may be eligible for a refund request within 14 days. Renewals and payments already refunded or requested are excluded. Check the payment date and type before contacting support.",
        articleId: "00000000-0000-4000-8000-000000000050",
        section: "Eligibility",
      };
    }
    if (normalized.includes("payment") || normalized.includes("failed")) {
      const forTaylor = customer?.handle === "taylor";
      return {
        content: forTaylor
          ? "Your latest $39.00 USD Business renewal payment failed because of insufficient funds. You can check the available balance or contact your payment provider. This demo cannot retry the payment or change payment details."
          : "Your latest payment was successful: $15.00 USD. If you are troubleshooting another payment, check your payment provider for a decline reason. This demo cannot retry a payment or change payment details.",
        articleId: "00000000-0000-4000-8000-000000000051",
        section: "Safe next steps",
      };
    }
    if (normalized.includes("subscription") || normalized.includes("plan")) {
      const forTaylor = customer?.handle === "taylor";
      return {
        content: forTaylor
          ? "Your current subscription is Business, active at $39.00 per month."
          : "Your current subscription is Pro, active at $15.00 per month.",
      };
    }
    return {
      content: "I can help with subscriptions, payments, refund guidance, and account access. This local preview is not connected to the support service, so the answer is illustrative.",
    };
  }

  function submitMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const text = composer.trim();
    if (!text || isTyping) return;
    setChatNotice(null);
    const userMessage: Message = {
      id: newId(),
      conversation_id: activeConversationId,
      run_id: newId(),
      role: "user",
      content: text,
      created_at: new Date().toISOString(),
      citations: [],
      approval: null,
      feedback: null,
    };
    setCurrentMessages((items) => [...items, userMessage]);
    setConversations((items) => items.map((conversation) => conversation.id === activeConversationId
      ? { ...conversation, title: conversation.title === "New conversation" ? text.slice(0, 32) : conversation.title, updated_at: new Date().toISOString() }
      : conversation));
    setComposer("");
    setIsTyping(true);

    window.setTimeout(() => {
      if (/reset|password/i.test(text)) {
        const approval: ApprovalCardType = {
          action_id: newId(),
          action_type: "request_password_reset",
          status: "pending",
          account_display_name: customer?.display_name ?? "Demo customer",
          created_at: new Date().toISOString(),
          decided_at: null,
          result: null,
        };
        const actionMessage: Message = {
          id: newId(),
          conversation_id: activeConversationId,
          run_id: newId(),
          role: "action",
          content: null,
          created_at: new Date().toISOString(),
          citations: [],
          approval,
          feedback: null,
        };
        setCurrentMessages((items) => [...items, actionMessage]);
      } else {
        const result = localAnswer(text);
        const matchedArticle = result.articleId ? articles.find((article) => article.id === result.articleId) : undefined;
        const response = makeAssistantMessage(result.content, matchedArticle ? [{
          article_id: matchedArticle.id,
          chunk_id: newId(),
          article_title: matchedArticle.title,
          section: result.section ?? "Overview",
        }] : []);
        setCurrentMessages((items) => [...items, response]);
      }
      setIsTyping(false);
    }, 520);
  }

  function decideLocally(messageId: string, approval: ApprovalCardType, approved: boolean) {
    const resolvedAt = new Date().toISOString();
    const resolved: ApprovalCardType = {
      ...approval,
      status: approved ? "approved" : "rejected",
      decided_at: resolvedAt,
      result: null,
    };
    setCurrentMessages((items) => items.flatMap((item) => item.id === messageId
      ? [
          { ...item, approval: resolved },
          makeAssistantMessage(approved
            ? "Your choice is recorded in this browser preview, but the action has not been executed. No reset request was created, no email was sent, and no password changed."
            : "The simulated password-reset request was cancelled in this local preview. No reset request was created."),
        ]
      : [item]));
  }

  function setFeedback(messageId: string, draft: FeedbackDraft) {
    const feedback: Feedback = {
      rating: draft.rating,
      comment: draft.comment.trim() || null,
      updated_at: new Date().toISOString(),
    };
    setCurrentMessages((items) => items.map((item) => item.id === messageId ? { ...item, feedback } : item));
  }

  function openNewArticle() {
    setArticleDraft({ title: "", category: "", body: "" });
    setArticleEditor("create");
    setArticleNotice(null);
  }

  function openEditArticle(article: Article) {
    setSelectedArticleId(article.id);
    setArticleDraft({ title: article.title, category: article.category, body: article.body });
    setArticleEditor("edit");
    setArticleNotice(null);
  }

  function saveArticle(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!articleDraft.title.trim() || !articleDraft.category.trim() || !articleDraft.body.trim()) return;
    const timestamp = new Date().toISOString();
    if (articleEditor === "create") {
      const article: Article = {
        ...articleDraft,
        id: newId(),
        title: articleDraft.title.trim(),
        category: articleDraft.category.trim(),
        body: articleDraft.body,
        created_at: timestamp,
        updated_at: timestamp,
      };
      setArticles((items) => [article, ...items]);
      setSelectedArticleId(article.id);
      setArticleNotice("Article added to this local preview. It has not been indexed or saved to the service.");
    } else if (selectedArticle) {
      const updated: Article = {
        ...selectedArticle,
        ...articleDraft,
        title: articleDraft.title.trim(),
        category: articleDraft.category.trim(),
        updated_at: timestamp,
      };
      setArticles((items) => items.map((item) => item.id === updated.id ? updated : item));
      setArticleNotice("Preview updated in this browser only. The service has not indexed or saved this article.");
    }
    setArticleEditor("closed");
  }

  function deleteArticle(id: string) {
    const remaining = articles.filter((article) => article.id !== id);
    setArticles(remaining);
    if (selectedArticleId === id) setSelectedArticleId(remaining[0]?.id ?? "");
    setArticleDeleteId(null);
    setArticleNotice("Article removed from this local preview only. The service was not changed.");
  }

  if (!customer) {
    return (
      <LoginScreen
        selectedProfile={selectedProfile}
        onSelect={setSelectedProfile}
        onContinue={login}
      />
    );
  }

  const customerIsTaylor = customer.handle === "taylor";

  return (
    <div className="app-frame">
      {mobileNavOpen && <button aria-label="Close navigation" className="mobile-scrim" onClick={() => setMobileNavOpen(false)} />}
      <Sidebar
        customer={customer}
        section={section}
        isOpen={mobileNavOpen}
        conversationCount={conversations.length}
        onNavigate={(next) => { setSection(next); setMobileNavOpen(false); }}
        onSwitch={switchProfile}
        onHelp={createConversation}
      />
      <div className="app-main">
        <header className="topbar">
          <div className="topbar-title">
            <Button aria-label="Open navigation" className="mobile-menu" variant="quiet" size="icon" onClick={() => setMobileNavOpen(true)}>
              <Menu size={19} />
            </Button>
            <div>
              <h1>{section === "chat" ? "Your support space" : section === "knowledge" ? "Knowledge guide" : "Account details"}</h1>
              <p>{section === "chat" ? todayLabel() : section === "knowledge" ? "Find and manage support articles" : "Your current demo profile"}</p>
            </div>
          </div>
          <div className="topbar-right">
            {previewMode && <span className="preview-pill"><PanelTop size={14} aria-hidden="true" /> Local preview <span className="preview-divider" /> Unsaved</span>}
            <div className="profile-menu-wrap">
              <button aria-expanded={profileMenuOpen} aria-haspopup="menu" className="topbar-profile" onClick={() => setProfileMenuOpen((open) => !open)} onKeyDown={(event) => { if (event.key === "Escape") setProfileMenuOpen(false); }} title="Profile options">
                <Avatar customer={customer} size="small" />
                <span>{customer.display_name.split(" ")[0]}</span>
                <ChevronDown size={15} />
              </button>
              {profileMenuOpen && <div className="profile-menu" role="menu">
                <button role="menuitem" onClick={switchProfile}><UserRound size={15} /> Switch demo profile</button>
                <button role="menuitem" onClick={switchProfile}><LogOut size={15} /> Log out</button>
              </div>}
            </div>
          </div>
        </header>

        {section === "chat" && (
          <div className="workspace chat-workspace">
            <ConversationRail
              conversations={conversations.filter((conversation) => conversation.title.toLowerCase().includes(searchText.toLowerCase()))}
              activeId={activeConversationId}
              searchText={searchText}
              onSearch={setSearchText}
              onCreate={createConversation}
              onSelect={chooseConversation}
            />
            <ChatPanel
              customer={customer}
              messages={messages}
              isTyping={isTyping}
              composer={composer}
              notice={chatNotice}
              onComposerChange={setComposer}
              onSubmit={submitMessage}
              onDecide={decideLocally}
              onFeedback={setFeedback}
              onDismissNotice={() => setChatNotice(null)}
              conversationTitle={activeConversation?.title ?? "New conversation"}
            />
            <AccountContext customer={customer} onOpenAccount={() => setSection("account")} />
          </div>
        )}

        {section === "knowledge" && (
          <KnowledgeWorkspace
            articles={articles.filter((article) => `${article.title} ${article.category}`.toLowerCase().includes(articleQuery.toLowerCase()))}
            allArticles={articles}
            selectedArticle={selectedArticle}
            query={articleQuery}
            notice={articleNotice}
            editor={articleEditor}
            draft={articleDraft}
            deleteId={articleDeleteId}
            onQuery={setArticleQuery}
            onSelect={setSelectedArticleId}
            onCreate={openNewArticle}
            onEdit={openEditArticle}
            onDraft={setArticleDraft}
            onEditorClose={() => setArticleEditor("closed")}
            onSave={saveArticle}
            onRequestDelete={setArticleDeleteId}
            onDelete={deleteArticle}
          />
        )}

        {section === "account" && (
          <AccountPage customer={customer} isTaylor={customerIsTaylor} onSwitch={switchProfile} />
        )}
      </div>
    </div>
  );
}

function Avatar({ customer, size = "regular" }: { customer: Customer; size?: "small" | "regular" }) {
  return <span className={`avatar avatar-${size}`} aria-hidden="true">{customer.display_name.split(" ").map((part) => part[0]).join("")}</span>;
}

function LoginScreen({
  selectedProfile,
  onSelect,
  onContinue,
}: {
  selectedProfile: string;
  onSelect: (id: string) => void;
  onContinue: () => void;
}) {
  return (
    <main className="login-page">
      <div className="login-shell">
        <section className="login-story">
          <BrandMark />
          <div className="login-copy">
            <h1>A clear next step<br />starts with a question.</h1>
            <p className="login-description">Get thoughtful answers about your account, grounded in trusted guidance and the details that matter to you.</p>
            <div className="login-proof"><span className="proof-check"><Check size={15} /></span><span>Helpful answers, with their sources close by.</span></div>
          </div>
          <p className="login-footnote">A fictional support experience for demonstration.</p>
        </section>
        <section className="login-form-wrap">
          <div className="login-form">
            <div className="login-heading">
              <h2>Choose your profile</h2>
              <p>Select one of the sample accounts to explore support.</p>
            </div>
            <div className="profile-options" role="radiogroup" aria-label="Demo customer profile">
              {demoCustomers.map((profile) => {
                const selected = selectedProfile === profile.id;
                const taylor = profile.handle === "taylor";
                return (
                  <button
                  aria-checked={selected}
                  className={`profile-option ${selected ? "is-selected" : ""}`}
                  id={`profile-${profile.id}`}
                  key={profile.id}
                  onClick={() => onSelect(profile.id)}
                  onKeyDown={(event) => {
                    if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
                    event.preventDefault();
                    const currentIndex = demoCustomers.findIndex((item) => item.id === profile.id);
                    const nextIndex = (currentIndex + (event.key === "ArrowLeft" || event.key === "ArrowUp" ? demoCustomers.length - 1 : 1)) % demoCustomers.length;
                    const nextProfile = demoCustomers[nextIndex];
                    onSelect(nextProfile.id);
                    document.getElementById(`profile-${nextProfile.id}`)?.focus();
                  }}
                  role="radio"
                    type="button"
                  >
                    <span className={`profile-avatar ${taylor ? "avatar-lilac" : "avatar-peach"}`}>{profile.display_name.split(" ").map((part) => part[0]).join("")}</span>
                    <span className="profile-info"><strong>{profile.display_name}</strong><small>{taylor ? "Business plan · Payment support" : "Pro plan · Account support"}</small></span>
                    <span className="radio-mark">{selected && <span />}</span>
                  </button>
                );
              })}
            </div>
            <Button className="login-submit" onClick={onContinue}>Continue as {demoCustomers.find((profile) => profile.id === selectedProfile)?.display_name.split(" ")[0]} <ArrowRight size={17} /></Button>
            <div className="login-safety"><Info size={15} /><span>No password needed. Demo profiles contain fictional data.</span></div>
          </div>
          <div className="login-bottom">Customer support <span>·</span> Demo environment</div>
        </section>
      </div>
    </main>
  );
}

function BrandMark() {
  return (
    <a className="brand-mark" href="#home" aria-label="Support demo home">
      <span className="brand-symbol"><Headset size={19} strokeWidth={1.8} aria-hidden="true" /></span>
      <span>support<span className="brand-support">customer care</span></span>
    </a>
  );
}

function Sidebar({
  customer,
  section,
  isOpen,
  conversationCount,
  onNavigate,
  onSwitch,
  onHelp,
}: {
  customer: Customer;
  section: Section;
  isOpen: boolean;
  conversationCount: number;
  onNavigate: (section: Section) => void;
  onSwitch: () => void;
  onHelp: () => void;
}) {
  return (
    <aside className={`sidebar ${isOpen ? "sidebar-open" : ""}`}>
      <div className="sidebar-top"><BrandMark /><button className="close-sidebar" aria-label="Close navigation" onClick={() => onNavigate(section)}><X size={18} /></button></div>
      <div className="sidebar-label">YOUR SPACE</div>
      <button className="sidebar-profile" onClick={onSwitch}>
        <Avatar customer={customer} />
        <span><strong>{customer.display_name}</strong><small>{customer.handle === "taylor" ? "Business" : "Pro"} account</small></span>
        <ChevronDown size={15} />
      </button>
      <nav aria-label="Main navigation" className="primary-nav">
        <button className={section === "chat" ? "nav-item active" : "nav-item"} onClick={() => onNavigate("chat")}><MessageCircle size={18} /><span>Conversations</span><span className="nav-count">{conversationCount}</span></button>
        <button className={section === "knowledge" ? "nav-item active" : "nav-item"} onClick={() => onNavigate("knowledge")}><BookOpen size={18} /><span>Knowledge guide</span></button>
        <button className={section === "account" ? "nav-item active" : "nav-item"} onClick={() => onNavigate("account")}><UserRound size={18} /><span>Account details</span></button>
      </nav>
      <div className="sidebar-bottom">
        <button className="sidebar-help" onClick={onHelp}><span className="help-icon"><CircleHelp size={17} /></span><div><b>Ask for support</b><small>Start a new conversation</small></div><ArrowRight size={15} /></button>
        <div className="sidebar-bottom-row"><span>Support demo</span><span>Local preview</span></div>
      </div>
    </aside>
  );
}

function ConversationRail({
  conversations,
  activeId,
  searchText,
  onSearch,
  onCreate,
  onSelect,
}: {
  conversations: typeof demoConversations;
  activeId: string;
  searchText: string;
  onSearch: (value: string) => void;
  onCreate: () => void;
  onSelect: (id: string) => void;
}) {
  return (
    <aside className="conversation-rail">
      <div className="conversation-heading"><div><h2>Conversations</h2><span>Pick up where you left off</span></div><Button aria-label="Start a new conversation" className="new-conversation" size="icon" onClick={onCreate}><Plus size={18} /></Button></div>
      <label className="search-box"><Search size={16} /><input aria-label="Search conversations" placeholder="Search conversations" value={searchText} onChange={(event) => onSearch(event.target.value)} /></label>
      <div className="conversation-list-heading"><span>RECENT</span></div>
      <nav className="conversation-list" aria-label="Recent conversations">
        {conversations.map((conversation, index) => (
          <button key={conversation.id} className={`conversation-item ${conversation.id === activeId ? "conversation-active" : ""}`} onClick={() => onSelect(conversation.id)}>
            <span className={`conversation-icon icon-tone-${index % 3}`}><MessageCircle size={16} /></span>
            <span className="conversation-copy"><strong>{conversation.title}</strong><small>{conversationTimeLabel(conversation.updated_at)}</small></span>
          </button>
        ))}
        {conversations.length === 0 && <div className="no-results"><Search size={18} /><span>No conversations match that search.</span></div>}
      </nav>
      <div className="conversation-rail-foot"><Clock3 size={15} /><span>These conversations are preview examples in this browser.</span></div>
    </aside>
  );
}

function ChatPanel({
  customer,
  messages,
  isTyping,
  composer,
  notice,
  onComposerChange,
  onSubmit,
  onDecide,
  onFeedback,
  onDismissNotice,
  conversationTitle,
}: {
  customer: Customer;
  messages: Message[];
  isTyping: boolean;
  composer: string;
  notice: string | null;
  onComposerChange: (value: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
  onDecide: (messageId: string, approval: ApprovalCardType, approved: boolean) => void;
  onFeedback: (messageId: string, draft: FeedbackDraft) => void;
  onDismissNotice: () => void;
  conversationTitle: string;
}) {
  const messageScrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (messageScrollRef.current) messageScrollRef.current.scrollTop = messageScrollRef.current.scrollHeight;
  }, [messages, isTyping]);

  const activeApproval = messages.some((message) => message.approval?.status === "pending");

  return (
    <section className="chat-panel" aria-label="Support conversation">
      <div className="chat-heading">
        <div><h2>{conversationTitle}</h2><p>Support conversation <span className="dot-separator">·</span> Started today</p></div>
        <div className="chat-heading-actions"><Badge tone="neutral">Local session</Badge></div>
      </div>
      {previewMode && <div className="preview-note"><span className="preview-note-icon"><Info size={16} /></span><span><strong>Preview data</strong> — Messages, feedback, and actions stay in this browser. Nothing is sent or saved to the support service.</span></div>}
      {notice && <div className="inline-notice" role="status">{notice}<button onClick={onDismissNotice} aria-label="Dismiss notice"><X size={15} /></button></div>}
      <div className="message-scroll" ref={messageScrollRef}>
        <div className="conversation-date"><span />{todayLabel()}<span /></div>
        {messages.map((message) => {
          if (message.role === "user") return <UserMessage key={message.id} message={message} customer={customer} />;
          if (message.role === "action" && message.approval) {
            return <ApprovalCard key={message.id} messageId={message.id} approval={message.approval} onDecide={onDecide} />;
          }
          if (message.role === "assistant") return <AssistantMessage key={message.id} message={message} onFeedback={onFeedback} />;
          return null;
        })}
        {isTyping && <div className="typing-row"><span className="assistant-avatar"><MessageCircle size={16} /></span><div className="typing-bubble"><span /><span /><span /></div><small>Support assistant is thinking</small></div>}
        {messages.length <= 1 && !isTyping && <div className="suggestions"><span>Try asking</span><button onClick={() => onComposerChange("What is my current subscription?")}>What is my current subscription?</button><button onClick={() => onComposerChange("How do I reset my password?")}>How do I reset my password?</button></div>}
      </div>
      <form className="composer-wrap" onSubmit={onSubmit}>
        {activeApproval && <div className="composer-locked"><KeyRound size={14} /> Resolve the pending confirmation above before sending another message.</div>}
        <div className={`composer ${activeApproval ? "composer-disabled" : ""}`}>
          <textarea
            aria-label="Write a message"
            placeholder="Ask a question about your account…"
            value={composer}
            onChange={(event) => onComposerChange(event.target.value)}
            onKeyDown={(event) => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); event.currentTarget.form?.requestSubmit(); } }}
            disabled={isTyping || activeApproval}
            rows={1}
          />
          <div className="composer-footer"><span>Sources are shown when available</span><Button aria-label="Send message" className="send-button" size="icon" disabled={!composer.trim() || isTyping || activeApproval}><Send size={17} /></Button></div>
        </div>
        <p className="composer-disclaimer">Support answers can be mistaken. Check important details with your service provider.</p>
      </form>
    </section>
  );
}

function UserMessage({ message, customer }: { message: Message; customer: Customer }) {
  return (
    <div className="message-row user-row">
      <div className="user-message-content"><div className="message-meta"><span>You</span><time>{timeLabel(message.created_at)}</time></div><div className="user-bubble">{message.content}</div></div>
      <Avatar customer={customer} size="small" />
    </div>
  );
}

function AssistantMessage({ message, onFeedback }: { message: Message; onFeedback: (id: string, draft: FeedbackDraft) => void }) {
  const [draft, setDraft] = useState<FeedbackDraft | null>(null);
  const [saved, setSaved] = useState(false);
  const [copied, setCopied] = useState(false);

  function copyAnswer() {
    if (!message.content) return;
    void navigator.clipboard?.writeText(message.content).then(() => {
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1700);
    });
  }

  return (
    <div className="assistant-row">
      <span className="assistant-avatar"><MessageCircle size={16} /></span>
      <article className="assistant-message">
        <div className="message-meta"><strong>Support assistant</strong><time>{timeLabel(message.created_at)}</time><Badge tone="neutral">Preview response</Badge></div>
        <div className="assistant-copy"><MarkdownContent content={message.content ?? ""} /></div>
        {message.citations.length > 0 && <div className="citation-list" aria-label="Sources">
          <span className="citation-label"><BookOpen size={14} /> From the knowledge guide</span>
          {message.citations.map((citation) => <span className="citation-chip" key={citation.chunk_id}><FileText size={14} /><span><strong>{citation.article_title}</strong><small>{citation.section}</small></span></span>)}
        </div>}
        <div className="message-actions"><span>{message.feedback ? "Thanks for your feedback" : "Was this helpful?"}</span>
          <button className={`feedback-button ${message.feedback?.rating === "positive" ? "feedback-selected" : ""}`} aria-label="This answer was helpful" aria-pressed={message.feedback?.rating === "positive"} onClick={() => { setDraft({ rating: "positive", comment: message.feedback?.comment ?? "" }); setSaved(false); }}><ThumbsUp size={15} /></button>
          <button className={`feedback-button ${message.feedback?.rating === "negative" ? "feedback-selected" : ""}`} aria-label="This answer was not helpful" aria-pressed={message.feedback?.rating === "negative"} onClick={() => { setDraft({ rating: "negative", comment: message.feedback?.comment ?? "" }); setSaved(false); }}><ThumbsDown size={15} /></button>
          <span className="action-spacer" />
          <button className="text-action" onClick={copyAnswer}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? "Copied" : "Copy"}</button>
        </div>
        {draft && <form className="feedback-form" onSubmit={(event) => { event.preventDefault(); onFeedback(message.id, draft); setSaved(true); setDraft(null); }}>
          <label htmlFor={`feedback-${message.id}`}>{draft.rating === "positive" ? "What worked well?" : "What could be clearer?"} <span>Optional</span></label>
          <Input id={`feedback-${message.id}`} value={draft.comment} onChange={(event) => setDraft({ ...draft, comment: event.target.value })} placeholder="Add a comment" maxLength={500} />
          <Button size="sm" type="submit">Save feedback</Button>
          <Button size="sm" variant="ghost" type="button" onClick={() => setDraft(null)}>Cancel</Button>
        </form>}
        {saved && <p className="feedback-saved" role="status"><CheckCircle2 size={14} /> Feedback saved in this local preview.</p>}
      </article>
    </div>
  );
}

function ApprovalCard({
  messageId,
  approval,
  onDecide,
}: {
  messageId: string;
  approval: ApprovalCardType;
  onDecide: (messageId: string, approval: ApprovalCardType, approved: boolean) => void;
}) {
  const [copied, setCopied] = useState(false);
  const statusLabel = approval.status === "pending"
    ? "Waiting for you"
    : approval.status === "approved"
      ? "Approved · not executed"
      : approval.status === "executed"
        ? "Request created"
        : approval.status === "rejected"
          ? "Cancelled"
          : approval.status;

  async function copyLink() {
    if (!approval.result) return;
    await navigator.clipboard?.writeText(approval.result.reset_url);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  }

  return (
    <div className="approval-row"><span className="assistant-avatar approval-avatar"><KeyRound size={16} /></span>
      <section className={`approval-card approval-${approval.status}`} aria-label="Password reset confirmation">
        <div className="approval-heading"><span className="approval-icon"><KeyRound size={17} /></span><div><h3>Confirm password reset</h3><p>Account action · {timeLabel(approval.created_at)}</p></div><Badge tone={approval.status === "pending" ? "warning" : approval.status === "executed" ? "success" : "neutral"}>{statusLabel}</Badge></div>
        <p className="approval-explanation">Create a simulated password-reset request for <strong>{approval.account_display_name}</strong>. Your password will not change.</p>
        {approval.status === "pending" && <>
          <div className="approval-preview-warning"><Info size={15} /><span>Preview only · no request is sent or saved.</span></div>
          <div className="approval-actions"><Button onClick={() => onDecide(messageId, approval, true)}>Confirm</Button><Button variant="secondary" onClick={() => onDecide(messageId, approval, false)}>Cancel</Button></div>
        </>}
        {approval.status === "approved" && <p className="approval-outcome"><CheckCircle2 size={15} /> Approval recorded locally. The operation has not been executed.</p>}
        {approval.status === "rejected" && <p className="approval-outcome"><X size={15} /> No reset request was created in this preview.</p>}
        {approval.status === "executed" && approval.result && <div className="reset-result"><p><CheckCircle2 size={15} /> Reset request created.</p><span className="simulated-label">SIMULATED · NON-OPERATIONAL LINK</span><div className="link-copy"><code>{approval.result.reset_url}</code><Button variant="secondary" size="sm" onClick={copyLink}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? "Copied" : "Copy link"}</Button></div><small>No email was sent and no password changed.</small></div>}
      </section>
    </div>
  );
}

function AccountContext({ customer, onOpenAccount }: { customer: Customer; onOpenAccount: () => void }) {
  const taylor = customer.handle === "taylor";
  return (
    <aside className="account-context" aria-label="Account summary">
      <div className="context-heading"><h2>Your account</h2><Badge tone="neutral">Demo</Badge></div>
      <div className="context-profile"><Avatar customer={customer} /><div><strong>{customer.display_name}</strong><small>{taylor ? "Business plan" : "Pro plan"}</small></div></div>
      <div className="account-card subscription-card"><div className="account-card-title"><span className="context-icon icon-sage"><BookOpen size={16} /></span><span>SUBSCRIPTION</span></div><div className="plan-line"><strong>{taylor ? "Business" : "Pro"}</strong><Badge tone="success">Active</Badge></div><p className="amount-line">${taylor ? "39.00" : "15.00"}<span> / month</span></p><div className="account-card-footer"><span>Monthly billing</span><button onClick={onOpenAccount}>View account <ArrowRight size={12} /></button></div></div>
      <div className="account-card payment-card"><div className="account-card-title"><span className={`context-icon ${taylor ? "icon-peach" : "icon-sage"}`}><CreditCard size={16} /></span><span>LATEST PAYMENT</span></div><div className="payment-amount">${taylor ? "39.00" : "15.00"}<span> USD</span></div><div className="payment-status"><span className={`payment-dot ${taylor ? "payment-failed" : ""}`} />{taylor ? "Failed renewal" : "Successful initial payment"}</div><p className="payment-date">{taylor ? <>Yesterday <span>·</span> Insufficient funds</> : "5 days ago"}</p></div>
      {taylor && <div className="context-tip"><span className="tip-icon"><CircleHelp size={16} /></span><p><strong>Payment help</strong><br />Check your balance or contact your payment provider. This demo cannot retry payments.</p></div>}
      <p className="context-footnote"><Info size={14} /> Fictional demo information</p>
    </aside>
  );
}

function KnowledgeWorkspace({
  articles,
  allArticles,
  selectedArticle,
  query,
  notice,
  editor,
  draft,
  deleteId,
  onQuery,
  onSelect,
  onCreate,
  onEdit,
  onDraft,
  onEditorClose,
  onSave,
  onRequestDelete,
  onDelete,
}: {
  articles: Article[];
  allArticles: Article[];
  selectedArticle: Article | null;
  query: string;
  notice: string | null;
  editor: "closed" | "create" | "edit";
  draft: { title: string; category: string; body: string };
  deleteId: string | null;
  onQuery: (value: string) => void;
  onSelect: (id: string) => void;
  onCreate: () => void;
  onEdit: (article: Article) => void;
  onDraft: (draft: { title: string; category: string; body: string }) => void;
  onEditorClose: () => void;
  onSave: (event: FormEvent<HTMLFormElement>) => void;
  onRequestDelete: (id: string | null) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="knowledge-workspace">
      <aside className="article-rail">
        <div className="article-rail-head"><div><h2>Articles</h2><span>{allArticles.length} guides</span></div><Button aria-label="Create article" size="icon" onClick={onCreate}><Plus size={18} /></Button></div>
        <label className="search-box article-search"><Search size={16} /><input aria-label="Search articles" placeholder="Search articles" value={query} onChange={(event) => onQuery(event.target.value)} /></label>
        <div className="article-list">
          {articles.map((article) => <button key={article.id} className={`article-list-item ${selectedArticle?.id === article.id && editor === "closed" ? "article-selected" : ""}`} onClick={() => { onSelect(article.id); onEditorClose(); }}><span className="article-icon"><FileText size={16} /></span><span><strong>{article.title}</strong><small>{article.category}</small></span><ArrowRight className="article-list-arrow" size={14} /></button>)}
          {articles.length === 0 && <div className="no-results"><Search size={18} /><span>No articles found.</span></div>}
        </div>
        <div className="article-rail-note"><Info size={15} /> Changes in this preview stay in your browser.</div>
      </aside>
      <section className="article-detail">
        {notice && <div className="inline-notice article-notice" role="status">{notice}</div>}
        {editor !== "closed" ? (
          <form className="article-editor" onSubmit={onSave}>
            <div className="article-editor-top"><div><Button variant="quiet" size="sm" type="button" onClick={onEditorClose}><ArrowLeft size={15} /> Back to article</Button><h2>{editor === "create" ? "Create an article" : "Edit article"}</h2><p>Write clear, useful guidance for customers.</p></div><Badge tone="neutral">Local preview</Badge></div>
            <label className="field-label">Title<Input required maxLength={160} value={draft.title} onChange={(event) => onDraft({ ...draft, title: event.target.value })} placeholder="e.g. Understanding your subscription" /></label>
            <label className="field-label">Category<Input required maxLength={80} value={draft.category} onChange={(event) => onDraft({ ...draft, category: event.target.value })} placeholder="e.g. Billing" /></label>
            <label className="field-label">Article body <span>Markdown supported</span><Textarea required maxLength={20_000} rows={14} value={draft.body} onChange={(event) => onDraft({ ...draft, body: event.target.value })} placeholder="## Start with a heading\n\nWrite the article content here…" /></label>
            <div className="editor-actions"><Button type="submit">{editor === "create" ? "Add to preview" : "Save preview changes"}</Button><Button type="button" variant="secondary" onClick={onEditorClose}>Cancel</Button></div>
          </form>
        ) : selectedArticle ? (
          <article className="article-reading">
            <div className="article-detail-top"><div className="article-breadcrumb"><span>Knowledge guide</span><ArrowRight size={13} /><span>{selectedArticle.category}</span></div><div className="article-tools"><Button variant="secondary" size="sm" onClick={() => onEdit(selectedArticle)}><Pencil size={14} /> Edit</Button><Button variant="quiet" size="icon" aria-label="Delete this article" onClick={() => onRequestDelete(selectedArticle.id)}><Trash2 size={16} /></Button></div></div>
            <Badge tone="accent">{selectedArticle.category}</Badge>
            <h2>{selectedArticle.title}</h2>
            <div className="article-meta"><span>Updated {new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(new Date(selectedArticle.updated_at))}</span><Badge tone="warning">Preview content</Badge></div>
            <div className="article-body"><MarkdownContent content={selectedArticle.body} /></div>
            <div className="article-source-note"><BookOpen size={16} /><p><strong>Article in the support guide</strong><br />This article appears as a source when it is retrieved by the support assistant. Preview edits are not indexed.</p></div>
            {deleteId === selectedArticle.id && <div className="delete-confirm" role="alert"><div><strong>Remove this article from the preview?</strong><span>This does not delete or change anything in the service.</span></div><div><Button variant="destructive" size="sm" onClick={() => onDelete(selectedArticle.id)}>Remove article</Button><Button variant="secondary" size="sm" onClick={() => onRequestDelete(null)}>Keep it</Button></div></div>}
          </article>
        ) : (
          <div className="empty-articles"><span className="empty-icon"><BookOpen size={23} /></span><h2>{allArticles.length ? "Choose an article" : "Your guide is ready for its first article"}</h2><p>Select an article from the list or create a new one to get started.</p><Button onClick={onCreate}><Plus size={16} /> Create an article</Button></div>
        )}
      </section>
    </div>
  );
}

function AccountPage({ customer, isTaylor, onSwitch }: { customer: Customer; isTaylor: boolean; onSwitch: () => void }) {
  return (
    <div className="account-page">
      <div className="account-page-heading"><div><h2>Your account</h2><p>Information shown here belongs to your selected demo profile.</p></div><Button variant="secondary" onClick={onSwitch}><UserRound size={15} /> Switch profile</Button></div>
      <div className="account-page-grid">
        <section className="account-overview-card"><div className="account-overview-header"><Avatar customer={customer} /><div><h3>{customer.display_name}</h3><p>Demo customer · {customer.handle}</p></div><Badge tone="accent">Fictional profile</Badge></div><div className="account-detail-row"><span>Profile type</span><strong>Demo customer</strong></div><div className="account-detail-row"><span>Plan</span><strong>{isTaylor ? "Business" : "Pro"}</strong></div><div className="account-detail-row"><span>Monthly billing</span><strong>${isTaylor ? "39.00" : "15.00"} USD</strong></div><div className="account-detail-row"><span>Subscription status</span><Badge tone="success">Active</Badge></div></section>
        <section className="account-overview-card payment-overview"><div className="overview-section-title"><span className="context-icon icon-peach"><CreditCard size={17} /></span><div><h3>Latest payment</h3><p>Most recent payment activity</p></div></div><div className="payment-large">${isTaylor ? "39.00" : "15.00"}<small> USD</small></div><Badge tone={isTaylor ? "danger" : "success"}>{isTaylor ? "Failed · Renewal" : "Successful · Initial payment"}</Badge><p className="payment-explainer">{isTaylor ? "Failure reason: insufficient funds. Check with your bank or payment provider. This demo cannot retry the payment." : "A successful initial payment dated five days ago."}</p></section>
        <section className="account-safety-card"><span className="safety-icon"><Info size={19} /></span><div><h3>About demo accounts</h3><p>These profiles use fictional data. Choosing a different profile clears the current account’s conversations and feedback from this browser view.</p><button onClick={onSwitch}>Choose another profile <ArrowRight size={14} /></button></div></section>
      </div>
      <div className="account-footer-note"><Info size={14} /> No real payment, password, or personal account data is connected to this demo.</div>
    </div>
  );
}

export default App;
