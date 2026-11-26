import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiClientError } from "./api/client";
import type { ApprovalCard, Article, ArticleInput, Conversation, Customer, HistoryResponse, Message, TurnResponse } from "./api/types";

export type FeedbackDraft = { rating: "positive" | "negative"; comment: string };

function describe(error: unknown): string {
  return error instanceof ApiClientError ? error.message : "Unable to reach the support service. Please try again.";
}

// Keep already-rendered messages in server order and replace returned cards by stable ID.
function upsertMessages(existing: Message[], incoming: Message[]): Message[] {
  const byId = new Map(existing.map((message) => [message.id, message]));
  incoming.forEach((message) => byId.set(message.id, message));
  return [...byId.values()].sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id.localeCompare(b.id));
}

export function useSupport() {
  const [customer, setCustomer] = useState<Customer | null>(null);
  const [profiles, setProfiles] = useState<Customer[]>([]);
  const [loadingSession, setLoadingSession] = useState(true);
  const [notice, setNotice] = useState<string | null>(null);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState("");
  const [histories, setHistories] = useState<Record<string, HistoryResponse>>({});
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [articles, setArticles] = useState<Article[]>([]);
  const [loadingArticles, setLoadingArticles] = useState(false);
  const [articleNotice, setArticleNotice] = useState<string | null>(null);
  const [articleLoadFailed, setArticleLoadFailed] = useState(false);
  const epoch = useRef(0);
  const busyIds = useRef(new Set<string>());
  const historyVersions = useRef<Record<string, number>>({});
  const creating = useRef<number | null>(null);

  const clearAccount = useCallback(() => {
    ++epoch.current;
    busyIds.current.clear();
    historyVersions.current = {};
    creating.current = null;
    setCustomer(null); setConversations([]); setActiveId(""); setHistories({}); setBusy({}); setArticles([]); setLoadingArticles(false); setArticleNotice(null); setArticleLoadFailed(false);
  }, []);
  const handleError = useCallback((error: unknown) => {
    if (error instanceof ApiClientError && error.status === 401) {
      clearAccount();
      setLoadingSession(false);
      setNotice("Your session has ended. Choose a profile to continue.");
    } else setNotice(describe(error));
  }, [clearAccount]);

  const loadConversations = useCallback(async (generation: number) => {
    const response = await api.conversations();
    if (generation !== epoch.current) return;
    setConversations(response.items);
    setActiveId((current) => response.items.some((item) => item.id === current) ? current : response.items[0]?.id ?? "");
  }, []);
  const loadHistory = useCallback(async (id: string, generation = epoch.current) => {
    const version = (historyVersions.current[id] ?? 0) + 1;
    historyVersions.current[id] = version;
    const history = await api.history(id);
    if (generation === epoch.current && historyVersions.current[id] === version) setHistories((items) => ({ ...items, [id]: history }));
    return history;
  }, []);
  const loadArticles = useCallback(async (generation = epoch.current) => {
    const summaries = await api.articles();
    const details = await Promise.all(summaries.items.map((item) => api.article(item.id)));
    if (generation === epoch.current) setArticles(details);
  }, []);

  useEffect(() => {
    const generation = epoch.current;
    void Promise.allSettled([api.customers(), api.me()]).then(async ([list, session]) => {
      if (generation !== epoch.current) return;
      if (list.status === "fulfilled") setProfiles(list.value.items);
      else setNotice(describe(list.reason));
      if (session.status === "fulfilled") {
        setCustomer(session.value);
        try { await loadConversations(generation); } catch (error) { if (generation === epoch.current) handleError(error); }
      } else if (!(session.reason instanceof ApiClientError && session.reason.status === 401)) {
        setNotice(describe(session.reason));
      }
      if (generation === epoch.current) setLoadingSession(false);
    });
  }, [handleError, loadConversations]);

  useEffect(() => {
    if (!customer || !activeId) return;
    const generation = epoch.current;
    void loadHistory(activeId, generation).catch((error) => { if (generation === epoch.current) handleError(error); });
  }, [customer, activeId, loadHistory, handleError]);

  const login = async (id: string) => {
    const generation = ++epoch.current;
    setNotice(null); setLoadingSession(true);
    try {
      const profile = await api.login(id);
      if (generation !== epoch.current) return;
      setCustomer(profile);
      await loadConversations(generation);
    } catch (error) { if (generation === epoch.current) handleError(error); }
    finally { if (generation === epoch.current) setLoadingSession(false); }
  };
  const logout = async () => {
    clearAccount(); setNotice(null); setLoadingSession(true);
    const generation = epoch.current;
    try { await api.logout(); } catch (error) { if (generation === epoch.current) setNotice(describe(error)); }
    finally { if (generation === epoch.current) setLoadingSession(false); }
  };
  const createConversation = async () => {
    const generation = epoch.current;
    if (creating.current === generation) return;
    creating.current = generation;
    try {
      const created = await api.createConversation();
      if (generation !== epoch.current) return;
      setConversations((items) => [created, ...items]); setActiveId(created.id); setNotice(null);
    } catch (error) { if (generation === epoch.current) handleError(error); }
    finally { if (creating.current === generation) creating.current = null; }
  };
  const applyTurn = (turn: TurnResponse) => {
    setHistories((items) => {
      const previous = items[turn.conversation_id];
      if (!previous) return items;
      return { ...items, [turn.conversation_id]: { ...previous,
        messages: upsertMessages(previous.messages, turn.messages),
        active_run: turn.status === "waiting_for_approval" ? { id: turn.run_id, conversation_id: turn.conversation_id, status: turn.status } : null,
        pending_approval: turn.pending_approval,
      } };
    });
    if (turn.error) setNotice(turn.error.message);
  };
  const runMutation = async (id: string, operation: () => Promise<TurnResponse>) => {
    if (!id || busyIds.current.has(id)) return;
    const generation = epoch.current;
    busyIds.current.add(id);
    historyVersions.current[id] = (historyVersions.current[id] ?? 0) + 1;
    setBusy((items) => ({ ...items, [id]: true })); setNotice(null);
    try {
      const turn = await operation();
      if (generation !== epoch.current) return;
      applyTurn(turn);
      await loadHistory(id, generation);
      await loadConversations(generation);
    } catch (error) {
      if (generation !== epoch.current) return;
      handleError(error);
      // Never resend an uncertain mutation; recover the authoritative server state.
      try { await loadHistory(id, generation); } catch { /* preserve the original error */ }
    } finally {
      if (generation === epoch.current) { busyIds.current.delete(id); setBusy((items) => ({ ...items, [id]: false })); }
    }
  };
  const chat = (message: string) => runMutation(activeId, () => api.chat(activeId, message));
  const decide = (_messageId: string, approval: ApprovalCard, approved: boolean) =>
    runMutation(activeId, () => api.decideApproval(approval.action_id, approved));
  const feedback = async (messageId: string, draft: FeedbackDraft) => {
    const generation = epoch.current, id = activeId;
    try {
      await api.feedback(messageId, draft.rating, draft.comment.trim() || null);
      if (generation === epoch.current) await loadHistory(id, generation);
    } catch (error) { if (generation === epoch.current) handleError(error); }
  };
  const refreshArticles = async () => {
    const generation = epoch.current;
    setLoadingArticles(true); setArticleLoadFailed(false);
    try { await loadArticles(generation); if (generation === epoch.current) setArticleNotice(null); }
    catch (error) { if (generation === epoch.current) { if (error instanceof ApiClientError && error.status === 401) handleError(error); else { setArticleLoadFailed(true); setArticleNotice(describe(error)); } } }
    finally { if (generation === epoch.current) setLoadingArticles(false); }
  };
  const saveArticle = async (draft: ArticleInput, id?: string) => {
    const generation = epoch.current;
    try {
      const saved = id ? await api.updateArticle(id, draft) : await api.createArticle(draft);
      await loadArticles(generation);
      if (generation === epoch.current) setArticleNotice("Article saved and indexed.");
      return generation === epoch.current ? saved : null;
    } catch (error) { if (generation === epoch.current) { if (error instanceof ApiClientError && error.status === 401) handleError(error); else setArticleNotice(describe(error)); } return null; }
  };
  const deleteArticle = async (id: string) => {
    const generation = epoch.current;
    try { await api.deleteArticle(id); await loadArticles(generation); if (generation === epoch.current) setArticleNotice("Article deleted."); return true; }
    catch (error) { if (generation === epoch.current) { if (error instanceof ApiClientError && error.status === 401) handleError(error); else setArticleNotice(describe(error)); } return false; }
  };

  return { customer, profiles, loadingSession, notice, setNotice, conversations, activeId, setActiveId,
    history: histories[activeId], busy: !!busy[activeId], login, logout, createConversation, chat, decide, feedback,
    articles, loadingArticles, articleLoadFailed, articleNotice, setArticleNotice, refreshArticles, saveArticle, deleteArticle };
}
