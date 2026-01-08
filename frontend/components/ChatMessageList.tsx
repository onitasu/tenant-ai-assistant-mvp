"use client";

import * as React from "react";
import {
  Box,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Link,
  List,
  ListItem,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import type { FAQResult, Reference } from "../lib/types";

export type ChatMessage = {
  id?: string;
  role: "user" | "assistant" | "faq";
  content?: string;
  references?: Reference[];
  faqItems?: FAQResult[];
  loading?: boolean;
  error?: string;
};

export default function ChatMessageList({
  messages,
  onClickReference,
}: {
  messages: ChatMessage[];
  onClickReference: (references: Reference[], index: number) => void;
}) {
  return (
    <List sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
      {messages.map((m, idx) => {
        const isUser = m.role === "user";
        const isFaq = m.role === "faq";
        return (
          <ListItem
            key={m.id || idx}
            sx={{
              display: "flex",
              flexDirection: "column",
              alignItems: isUser ? "flex-end" : "flex-start",
            }}
            disableGutters
          >
            {isFaq ? (
              <Card sx={{ mt: 1, maxWidth: "900px", width: "100%" }}>
                <CardContent>
                  <Typography variant="subtitle2" sx={{ mb: 1 }}>
                    関連FAQ候補
                  </Typography>
                  {m.loading ? (
                    <Typography variant="body2" color="text.secondary">
                      関連FAQを検索中...
                    </Typography>
                  ) : m.error ? (
                    <Typography variant="body2" color="error">
                      {m.error}
                    </Typography>
                  ) : m.faqItems && m.faqItems.length > 0 ? (
                    <Box sx={{ display: "flex", flexDirection: "column", gap: 1 }}>
                      {m.faqItems.map((item, itemIdx) => {
                        const hasRef =
                          item.page_id && item.page_number && item.image_url;
                        const reference: Reference | null = hasRef
                          ? {
                              page_id: item.page_id!,
                              page_number: item.page_number!,
                              image_url: item.image_url!,
                              relevance_score: item.relevance_score,
                              is_primary: false,
                            }
                          : null;
                        return (
                          <Accordion
                            key={item.id}
                            disableGutters
                            elevation={0}
                            sx={{
                              bgcolor: "transparent",
                              boxShadow: "none",
                              borderBottom:
                                itemIdx === m.faqItems!.length - 1
                                  ? "none"
                                  : "1px solid",
                              borderColor: "divider",
                              "&:before": { display: "none" },
                            }}
                          >
                            <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                              <Typography variant="subtitle2">
                                {item.title}
                              </Typography>
                            </AccordionSummary>
                            <AccordionDetails sx={{ pt: 0 }}>
                              <Typography
                                variant="body2"
                                sx={{ whiteSpace: "pre-wrap" }}
                              >
                                {item.answer}
                              </Typography>
                              {reference && (
                                <Link
                                  component="button"
                                  variant="body2"
                                  sx={{ mt: 0.5 }}
                                  onClick={() =>
                                    onClickReference([reference], 0)
                                  }
                                >
                                  参照: P.{item.page_number}
                                </Link>
                              )}
                            </AccordionDetails>
                          </Accordion>
                        );
                      })}
                    </Box>
                  ) : (
                    <Typography variant="body2" color="text.secondary">
                      該当するFAQはありません
                    </Typography>
                  )}
                </CardContent>
              </Card>
            ) : (
              <Card sx={{ mt: 1, maxWidth: "900px", width: "100%" }}>
                <CardContent>
                  {m.content && (
                    <Typography variant="body1" sx={{ whiteSpace: "pre-wrap" }}>
                      {m.content}
                    </Typography>
                  )}

                  {m.references && m.references.length > 0 && (
                    <Box sx={{ mt: 2 }}>
                      <Typography variant="subtitle2" sx={{ mb: 1 }}>
                        参照ページ
                      </Typography>

                      <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
                        {m.references.map((ref, rIdx) => (
                          <Card key={ref.page_id} sx={{ width: 120 }}>
                            <CardActionArea
                              onClick={() =>
                                onClickReference(m.references!, rIdx)
                              }
                            >
                              <CardContent sx={{ textAlign: "center" }}>
                                <Typography variant="h6">
                                  P.{ref.page_number}
                                </Typography>
                                <Chip
                                  size="small"
                                  label={ref.is_primary ? "★最重視" : "参照"}
                                  sx={{ mt: 1 }}
                                />
                              </CardContent>
                            </CardActionArea>
                          </Card>
                        ))}
                      </Box>
                    </Box>
                  )}
                </CardContent>
              </Card>
            )}
          </ListItem>
        );
      })}
    </List>
  );
}
