"use client";

import * as React from "react";
import {
  AppBar,
  Box,
  Button,
  CircularProgress,
  Container,
  Divider,
  Link,
  Paper,
  Toolbar,
  Typography,
  Alert,
  List,
  ListItem,
  ListItemText,
} from "@mui/material";

import FAQList from "../components/FAQList";
import ChatInput from "../components/ChatInput";
import ChatMessageList, { ChatMessage } from "../components/ChatMessageList";
import ReferenceModal from "../components/ReferenceModal";
import { apiGet, apiPostJson } from "../lib/api";
import type { FAQ, FAQListResponse, ChatResponse, FAQResult, Reference } from "../lib/types";

function getOrCreateSessionId(): string {
  if (typeof window === "undefined") return "sess_local";
  const key = "tenant_ai_session_id";
  const existing = localStorage.getItem(key);
  if (existing) return existing;

  const sid = `sess_${crypto.randomUUID()}`;
  localStorage.setItem(key, sid);
  return sid;
}

export default function ChatPage() {
  const [faqs, setFaqs] = React.useState<FAQ[]>([]);
  const [messages, setMessages] = React.useState<ChatMessage[]>([]);
  const [input, setInput] = React.useState("");
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  const [relatedFaqs, setRelatedFaqs] = React.useState<FAQResult[]>([]);

  // Reference modal state
  const [refOpen, setRefOpen] = React.useState(false);
  const [modalRefs, setModalRefs] = React.useState<Reference[]>([]);
  const [modalIndex, setModalIndex] = React.useState(0);

  const sessionId = React.useMemo(() => getOrCreateSessionId(), []);

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

  const sendQuestion = async (question: string) => {
    if (!question.trim()) return;

    setError(null);
    setLoading(true);

    setMessages((prev) => [...prev, { role: "user", content: question }]);
    setInput("");

    try {
      const res = await apiPostJson<ChatResponse>("/chat", {
        query: question,
        session_id: sessionId,
      });

      setRelatedFaqs(res.faq_results);

      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.answer, references: res.references },
      ]);
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setLoading(false);
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

        <Paper sx={{ p: 2, mb: 2 }}>
          <FAQList
            faqs={faqs}
            onSelect={(q) => {
              // FAQタイトルをそのまま質問として送信
              sendQuestion(q);
            }}
          />
        </Paper>

        {relatedFaqs.length > 0 && (
          <Paper sx={{ p: 2, mb: 2 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>
              🔎 関連FAQ候補
            </Typography>
            <List dense>
              {relatedFaqs.map((f) => (
                <ListItem key={f.id} disableGutters>
                  <ListItemText
                    primary={`${f.title} (score: ${f.relevance_score.toFixed(2)})`}
                    secondary={f.answer}
                    secondaryTypographyProps={{ sx: { whiteSpace: "pre-wrap" } }}
                  />
                </ListItem>
              ))}
            </List>
          </Paper>
        )}

        <Paper sx={{ p: 2 }}>
          <Typography variant="h6" sx={{ mb: 1 }}>
            会話
          </Typography>

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
                disabled={loading}
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
