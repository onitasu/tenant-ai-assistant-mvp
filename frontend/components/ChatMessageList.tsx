"use client";

import * as React from "react";
import {
  Avatar,
  Box,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  List,
  ListItem,
  Typography,
} from "@mui/material";
import type { Reference } from "../lib/types";

export type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  references?: Reference[];
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
        return (
          <ListItem
            key={idx}
            sx={{
              display: "flex",
              flexDirection: "column",
              alignItems: isUser ? "flex-end" : "flex-start",
            }}
            disableGutters
          >
            <Box sx={{ display: "flex", gap: 1, width: "100%" }}>
              {!isUser && <Avatar sx={{ bgcolor: "primary.main" }}>🤖</Avatar>}
              <Box sx={{ flexGrow: 1 }} />
              {isUser && <Avatar sx={{ bgcolor: "grey.500" }}>👤</Avatar>}
            </Box>

            <Card sx={{ mt: 1, maxWidth: "900px", width: "100%" }}>
              <CardContent>
                <Typography
                  variant="body1"
                  sx={{ whiteSpace: "pre-wrap" }}
                >
                  {m.content}
                </Typography>

                {m.references && m.references.length > 0 && (
                  <Box sx={{ mt: 2 }}>
                    <Typography variant="subtitle2" sx={{ mb: 1 }}>
                      📄 参照ページ
                    </Typography>

                    <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
                      {m.references.map((ref, rIdx) => (
                        <Card key={ref.page_id} sx={{ width: 120 }}>
                          <CardActionArea
                            onClick={() => onClickReference(m.references!, rIdx)}
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
          </ListItem>
        );
      })}
    </List>
  );
}
