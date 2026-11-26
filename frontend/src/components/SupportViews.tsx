import { useEffect, useRef, useState, type FormEvent } from "react";
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
  Copy,
  FileText,
  Headset,
  Info,
  KeyRound,
  MessageCircle,
  Plus,
  Pencil,
  Search,
  Send,
  ThumbsDown,
  ThumbsUp,
  Trash2,
  X,
} from "lucide-react";
import type {
  ApprovalCard as ApprovalCardType,
  Article,
  Customer,
  Conversation,
  Message,
} from "../api/types";
import { Badge } from "./ui/badge";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Textarea } from "./ui/textarea";


type Section = "chat" | "account";
type FeedbackDraft = { rating: "positive" | "negative"; comment: string };

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

function Avatar({ customer, size = "regular" }: { customer: Customer; size?: "small" | "regular" }) {
  const tone = customer.handle === "taylor" ? "avatar-lilac" : "avatar-peach";
  return <span className={`avatar avatar-${size} ${tone}`} aria-hidden="true">{customer.display_name.split(" ").map((part) => part[0]).join("")}</span>;
}

export function LoginScreen({
  selectedProfile,
  onSelect,
  onContinue,
  onKnowledge,
  profiles = [],
  loading = false,
  notice = null,
}: {
  selectedProfile: string;
  onSelect: (id: string) => void;
  onContinue: () => void;
  onKnowledge: () => void;
  profiles?: Customer[];
  loading?: boolean;
  notice?: string | null;
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
          <p className="login-footnote">Choose your profile to continue.</p>
        </section>
        <section className="login-form-wrap">
          <div className="login-form">
            <div className="login-heading">
              <h2>Choose your profile</h2>
              <p>Select one of the sample accounts to explore support.</p>
            </div>
            <div className="profile-options" role="radiogroup" aria-label="Customer profile">
              {profiles.map((profile) => {
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
                    const currentIndex = profiles.findIndex((item) => item.id === profile.id);
                    const nextIndex = (currentIndex + (event.key === "ArrowLeft" || event.key === "ArrowUp" ? profiles.length - 1 : 1)) % profiles.length;
                    const nextProfile = profiles[nextIndex];
                    onSelect(nextProfile.id);
                    document.getElementById(`profile-${nextProfile.id}`)?.focus();
                  }}
                  role="radio"
                    type="button"
                  >
                    <span className={`profile-avatar ${taylor ? "avatar-lilac" : "avatar-peach"}`}>{profile.display_name.split(" ").map((part) => part[0]).join("")}</span>
                    <span className="profile-info"><strong>{profile.display_name}</strong><small>@{profile.handle}</small></span>
                    <span className="radio-mark">{selected && <span />}</span>
                  </button>
                );
              })}
            </div>
            {notice && <p role="alert">{notice}</p>}
            <Button className="login-submit" disabled={loading || !selectedProfile} onClick={onContinue}>{loading ? "Connecting…" : `Continue as ${profiles.find((profile) => profile.id === selectedProfile)?.display_name.split(" ")[0] ?? "profile"}`} <ArrowRight size={17} /></Button>
            <div className="login-safety"><Info size={15} /><span>Demo only: anyone can select a profile. No real authentication.</span></div>
            <button className="login-knowledge-link" type="button" disabled={loading} onClick={onKnowledge}><BookOpen size={17} /><span><strong>Manage the knowledge guide</strong><small>Open the separate demo administration area</small></span><ArrowRight size={16} /></button>
          </div>
          <div className="login-bottom">Customer support</div>
        </section>
      </div>
    </main>
  );
}

function BrandMark() {
  return (
    <a className="brand-mark" href="#home" aria-label="Support home">
      <span className="brand-symbol"><Headset size={19} strokeWidth={1.8} aria-hidden="true" /></span>
      <span>support<span className="brand-support">customer care</span></span>
    </a>
  );
}

export function Sidebar({
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
        <span><strong>{customer.display_name}</strong><small>Demo profile</small></span>
        <ChevronDown size={15} />
      </button>
      <nav aria-label="Main navigation" className="primary-nav">
        <button className={section === "chat" ? "nav-item active" : "nav-item"} onClick={() => onNavigate("chat")}><MessageCircle size={18} /><span>Conversations</span><span className="nav-count">{conversationCount}</span></button>
      </nav>
      <div className="sidebar-bottom">
        <button className="sidebar-help" onClick={onHelp}><span className="help-icon"><CircleHelp size={17} /></span><div><b>Ask for support</b><small>Start a new conversation</small></div><ArrowRight size={15} /></button>
        <div className="sidebar-bottom-row"><span>Customer support</span><span>Demo session</span></div>
      </div>
    </aside>
  );
}

export function ConversationRail({
  conversations,
  activeId,
  searchText,
  onSearch,
  onCreate,
  onSelect,
}: {
  conversations: Conversation[];
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
        {conversations.length === 0 && <div className="no-results">{searchText.trim() ? <><Search size={18} /><span>No conversations match that search.</span></> : <><MessageCircle size={18} /><span>Your first conversation will appear here.</span></>}</div>}
      </nav>
      <div className="conversation-rail-foot"><Clock3 size={15} /><span>Your conversations are saved.</span></div>
    </aside>
  );
}

