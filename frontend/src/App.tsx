import { useEffect, useState, type FormEvent } from "react";
import { ArrowUpRight, CreditCard, Layers3, Menu, ShieldCheck } from "lucide-react";
import { ChatPanel, ConversationRail, KnowledgeWorkspace, LoginScreen, Sidebar } from "./components/SupportViews";
import { Button } from "./components/ui/button";
import { useSupport } from "./useSupport";
import type { Article } from "./api/types";

export default function App() {
  const support = useSupport();
  const [selectedProfile, setSelectedProfile] = useState("");
  const [section, setSection] = useState<"chat" | "account">("chat");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [composer, setComposer] = useState("");
  const [articleQuery, setArticleQuery] = useState("");
  const [articleId, setArticleId] = useState("");
  const [editor, setEditor] = useState<"closed" | "create" | "edit">("closed");
  const [draft, setDraft] = useState({ title: "", category: "", body: "" });
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [articleBusy, setArticleBusy] = useState(false);

  useEffect(() => { if (!selectedProfile && support.profiles[0]) setSelectedProfile(support.profiles[0].id); }, [support.profiles, selectedProfile]);
  useEffect(() => { if (support.articles.length && !support.articles.some((item) => item.id === articleId)) setArticleId(support.articles[0].id); }, [support.articles, articleId]);
  useEffect(() => {
    if (support.knowledgeAdmin) void support.refreshArticles();
    // Refresh on entering the separate knowledge area, not on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [support.knowledgeAdmin]);
  const current = support.conversations.find((item) => item.id === support.activeId);
  const selectedArticle = support.articles.find((item) => item.id === articleId) ?? null;
  const switchProfile = () => { setSection("chat"); setComposer(""); setMobileOpen(false); void support.logout(); };
  const create = () => { setSection("chat"); setMobileOpen(false); setComposer(""); void support.createConversation(); };
  const send = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const text = composer.trim();
    if (!text || support.loadingSession || support.busy || (support.activeId && (!support.history || support.history.active_run))) return;
    setComposer("");
    void support.chat(text).then((sent) => { if (sent === false) setComposer((current) => current || text); });
  };
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (articleBusy || !draft.title.trim() || !draft.category.trim() || !draft.body.trim()) return;
    setArticleBusy(true);
    const result = await support.saveArticle(draft, editor === "edit" ? articleId : undefined);
    if (result) { setArticleId(result.id); setEditor("closed"); }
    setArticleBusy(false);
  };
  const remove = async (id: string) => {
    if (articleBusy) return;
    setArticleBusy(true);
    if (await support.deleteArticle(id)) { setArticleId(""); setDeleteId(null); }
    setArticleBusy(false);
  };
  const edit = (article: Article) => { setArticleId(article.id); setDraft({ title: article.title, category: article.category, body: article.body }); setEditor("edit"); support.setArticleNotice(null); };

  if (support.knowledgeAdmin) return <main className="knowledge-admin-page">
    <header className="knowledge-admin-header"><div><h1>Knowledge guide</h1><p>Demo administration · Changes are shared across profiles</p></div><Button variant="secondary" onClick={() => { setEditor("closed"); void support.logout(); }}>Back to profile selection</Button></header>
    <KnowledgeWorkspace busy={articleBusy} loading={support.loadingArticles} loadFailed={support.articleLoadFailed} articles={support.articles.filter((a) => `${a.title} ${a.category}`.toLowerCase().includes(articleQuery.toLowerCase()))}
      allArticles={support.articles} selectedArticle={selectedArticle} query={articleQuery} notice={support.articleNotice}
      editor={editor} draft={draft} deleteId={deleteId} onQuery={setArticleQuery} onSelect={setArticleId}
      onCreate={() => { setDraft({ title: "", category: "", body: "" }); setEditor("create"); support.setArticleNotice(null); }}
      onEdit={edit} onDraft={setDraft} onEditorClose={() => setEditor("closed")} onSave={(event) => { void save(event); }}
      onRequestDelete={setDeleteId} onDelete={(id) => { void remove(id); }} />
  </main>;

  if (!support.customer) return <LoginScreen profiles={support.profiles} selectedProfile={selectedProfile}
    onSelect={setSelectedProfile} onContinue={() => { void support.login(selectedProfile); }}
    onKnowledge={() => { void support.enterKnowledge(); }} loading={support.loadingSession} notice={support.notice} />;

  const customer = support.customer;
  return <div className="app-frame">
    {mobileOpen && <button aria-label="Close navigation" className="mobile-scrim" onClick={() => setMobileOpen(false)} />}
    <Sidebar customer={customer} section={section} isOpen={mobileOpen} conversationCount={support.conversations.length}
      onNavigate={(next) => { setSection(next); setMobileOpen(false); }} onSwitch={switchProfile} onHelp={create} />
    <div className="app-main">
      <header className="topbar"><div className="topbar-title">
        <Button aria-label="Open navigation" className="mobile-menu" variant="quiet" size="icon" onClick={() => setMobileOpen(true)}><Menu size={19} /></Button>
        <div><h1>Your support space</h1><p>Demo support session</p></div>
      </div><div className="topbar-right"><button className="topbar-profile" onClick={switchProfile}>Switch profile · {customer.display_name}</button></div></header>
      <div className="workspace chat-workspace">
          <ConversationRail conversations={support.conversations.filter((item) => item.title.toLowerCase().includes(search.toLowerCase()))}
            activeId={support.activeId} searchText={search} onSearch={setSearch} onCreate={create}
            onSelect={(id) => { support.setActiveId(id); support.setNotice(null); setComposer(""); }} />
          <ChatPanel customer={customer} messages={support.history?.messages ?? []} isTyping={support.busy}
            locked={support.loadingSession || (!!support.activeId && (!support.history || !!support.history.active_run))} composer={composer} notice={support.notice}
            onComposerChange={setComposer} onSubmit={send} onDecide={support.decide} onFeedback={support.feedback}
            onDismissNotice={() => support.setNotice(null)} conversationTitle={current?.title ?? "Start a conversation"} />
          <aside className="account-context" aria-label="Account summary">
            <div className="context-heading"><h2>Your profile</h2><span className="context-demo-label">Demo</span></div>
            <div className="context-profile">
              <span className="context-avatar" aria-hidden="true">{customer.display_name.charAt(0).toUpperCase()}</span>
              <div><strong>{customer.display_name}</strong><small>@{customer.handle}</small></div>
            </div>
            <div className="context-questions">
              <h3>Ask about your account</h3>
              <p>Get the latest details from your demo profile.</p>
              <button type="button" disabled={support.loadingSession || support.busy || (!!support.activeId && (!support.history || !!support.history.active_run))} onClick={() => { setComposer("What is my current subscription?"); document.getElementById("support-composer")?.focus(); }}>
                <span className="context-question-icon"><Layers3 size={17} /></span><span><strong>Subscription</strong><small>Plan and billing</small></span><ArrowUpRight className="context-arrow" size={15} />
              </button>
              <button type="button" disabled={support.loadingSession || support.busy || (!!support.activeId && (!support.history || !!support.history.active_run))} onClick={() => { setComposer("What is the status of my latest payment?"); document.getElementById("support-composer")?.focus(); }}>
                <span className="context-question-icon"><CreditCard size={17} /></span><span><strong>Latest payment</strong><small>Status and details</small></span><ArrowUpRight className="context-arrow" size={15} />
              </button>
            </div>
            <p className="context-footnote"><ShieldCheck size={16} /><span>Demo account data is fictional. Each profile has its own conversation history.</span></p>
          </aside>
        </div>
    </div>
  </div>;
}
