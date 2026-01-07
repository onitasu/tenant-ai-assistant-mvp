"use client";

import * as React from "react";
import {
  AppBar,
  Toolbar,
  Typography,
  Link,
  Container,
  Paper,
  Box,
  Button,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Table,
  TableHead,
  TableRow,
  TableCell,
  TableBody,
  IconButton,
  Alert,
  MenuItem,
  CircularProgress,
} from "@mui/material";
import DeleteIcon from "@mui/icons-material/Delete";
import EditIcon from "@mui/icons-material/Edit";
import UploadIcon from "@mui/icons-material/Upload";

import { apiDelete, apiGet, apiPostForm, apiPostJson, apiPutJson } from "../../lib/api";
import type {
  Document,
  DocumentListResponse,
  FAQ,
  FAQListResponse,
  Page,
  PageListResponse,
} from "../../lib/types";

export default function AdminPage() {
  const [docs, setDocs] = React.useState<Document[]>([]);
  const [faqs, setFaqs] = React.useState<FAQ[]>([]);
  const [pages, setPages] = React.useState<Page[]>([]);

  const [error, setError] = React.useState<string | null>(null);

  const [uploadOpen, setUploadOpen] = React.useState(false);
  const [uploadTitle, setUploadTitle] = React.useState("");
  const [uploadFile, setUploadFile] = React.useState<File | null>(null);
  const [uploading, setUploading] = React.useState(false);

  const [faqOpen, setFaqOpen] = React.useState(false);
  const [faqEditing, setFaqEditing] = React.useState<FAQ | null>(null);
  const [faqTitle, setFaqTitle] = React.useState("");
  const [faqSearchQuery, setFaqSearchQuery] = React.useState("");
  const [faqAnswer, setFaqAnswer] = React.useState("");
  const [faqPageId, setFaqPageId] = React.useState<string>("");
  const [faqOrder, setFaqOrder] = React.useState<number>(0);
  const [faqSaving, setFaqSaving] = React.useState(false);

  const refresh = async () => {
    setError(null);
    try {
      const d = await apiGet<DocumentListResponse>("/documents");
      setDocs(d.items);

      const f = await apiGet<FAQListResponse>("/faqs");
      setFaqs(f.items);
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  };

  React.useEffect(() => {
    refresh();
  }, []);

  // Load all pages (for FAQ page selector)
  React.useEffect(() => {
    (async () => {
      try {
        const all: Page[] = [];
        for (const doc of docs) {
          const pl = await apiGet<PageListResponse>(`/documents/${doc.id}/pages`);
          all.push(...pl.items);
        }
        setPages(all);
      } catch {
        // ignore
      }
    })();
  }, [docs]);

  const onUpload = async () => {
    if (!uploadFile) return;
    setUploading(true);
    setError(null);

    try {
      const fd = new FormData();
      fd.append("file", uploadFile);
      fd.append("title", uploadTitle);

      await apiPostForm("/documents/upload", fd);

      setUploadOpen(false);
      setUploadTitle("");
      setUploadFile(null);

      await refresh();
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setUploading(false);
    }
  };

  const onDeleteDoc = async (id: string) => {
    if (!confirm("このドキュメントを削除しますか？")) return;
    setError(null);
    try {
      await apiDelete(`/documents/${id}`);
      await refresh();
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  };

  const openFaqDialog = (faq?: FAQ) => {
    setFaqEditing(faq || null);
    setFaqTitle(faq?.title || "");
    setFaqSearchQuery(faq?.search_query || "");
    setFaqAnswer(faq?.answer || "");
    setFaqPageId(faq?.page_id || "");
    setFaqOrder(faq?.display_order || 0);
    setFaqOpen(true);
  };

  const saveFaq = async () => {
    setFaqSaving(true);
    setError(null);

    try {
      const payload: any = {
        title: faqTitle,
        search_query: faqSearchQuery,
        answer: faqAnswer,
        page_id: faqPageId || null,
        display_order: faqOrder,
      };

      if (faqEditing) {
        await apiPutJson(`/faqs/${faqEditing.id}`, payload);
      } else {
        await apiPostJson(`/faqs`, payload);
      }

      setFaqOpen(false);
      setFaqEditing(null);

      await refresh();
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setFaqSaving(false);
    }
  };

  const deleteFaq = async (id: string) => {
    if (!confirm("このFAQを削除しますか？")) return;
    setError(null);
    try {
      await apiDelete(`/faqs/${id}`);
      await refresh();
    } catch (e: any) {
      setError(e?.message || String(e));
    }
  };

  const pageLabel = (p: Page): string => {
    const doc = docs.find((d) => d.id === p.document_id);
    const docTitle = doc?.title || p.document_id;
    return `${docTitle} - P.${p.page_number}`;
  };

  return (
    <>
      <AppBar position="sticky">
        <Toolbar>
          <Typography variant="h6" sx={{ flexGrow: 1 }}>
            🏢 管理画面
          </Typography>
          <Link href="/" color="inherit" underline="hover">
            チャット画面
          </Link>
        </Toolbar>
      </AppBar>

      <Container maxWidth="lg" sx={{ py: 3 }}>
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {/* Documents */}
        <Paper sx={{ p: 2, mb: 3 }}>
          <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
            <Typography variant="h6" sx={{ flexGrow: 1 }}>
              ドキュメント管理
            </Typography>
            <Button
              variant="contained"
              startIcon={<UploadIcon />}
              onClick={() => setUploadOpen(true)}
            >
              アップロード
            </Button>
          </Box>

          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>タイトル</TableCell>
                <TableCell>ページ数</TableCell>
                <TableCell>ステータス</TableCell>
                <TableCell align="right">操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {docs.map((d) => (
                <TableRow key={d.id}>
                  <TableCell>{d.title}</TableCell>
                  <TableCell>{d.total_pages}</TableCell>
                  <TableCell>{d.status}</TableCell>
                  <TableCell align="right">
                    <IconButton onClick={() => onDeleteDoc(d.id)} aria-label="delete">
                      <DeleteIcon />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
              {docs.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4}>ドキュメントがありません</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </Paper>

        {/* FAQs */}
        <Paper sx={{ p: 2 }}>
          <Box sx={{ display: "flex", alignItems: "center", mb: 2 }}>
            <Typography variant="h6" sx={{ flexGrow: 1 }}>
              FAQ管理
            </Typography>
            <Button variant="contained" onClick={() => openFaqDialog()}>
              + 追加
            </Button>
          </Box>

          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>タイトル</TableCell>
                <TableCell>表示順</TableCell>
                <TableCell>参照ページ</TableCell>
                <TableCell align="right">操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {faqs.map((f) => (
                <TableRow key={f.id}>
                  <TableCell>{f.title}</TableCell>
                  <TableCell>{f.display_order}</TableCell>
                  <TableCell>{f.page_id ? f.page_id : "-"}</TableCell>
                  <TableCell align="right">
                    <IconButton onClick={() => openFaqDialog(f)} aria-label="edit">
                      <EditIcon />
                    </IconButton>
                    <IconButton onClick={() => deleteFaq(f.id)} aria-label="delete">
                      <DeleteIcon />
                    </IconButton>
                  </TableCell>
                </TableRow>
              ))}
              {faqs.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4}>FAQがありません</TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </Paper>
      </Container>

      {/* Upload Dialog */}
      <Dialog open={uploadOpen} onClose={() => setUploadOpen(false)} fullWidth>
        <DialogTitle>ドキュメントアップロード</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
          <TextField
            label="タイトル（任意）"
            value={uploadTitle}
            onChange={(e) => setUploadTitle(e.target.value)}
            placeholder="例: 入居者マニュアル"
          />
          <Button variant="outlined" component="label">
            ファイルを選択（PDF / PPTX）
            <input
              type="file"
              hidden
              accept=".pdf,.pptx,.ppt"
              onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
            />
          </Button>
          <Typography variant="body2" color="text.secondary">
            {uploadFile ? `選択中: ${uploadFile.name}` : "未選択"}
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUploadOpen(false)}>キャンセル</Button>
          <Button variant="contained" onClick={onUpload} disabled={!uploadFile || uploading}>
            {uploading ? <CircularProgress size={18} /> : "アップロード"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* FAQ Dialog */}
      <Dialog open={faqOpen} onClose={() => setFaqOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>{faqEditing ? "FAQ編集" : "FAQ追加"}</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
          <TextField
            label="タイトル"
            value={faqTitle}
            onChange={(e) => setFaqTitle(e.target.value)}
            fullWidth
          />
          <TextField
            label="検索クエリ（FAISS用）"
            value={faqSearchQuery}
            onChange={(e) => setFaqSearchQuery(e.target.value)}
            fullWidth
          />
          <TextField
            label="回答"
            value={faqAnswer}
            onChange={(e) => setFaqAnswer(e.target.value)}
            fullWidth
            multiline
            minRows={4}
          />

          <TextField
            select
            label="参照ページ（任意）"
            value={faqPageId}
            onChange={(e) => setFaqPageId(e.target.value)}
            fullWidth
            helperText="参照ページを設定すると、FAQ検索結果にもページ情報が付きます。"
          >
            <MenuItem value="">なし</MenuItem>
            {pages.map((p) => (
              <MenuItem key={p.id} value={p.id}>
                {pageLabel(p)}
              </MenuItem>
            ))}
          </TextField>

          <TextField
            type="number"
            label="表示順"
            value={faqOrder}
            onChange={(e) => setFaqOrder(parseInt(e.target.value || "0", 10))}
            fullWidth
          />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setFaqOpen(false)}>キャンセル</Button>
          <Button
            variant="contained"
            onClick={saveFaq}
            disabled={faqSaving || !faqTitle.trim() || !faqSearchQuery.trim() || !faqAnswer.trim()}
          >
            {faqSaving ? <CircularProgress size={18} /> : "保存"}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