export function ChatPanel({
  locked = false,
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
  locked?: boolean;
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

  const pendingApproval = messages.some((message) => message.approval?.status === "pending");
  const activeApproval = locked || pendingApproval;

  return (
    <section className="chat-panel" aria-label="Support conversation">
      <div className="chat-heading">
        <div><h2>{conversationTitle}</h2><p>Support conversation <span className="dot-separator">·</span> Started today</p></div>
        <div className="chat-heading-actions"><Badge tone="neutral">Local session</Badge></div>
      </div>

      {notice && <div className="inline-notice" role="status">{notice}<button onClick={onDismissNotice} aria-label="Dismiss notice"><X size={15} /></button></div>}
      <div className="message-scroll" ref={messageScrollRef}>
        <div className="conversation-date"><span />{todayLabel()}<span /></div>
        {messages.map((message) => {
          if (message.role === "user") return <UserMessage key={message.id} message={message} customer={customer} />;
          if (message.role === "action" && message.approval) {
            return <ApprovalCard key={message.id} messageId={message.id} approval={message.approval} onDecide={onDecide} disabled={isTyping} />;
          }
          if (message.role === "assistant") return <AssistantMessage key={message.id} message={message} onFeedback={onFeedback} />;
          return null;
        })}
        {isTyping && <div className="typing-row"><span className="assistant-avatar"><MessageCircle size={16} /></span><div className="typing-bubble"><span /><span /><span /></div><small>Support assistant is thinking</small></div>}
        {messages.length <= 1 && !isTyping && <div className="suggestions"><span>Try asking</span><button onClick={() => onComposerChange("What is my current subscription?")}>What is my current subscription?</button><button onClick={() => onComposerChange("How do I reset my password?")}>How do I reset my password?</button></div>}
      </div>
      <form className="composer-wrap" onSubmit={onSubmit}>
        {activeApproval && <div className="composer-locked"><KeyRound size={14} /> {pendingApproval ? "Resolve the pending confirmation above before sending another message." : "Select a conversation, or wait for the current turn to finish."}</div>}
        <div className={`composer ${activeApproval ? "composer-disabled" : ""}`}>
          <textarea
            id="support-composer"
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
        <div className="message-meta"><strong>Support assistant</strong><time>{timeLabel(message.created_at)}</time></div>
        <div className="assistant-copy"><MarkdownContent content={message.content ?? ""} /></div>
        {message.citations.length > 0 && <div className="citation-list" aria-label="Sources">
          <span className="citation-label"><BookOpen size={14} /> From the knowledge guide</span>
          {message.citations.map((citation) => <span className="citation-chip" key={citation.chunk_id}><FileText size={14} /><span><strong>{citation.article_title}</strong><small>{citation.section}</small></span></span>)}
        </div>}
        {message.run_id && <div className="message-actions"><span>{message.feedback ? "Thanks for your feedback" : "Was this helpful?"}</span>
          <button className={`feedback-button ${message.feedback?.rating === "positive" ? "feedback-selected" : ""}`} aria-label="This answer was helpful" aria-pressed={message.feedback?.rating === "positive"} onClick={() => { setDraft({ rating: "positive", comment: message.feedback?.comment ?? "" }); }}><ThumbsUp size={15} /></button>
          <button className={`feedback-button ${message.feedback?.rating === "negative" ? "feedback-selected" : ""}`} aria-label="This answer was not helpful" aria-pressed={message.feedback?.rating === "negative"} onClick={() => { setDraft({ rating: "negative", comment: message.feedback?.comment ?? "" }); }}><ThumbsDown size={15} /></button>
          <span className="action-spacer" />
          <button className="text-action" onClick={copyAnswer}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? "Copied" : "Copy"}</button>
        </div>}
        {draft && <form className="feedback-form" onSubmit={(event) => { event.preventDefault(); onFeedback(message.id, draft); setDraft(null); }}>
          <label htmlFor={`feedback-${message.id}`}>{draft.rating === "positive" ? "What worked well?" : "What could be clearer?"} <span>Optional</span></label>
          <Textarea id={`feedback-${message.id}`} value={draft.comment} onChange={(event) => setDraft({ ...draft, comment: event.target.value })} placeholder="Add a comment" maxLength={500} rows={3} />
          <Button size="sm" type="submit">Save feedback</Button>
          <Button size="sm" variant="ghost" type="button" onClick={() => setDraft(null)}>Cancel</Button>
        </form>}
      </article>
    </div>
  );
}

