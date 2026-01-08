"use client";

import * as React from "react";
import {
  Dialog,
  DialogTitle,
  DialogContent,
  IconButton,
  Box,
  Typography,
  Button,
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import type { Reference } from "../lib/types";

export default function ReferenceModal({
  open,
  onClose,
  references,
  currentIndex,
  onChangeIndex,
}: {
  open: boolean;
  onClose: () => void;
  references: Reference[];
  currentIndex: number;
  onChangeIndex: (next: number) => void;
}) {
  const ref = references[currentIndex];

  if (!ref) return null;

  const canPrev = currentIndex > 0;
  const canNext = currentIndex < references.length - 1;

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle sx={{ display: "flex", alignItems: "center" }}>
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="h6">
            参照ページ: P.{ref.page_number}{" "}
            {ref.is_primary ? "★最重視" : ""}
          </Typography>
        </Box>
        <IconButton onClick={onClose} aria-label="close">
          <CloseIcon />
        </IconButton>
      </DialogTitle>

      <DialogContent>
        <Box sx={{ display: "flex", justifyContent: "center", mb: 2 }}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img
            src={ref.image_url}
            alt={`P.${ref.page_number}`}
            style={{ maxWidth: "100%", maxHeight: "70vh", objectFit: "contain", borderRadius: 8 }}
          />
        </Box>

        <Box sx={{ display: "flex", justifyContent: "space-between" }}>
          <Button
            variant="outlined"
            disabled={!canPrev}
            onClick={() => onChangeIndex(currentIndex - 1)}
          >
            ◀ 前の参照
          </Button>
          <Button
            variant="outlined"
            disabled={!canNext}
            onClick={() => onChangeIndex(currentIndex + 1)}
          >
            次の参照 ▶
          </Button>
        </Box>
      </DialogContent>
    </Dialog>
  );
}
