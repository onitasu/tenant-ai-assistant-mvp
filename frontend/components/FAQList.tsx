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
}: {
  faqs: FAQ[];
  onSelect: (question: string) => void;
}) {
  return (
    <Box>
      <Typography variant="h6" sx={{ mb: 1 }}>
        よくある質問
      </Typography>

      {faqs.map((faq) => (
        <Accordion key={faq.id} disableGutters>
          <AccordionSummary expandIcon={<ExpandMoreIcon />}>
            <Typography
              sx={{ cursor: "pointer" }}
              onClick={(e) => {
                e.stopPropagation();
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
  );
}
