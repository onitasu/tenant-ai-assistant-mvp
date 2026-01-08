"use client";

import * as React from "react";
import { Box, Button, TextField } from "@mui/material";

export default function ChatInput({
  value,
  onChange,
  onSend,
  disabled,
}: {
  value: string;
  onChange: (v: string) => void;
  onSend: () => void;
  disabled?: boolean;
}) {
  return (
    <Box sx={{ display: "flex", gap: 1 }}>
      <TextField
        fullWidth
        placeholder="ご質問を入力..."
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            if (disabled || !value.trim()) return;
            onSend();
          }
        }}
        multiline
        minRows={1}
        maxRows={4}
      />
      <Button
        variant="contained"
        onClick={onSend}
        disabled={disabled || !value.trim()}
        sx={{ minWidth: 90 }}
      >
        送信
      </Button>
    </Box>
  );
}
