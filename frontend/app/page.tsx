"use client";

import * as React from "react";
import {
  AppBar,
  Box,
  Button,
  CircularProgress,
  Container,
  Divider,
  IconButton,
  Link,
  Paper,
  Toolbar,
  Tooltip,
  Typography,
  Alert,
} from "@mui/material";
import RefreshIcon from "@mui/icons-material/Refresh";

import FAQList from "../components/FAQList";
import ChatInput from "../components/ChatInput";
import ChatMessageList, { ChatMessage } from "../components/ChatMessageList";
import ReferenceModal from "../components/ReferenceModal";
import { apiGet, apiPostJson } from "../lib/api";
import type { FAQ, FAQListResponse, ChatResponse, PrepareResponse, Reference, ConversationResponse } from "../lib/types";

const SESSION_KEY = "tenant_ai_session_id";

function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return "sess_local";
  const existing = localStorage.getItem(SESSION_KEY);
  if (existing) return existing;

  const sid = `sess_${crypto.randomUUID()}`;
  localStorage.setItem(SESSION_KEY, sid);
  return sid;
}

function createNewSessionId(): string {
  const sid = `sess_${crypto.randomUUID()}`;
  if (typeof window !== "undefined") {
    localStorage.setItem(SESSION_KEY, sid);
  }
  return sid;
}

export default function ChatPage() {
  const [faqs, setFaqs] = React.useState<FAQ[]>([]);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const isSendingRef = React.useRef(false);

  // Reference modal state
  const [refOpen, setRefOpen] = React.useState(false);
  const [modalRefs, setModalRefs] = React.useState<Reference[]>([]);
  const [modalIndex, setModalIndex] = React.useState(0);

  const [sessionId, setSessionId] = React.useState(() => getOrCreateSessionId());
  const abortControllerRef = React.useRef<AbortController | null>(null);

  const clearChat = () => {
    setMessages([]);
    setInput("");
    setError(null);
    setSessionId(createNewSessionId());
  };

  React.useEffect(() => {
    (async () => {
      try {
        const data = await apiGet<FAQListResponse>("/faqs");
        setFaqs(data.items);
      } catch (e: any) {
        setError(e?.message || String(e));
      }
    })();
  }, []);

  // Load conversation history when session changes
  React.useEffect(() => {
    (async () => {
      try {
        const data = await apiGet<ConversationResponse>(`/chat/conversations/${sessionId}`);
        const restored: ChatMessage[] = data.messages.map((m) => ({
          id: m.id,
          role: m.role as "user" | "assistant",
          content: m.content,
          references: m.references,
        }));
        setMessages(restored);
      } catch {
        // 404 = no conversation yet, ignore
        setMessages([]);
      }
    })();
  }, [sessionId]);

  const sendQuestion = async (question: string) => {
    if (!question.trim()) return;
    if (loading || isSendingRef.current) return;
    isSendingRef.current = true;

    // Create new AbortController for this request
    abortControllerRef.current = new AbortController();
    const signal = abortControllerRef.current.signal;

    setError(null);
    setLoading(true);

    const userMessageId = `user_${crypto.randomUUID()}`;
    const faqMessageId = `faq_${crypto.randomUUID()}`;

    setMessages((prev) => [
      ...prev,
      { id: userMessageId, role: "user", content: question },
      { id: faqMessageId, role: "faq", loading: true, faqItems: [] },
    ]);
    setInput("");

    try {
      // Step 1: Call prepare to get query + FAQs (fast)
      const prepareRes = await apiPostJson<PrepareResponse>("/chat/prepare", {
        query: question,
        session_id: sessionId,
      }, signal);

      // Update FAQ message immediately with related FAQs
      setMessages((prev) =>
        prev.map((m) =>
          m.id === faqMessageId
            ? { ...m, loading: false, faqItems: prepareRes.related_faqs, error: undefined }
            : m
        )
      );

      // Step 2: Call chat with prepared_query to get answer
      const chatRes = await apiPostJson<ChatResponse>("/chat", {
        query: question,
        session_id: sessionId,
        prepared_query: prepareRes.prepared_query,
      }, signal);

      // Add assistant message
      setMessages((prev) => [
        ...prev,
        {
          id: `assistant_${crypto.randomUUID()}`,
          role: "assistant",
          content: chatRes.answer,
          references: chatRes.references,
        },
      ]);
    } catch (e: any) {
      // Check if this was an abort
      if (e.name === "AbortError") {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === faqMessageId
              ? { ...m, loading: false, faqItems: [], error: "キャンセルされました" }
              : m
          )
        );
      } else {
        setError(e?.message || String(e));
        // Mark FAQ message as failed too
        setMessages((prev) =>
          prev.map((m) =>
            m.id === faqMessageId
              ? { ...m, loading: false, faqItems: [], error: "エラーが発生しました" }
              : m
          )
        );
      }
    } finally {
      setLoading(false);
      isSendingRef.current = false;
      abortControllerRef.current = null;
    }
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  const onClickReference = (refs: Reference[], index: number) => {
    setModalRefs(refs);
    setModalIndex(index);
    setRefOpen(true);
  };

  return (
    <>
      <AppBar position="sticky">
        <Toolbar>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            🏢 テナントAIアシスタント
          </Typography>
          <Link href="/admin" color="inherit" underline="hover">
            管理画面
          </Link>
        </Toolbar>
      </AppBar>

      <Container maxWidth="lg" sx={{ py: 3 }}>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        <Box sx={{ mb: 2 }}>
          <FAQList
            faqs={faqs}
            disabled={loading}
            onSelect={(q) => {
              // FAQタイトルをそのまま質問として送信
              sendQuestion(q);
            }}
          />
        </Box>

        <Paper sx={{ p: 2 }}>
          <Box sx={{ display: "flex", alignItems: "center", mb: 1 }}>
            <Typography variant="h6" sx={{ flexGrow: 1 }}>
              会話
            </Typography>
            <Tooltip title="新しい会話を開始">
              <IconButton
                onClick={clearChat}
                disabled={loading || messages.length === 0}
                size="small"
              >
                <RefreshIcon />
              </IconButton>
            </Tooltip>
          </Box>

          <Divider sx={{ mb: 2 }} />

          <Box sx={{ minHeight: 320, maxHeight: 520, overflow: "auto", pr: 1 }}>
            <ChatMessageList messages={messages} onClickReference={onClickReference} />
          </Box>

          <Divider sx={{ my: 2 }} />

          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <Box sx={{ flexGrow: 1 }}>
              <ChatInput
                value={input}
                onChange={setInput}
                onSend={() => sendQuestion(input)}
                onStop={handleStop}
                loading={loading}
              />
            </Box>
            {loading && <CircularProgress size={28} />}
          </Box>
        </Paper>
      </Container>

      <ReferenceModal
        open={refOpen}
        onClose={() => setRefOpen(false)}
        references={modalRefs}
        currentIndex={modalIndex}
        onChangeIndex={setModalIndex}
      />
    </>
  );
}
