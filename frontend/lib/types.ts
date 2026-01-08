export type FAQ = {
  id: string;
  title: string;
  search_query: string;
  answer: string;
  page_id?: string | null;
  display_order: number;
  created_at?: string | null;
};

export type FAQListResponse = { items: FAQ[] };

export type Document = {
  id: string;
  title: string;
  status: string;
  total_pages: number;
  created_at?: string | null;
  updated_at?: string | null;
};

export type DocumentListResponse = { items: Document[] };

export type Page = {
  id: string;
  document_id: string;
  page_number: number;
  title?: string | null;
  search_query?: string | null;
  page_text?: string | null;
  img_description?: string | null;
  image_url?: string | null;
};

export type PageListResponse = { items: Page[] };

export type Reference = {
  page_id: string;
  page_number: number;
  image_url: string;
  relevance_score: number;
  is_primary: boolean;
};

export type FAQResult = {
  id: string;
  title: string;
  search_query: string;
  answer: string;
  page_id?: string | null;
  page_number?: number | null;
  image_url?: string | null;
  relevance_score: number;
};

export type PrepareResponse = {
  prepared_query: string;
  related_faqs: FAQResult[];
};

export type ChatResponse = {
  answer: string;
  references: Reference[];
};

export type MessageResponse = {
  id: string;
  role: string;
  content: string;
  created_at?: string | null;
  references: Reference[];
};

export type ConversationResponse = {
  session_id: string;
  messages: MessageResponse[];
};
