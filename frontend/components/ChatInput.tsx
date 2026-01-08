"use client";

import * as React from "react";
import { Box, Button, TextField } from "@mui/material";
import StopIcon from "@mui/icons-material/Stop";

export default function ChatInput({
  value,
  onChange,
  onSend,
  onStop,
  loading,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  onStop?: () => void;
  loading?: boolean;
}) {
  return (
    <Box sx={{ display: "flex", gap: 1 }}>
      <TextField
        fullWidth
        placeholder="ご質問を入力... (Cmd/Ctrl+Enterで送信)"
        value={value}
        disabled={loading}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          // Cmd+Enter (Mac) or Ctrl+Enter (Windows/Linux) to send
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            if (loading || !value.trim()) return;
            onSend();
          }
        }}
        multiline
        minRows={1}
        maxRows={4}
      />
      {loading ? (
        <Button
          variant="contained"
          color="error"
          onClick={onStop}
          sx={{ minWidth: 90 }}
          startIcon={<StopIcon />}
        >
          停止
        </Button>
      ) : (
        <Button
          variant="contained"
          onClick={onSend}
          disabled={!value.trim()}
          sx={{ minWidth: 90 }}
        >
          送信
        </Button>
      )}
    </Box>
  );
}