function ApprovalCard({
  messageId,
  approval,
  onDecide,
  disabled = false,
}: {
  messageId: string;
  approval: ApprovalCardType;
  onDecide: (messageId: string, approval: ApprovalCardType, approved: boolean) => void;
  disabled?: boolean;
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
          <div className="approval-actions"><Button disabled={disabled} onClick={() => onDecide(messageId, approval, true)}>Confirm</Button><Button disabled={disabled} variant="secondary" onClick={() => onDecide(messageId, approval, false)}>Cancel</Button></div>
        </>}
        {approval.status === "approved" && <p className="approval-outcome"><CheckCircle2 size={15} /> Approval recorded. The operation has not been executed.</p>}
        {approval.status === "rejected" && <p className="approval-outcome"><X size={15} /> No reset request was created.</p>}
        {approval.status === "executed" && approval.result && <div className="reset-result"><p><CheckCircle2 size={15} /> Reset request created.</p><span className="simulated-label">SIMULATED · NON-OPERATIONAL LINK</span><div className="link-copy"><code>{approval.result.reset_url}</code><Button variant="secondary" size="sm" onClick={copyLink}>{copied ? <Check size={14} /> : <Copy size={14} />}{copied ? "Copied" : "Copy link"}</Button></div><small>No email was sent and no password changed.</small></div>}
      </section>
    </div>
  );
}

export function KnowledgeWorkspace({
  busy = false,
  loading = false,
  loadFailed = false,
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
  busy?: boolean;
  loading?: boolean;
  loadFailed?: boolean;
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
          {loading ? <div className="no-results" role="status">Loading articles…</div> : loadFailed ? <div className="no-results">Articles could not be loaded.</div> : articles.length === 0 && <div className="no-results"><Search size={18} /><span>No articles found.</span></div>}
        </div>
        <div className="article-rail-note"><Info size={15} /> Demo knowledge administration. Articles are indexed when saved.</div>
      </aside>
      <section className="article-detail">
        {notice && <div className="inline-notice article-notice" role="status">{notice}</div>}
        {loading ? <div className="empty-articles" role="status">Loading articles…</div> : loadFailed ? <div className="empty-articles">Unable to load articles. Reopen the knowledge guide to retry.</div> : editor !== "closed" ? (
          <form className="article-editor" onSubmit={onSave}>
            <div className="article-editor-top"><div><Button variant="quiet" size="sm" type="button" onClick={onEditorClose}><ArrowLeft size={15} /> Back to article</Button><h2>{editor === "create" ? "Create an article" : "Edit article"}</h2><p>Write clear, useful guidance for customers.</p></div></div>
            <label className="field-label">Title<Input required maxLength={160} value={draft.title} onChange={(event) => onDraft({ ...draft, title: event.target.value })} placeholder="e.g. Understanding your subscription" /></label>
            <label className="field-label">Category<Input required maxLength={80} value={draft.category} onChange={(event) => onDraft({ ...draft, category: event.target.value })} placeholder="e.g. Billing" /></label>
            <label className="field-label">Article body <span>Markdown supported</span><Textarea required maxLength={20_000} rows={14} value={draft.body} onChange={(event) => onDraft({ ...draft, body: event.target.value })} placeholder="## Start with a heading\n\nWrite the article content here…" /></label>
            <div className="editor-actions"><Button type="submit" disabled={busy}>{busy ? "Saving…" : "Save article"}</Button><Button type="button" variant="secondary" onClick={onEditorClose}>Cancel</Button></div>
          </form>
        ) : selectedArticle ? (
          <article className="article-reading">
            <div className="article-detail-top"><div className="article-breadcrumb"><span>Knowledge guide</span><ArrowRight size={13} /><span>{selectedArticle.category}</span></div><div className="article-tools"><Button variant="secondary" size="sm" onClick={() => onEdit(selectedArticle)}><Pencil size={14} /> Edit</Button><Button variant="quiet" size="icon" aria-label="Delete this article" onClick={() => onRequestDelete(selectedArticle.id)}><Trash2 size={16} /></Button></div></div>
            <Badge tone="accent">{selectedArticle.category}</Badge>
            <h2>{selectedArticle.title}</h2>
            <div className="article-meta"><span>Updated {new Intl.DateTimeFormat("en", { month: "short", day: "numeric" }).format(new Date(selectedArticle.updated_at))}</span></div>
            <div className="article-body"><MarkdownContent content={selectedArticle.body} /></div>
            <div className="article-source-note"><BookOpen size={16} /><p><strong>Article in the support guide</strong><br />This article can be retrieved by the support assistant.</p></div>
            {deleteId === selectedArticle.id && <div className="delete-confirm" role="alert"><div><strong>Delete this article?</strong><span>The article and its indexed sections will be deleted.</span></div><div><Button variant="destructive" size="sm" disabled={busy} onClick={() => onDelete(selectedArticle.id)}>Remove article</Button><Button variant="secondary" size="sm" onClick={() => onRequestDelete(null)}>Keep it</Button></div></div>}
          </article>
        ) : (
          <div className="empty-articles"><span className="empty-icon"><BookOpen size={23} /></span><h2>{allArticles.length ? "Choose an article" : "Your guide is ready for its first article"}</h2><p>Select an article from the list or create a new one to get started.</p><Button onClick={onCreate}><Plus size={16} /> Create an article</Button></div>
        )}
      </section>
    </div>
  );
}
