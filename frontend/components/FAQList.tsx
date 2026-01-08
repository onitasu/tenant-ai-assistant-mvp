"use client";

import * as React from "react";
import {
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Typography,
  Box,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import type { FAQ } from "../lib/types";

export default function FAQList({
  faqs,
  onSelect,
  disabled = false,
}: {
  faqs: FAQ[];
  onSelect: (question: string) => void;
  disabled?: boolean;
}) {
  return (
    <Accordion disableGutters>
      <AccordionSummary
        expandIcon={<ExpandMoreIcon />}
        sx={disabled ? { opacity: 0.6, pointerEvents: "none" } : undefined}
      >
        <Typography variant="h6">よくある質問</Typography>
      </AccordionSummary>
      <AccordionDetails>
        <Box>
          {faqs.map((faq) => (
            <Accordion key={faq.id} disableGutters>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography
                  sx={{ cursor: disabled ? "not-allowed" : "pointer", opacity: disabled ? 0.6 : 1 }}
                  onClick={(e) => {
                    e.stopPropagation();
                    if (disabled) return;
                    onSelect(faq.title);
                  }}
                >
                  📋 {faq.title}
                </Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                  {faq.answer}
                </Typography>
              </AccordionDetails>
            </Accordion>
          ))}
        </Box>
      </AccordionDetails>
    </Accordion>
  );
}
