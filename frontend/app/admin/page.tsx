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
  LinearProgress,
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
  const [pagesLoading, setPagesLoading] = React.useState(false);
  const [selectedDocId, setSelectedDocId] = React.useState("");
  const [pageDetailOpen, setPageDetailOpen] = React.useState(false);
  const [pageDetail, setPageDetail] = React.useState<Page | null>(null);

  const [error, setError] = React.useState<string | null>(null);

  const [uploadOpen, setUploadOpen] = React.useState(false);
  const [uploadTitle, setUploadTitle] = React.useState("");
  const [uploadFile, setUploadFile] = React.useState<File | null>(null);
  const [uploading, setUploading] = React.useState(false);
  const [uploadProgress, setUploadProgress] = React.useState<{
    message: string;
    currentPage: number;
    totalPages: number;
  } | null>(null);

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

  React.useEffect(() => {
    if (docs.length === 0) {
      setSelectedDocId("");
      return;
    }
    if (!selectedDocId || !docs.some((d) => d.id === selectedDocId)) {
      setSelectedDocId(docs[0].id);
    }
  }, [docs, selectedDocId]);

  // Load all pages (for FAQ page selector)
  React.useEffect(() => {
    (async () => {
      setPagesLoading(true);
      try {
        const all: Page[] = [];
        for (const doc of docs) {
          const pl = await apiGet<PageListResponse>(`/documents/${doc.id}/pages`);
          all.push(...pl.items);
        }
        setPages(all);
      } catch {
        // ignore
      } finally {
        setPagesLoading(false);
      }
    })();
  }, [docs]);

  const onUpload = async () => {
    if (!uploadFile) return;
    setUploading(true);
    setError(null);
    setUploadProgress(null);

    try {
      const fd = new FormData();
      fd.append("file", uploadFile);
      fd.append("title", uploadTitle);

      const baseUrl = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
      const response = await fetch(`${baseUrl}/documents/upload`, {
        method: "POST",
        body: fd,
      });

      if (!response.ok) {
        throw new Error(`Upload failed: ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();

      if (reader) {
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          const text = decoder.decode(value);
          const lines = text.split("\n");

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6));

                if (data.status === "processing") {
                  setUploadProgress({
                    message: data.message || "処理中...",
                    currentPage: data.current_page || 0,
                    totalPages: data.total_pages || 0,
                  });
                } else if (data.status === "completed") {
                  setUploadOpen(false);
                  setUploadTitle("");
                  setUploadFile(null);
                  setUploadProgress(null);
                  await refresh();
                } else if (data.status === "error") {
                  throw new Error(data.message || "処理中にエラーが発生しました");
                }
              } catch (parseError) {
                // Ignore parse errors for incomplete chunks
              }
            }
          }
        }
      }
    } catch (e: any) {
      setError(e?.message || String(e));
    } finally {
      setUploading(false);
      setUploadProgress(null);
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

  const openPageDetail = (page: Page) => {
    setPageDetail(page);
    setPageDetailOpen(true);
  };

  const closePageDetail = () => {
    setPageDetailOpen(false);
    setPageDetail(null);
  };

  const pagesForSelectedDoc = React.useMemo(() => {
    if (!selectedDocId) return [];
    return pages.filter((p) => p.document_id === selectedDocId);
  }, [pages, selectedDocId]);

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

        {/* Pages */}
        <Paper sx={{ p: 2, mb: 3 }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 2, flexWrap: "wrap" }}>
            <Typography variant="h6" sx={{ flexGrow: 1 }}>
              ページ構造化データ
            </Typography>
            <TextField
              select
              size="small"
              label="ドキュメント"
              value={selectedDocId}
              onChange={(e) => setSelectedDocId(e.target.value)}
              sx={{ minWidth: 240 }}
              disabled={docs.length === 0}
            >
              {docs.map((d) => (
                <MenuItem key={d.id} value={d.id}>
                  {d.title}
                </MenuItem>
              ))}
            </TextField>
          </Box>

          {pagesLoading && <LinearProgress sx={{ mb: 2 }} />}

          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>ページ</TableCell>
                <TableCell>タイトル</TableCell>
                <TableCell>検索クエリ</TableCell>
                <TableCell align="right">操作</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {pagesForSelectedDoc.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>P.{p.page_number}</TableCell>
                  <TableCell>{p.title || "-"}</TableCell>
                  <TableCell sx={{ maxWidth: 360 }}>
                    <Typography
                      variant="body2"
                      sx={{ whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}
                    >
                      {p.search_query || "-"}
                    </Typography>
                  </TableCell>
                  <TableCell align="right">
                    <Button variant="outlined" size="small" onClick={() => openPageDetail(p)}>
                      構造化データを見る
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {!pagesLoading && pagesForSelectedDoc.length === 0 && (
                <TableRow>
                  <TableCell colSpan={4}>
                    {docs.length === 0 ? "ドキュメントがありません" : "ページがありません"}
                  </TableCell>
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
      <Dialog open={uploadOpen} onClose={() => !uploading && setUploadOpen(false)} fullWidth>
        <DialogTitle>ドキュメントアップロード</DialogTitle>
        <DialogContent sx={{ display: "flex", flexDirection: "column", gap: 2, mt: 1 }}>
          <TextField
            label="タイトル（任意）"
            value={uploadTitle}
            onChange={(e) => setUploadTitle(e.target.value)}
            placeholder="例: 入居者マニュアル"
            disabled={uploading}
          />
          <Button variant="outlined" component="label" disabled={uploading}>
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

          {/* Progress display */}
          {uploading && uploadProgress && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="body2" color="primary" sx={{ mb: 1 }}>
                {uploadProgress.message}
              </Typography>
              {uploadProgress.totalPages > 0 && (
                <>
                  <LinearProgress
                    variant="determinate"
                    value={(uploadProgress.currentPage / uploadProgress.totalPages) * 100}
                    sx={{ height: 8, borderRadius: 4 }}
                  />
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
                    {uploadProgress.currentPage} / {uploadProgress.totalPages} ページ完了
                  </Typography>
                </>
              )}
              {uploadProgress.totalPages === 0 && (
                <LinearProgress sx={{ height: 8, borderRadius: 4 }} />
              )}
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setUploadOpen(false)} disabled={uploading}>
            キャンセル
          </Button>
          <Button variant="contained" onClick={onUpload} disabled={!uploadFile || uploading}>
            {uploading ? <CircularProgress size={18} /> : "アップロード"}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Page Detail Dialog */}
      <Dialog open={pageDetailOpen} onClose={closePageDetail} fullWidth maxWidth="lg">
        <DialogTitle>
          {pageDetail ? `構造化データ: ${pageLabel(pageDetail)}` : "構造化データ"}
        </DialogTitle>
        <DialogContent>
          {pageDetail ? (
            <Box
              sx={{
                display: "grid",
                gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
                gap: 2,
              }}
            >
              <Box sx={{ display: "flex", justifyContent: "center" }}>
                {pageDetail.image_url ? (
                  <>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={pageDetail.image_url}
                      alt={`P.${pageDetail.page_number}`}
                      style={{ maxWidth: "100%", height: "auto", borderRadius: 8 }}
                    />
                  </>
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    画像がありません
                  </Typography>
                )}
              </Box>
              <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">
                    タイトル
                  </Typography>
                  <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                    {pageDetail.title || "未抽出"}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">
                    検索クエリ
                  </Typography>
                  <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                    {pageDetail.search_query || "未抽出"}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">
                    本文テキスト
                  </Typography>
                  <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                    {pageDetail.page_text || "未抽出"}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="subtitle2" color="text.secondary">
                    図表/画像の説明
                  </Typography>
                  <Typography variant="body2" sx={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
                    {pageDetail.img_description || "未抽出"}
                  </Typography>
                </Box>
              </Box>
            </Box>
          ) : (
            <Typography variant="body2" color="text.secondary">
              表示できるデータがありません。
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={closePageDetail}>閉じる</Button>
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
