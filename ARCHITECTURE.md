# アーキテクチャ・機能詳細ドキュメント

## 概要

テナント入居者向けAIアシスタントシステム。PDFやPPTXドキュメントをアップロードし、AIが内容を理解して質問に回答します。

## 技術スタック

| レイヤー | 技術 |
|---------|------|
| フロントエンド | Next.js 14 (App Router) + Material-UI |
| バックエンド | FastAPI + SQLAlchemy |
| データベース | MySQL 8.0 |
| ベクトル検索 | FAISS + OpenAI Embeddings |
| AI | Google Gemini (OCR・チャット) |
| コンテナ | Docker Compose |

---

## 1. チャット機能

### 1.1 2段階処理アーキテクチャ

ユーザー体験を向上させるため、チャット処理を2段階に分離しています。

```
ユーザー質問
    │
    ├─► [Step 1: /chat/prepare] 高速レスポンス（〜1秒）
    │   ├─ クエリ改写（会話履歴考慮）
    │   └─ FAQ検索（FAISS）
    │   → FAQ候補を即座に表示
    │
    └─► [Step 2: /chat] 詳細回答生成（数秒）
        ├─ チャンク検索（FAISS）
        ├─ LLM回答生成
        └─ 参照ページ抽出
        → AI回答を追加表示
```

### 1.2 投機的並列実行

回答生成の高速化のため、テキストモードとPDFモードを並列実行します。

```python
# PDFタスクをバックグラウンドで先行開始
pdf_task = asyncio.create_task(create_llm_answer_with_pdf(...))

# テキストモードを実行
text_llm = await create_llm_answer_text_only(...)

if text_llm.image_use:
    # PDFが必要 → 先行開始したタスクの結果を使用
    llm = await pdf_task
else:
    # テキストで十分 → PDFタスクをキャンセル
    pdf_task.cancel()
```

**フォールバック戦略**:
- テキストモード失敗 → PDFモードに自動切り替え
- PDFモード失敗 → テキスト回答で対応
- 両方失敗 → エラーを返す

### 1.3 会話コンテキスト管理

直近5件のメッセージから会話履歴を構築し、クエリ改写時に活用します。

```
会話履歴:
  ユーザー: ゴミ捨て場はどこですか？
  アシスタント: 1階北側にあります。
  ユーザー: 利用時間は？ ← 「それ」が「ゴミ捨て場」を指すことを解決

→ 改写後クエリ: "ゴミ捨て場 利用時間"
```

### 1.4 LLMプロンプトの工夫

| 項目 | 対策 |
|------|------|
| 外部知識の排除 | 「入力に存在しない単語を追加しないこと」を明示 |
| 信頼度表示 | 確信度が低い場合「※確認が必要です」を出力 |
| 参照制限 | referenced_pagesは実際に添付したページのみ |
| 画像判定 | LLMが `image_use` フラグでPDF必要性を判定 |

### 1.5 停止機能

フロントエンドでAbortControllerを使用し、リクエスト中断が可能です。

```typescript
// 停止ボタン押下時
const handleStop = () => {
  abortControllerRef.current?.abort();
};

// APIコール時にsignalを渡す
await apiPostJson("/chat", data, signal);
```

---

## 2. ドキュメント処理

### 2.1 処理パイプライン

```
PDF/PPTX アップロード
    │
    ├─► PPTX → PDF変換（LibreOffice）
    │
    └─► ページ分割・処理（各ページで）
        ├─ PDF抽出（pypdf）
        ├─ PNG変換（プレビュー用）
        └─ Gemini OCR + 構造化出力
            ├─ title: ページ見出し
            ├─ search_query: 検索用キーワード
            ├─ page_text: OCRテキスト
            └─ img_description: 図表説明
        │
        └─► FAISSインデックス追加
```

### 2.2 Gemini構造化出力

Pydanticモデルを使用してGeminiからJSON形式で出力を取得します。

```python
class PageExtraction(BaseModel):
    title: Optional[str] = Field(description="ページの見出し")
    search_query: str = Field(description="検索用キーワード")
    page_text: Optional[str] = Field(description="OCRテキスト")
    img_description: Optional[str] = Field(description="図表の説明")

result = await generate_structured(
    model="gemini-3-pro-preview",
    contents=[pdf_bytes, prompt],
    schema_model=PageExtraction,
)
```

### 2.3 ストリーミング進捗通知

大きなファイル処理中の進捗をSSE（Server-Sent Events）で通知します。

```python
# バックエンド
async def generate_progress():
    async for progress in process_document_with_progress(...):
        yield f"data: {json.dumps(progress)}\n\n"
        # { "current": 3, "total": 10, "status": "processing" }

return StreamingResponse(generate_progress(), media_type="text/event-stream")
```

```typescript
// フロントエンド
const reader = response.body?.getReader();
while (true) {
  const { value, done } = await reader.read();
  if (done) break;
  const progress = JSON.parse(new TextDecoder().decode(value));
  setProgress(progress.current / progress.total * 100);
}
```

---

## 3. ベクトル検索

### 3.1 2つの独立したインデックス

| インデックス | 用途 | 検索対象 |
|-------------|------|----------|
| chunk_faiss | ドキュメント検索 | ページのsearch_query |
| faq_faiss | FAQ検索 | FAQのsearch_query |

### 3.2 埋め込みモデル

OpenAI `text-embedding-3-large` を使用（3072次元）。

```python
embeddings = OpenAIEmbeddings(
    model="text-embedding-3-large",
    openai_api_key=settings.openai_api_key,
)
```

### 3.3 スコア変換

FAISSのL2距離を0〜1のrelevance_scoreに変換。

```python
def _distance_to_relevance(distance: float) -> float:
    return 1.0 / (1.0 + float(distance))
    # 距離0 → スコア1.0
    # 距離1 → スコア0.5
    # 距離∞ → スコア0.0
```

---

## 4. セッション管理

### 4.1 クライアント側セッションID生成

```typescript
const SESSION_KEY = "tenant_ai_session_id";

function getOrCreateSessionId(): string {
  const existing = localStorage.getItem(SESSION_KEY);
  if (existing) return existing;

  const sid = `sess_${crypto.randomUUID()}`;
  localStorage.setItem(SESSION_KEY, sid);
  return sid;
}
```

### 4.2 会話履歴の永続化

- **DB保存**: Conversation → Message → MessageReference
- **リロード時復元**: `GET /chat/conversations/{sessionId}`
- **新規会話**: 「新しい会話を開始」で新しいsessionId生成

---

## 5. FAQ管理

### 5.1 ドラッグ&ドロップ並べ替え

@dnd-kit/core を使用した並べ替え機能。

```typescript
// 並べ替え後にAPIコール
await apiPutJson("/faqs/reorder", {
  faq_ids: newOrder.map(faq => faq.id)
});
```

### 5.2 FAISSインデックス自動再構築

FAQ作成・更新・削除時にインデックスを自動再構築。

```python
async def rebuild_faq_index(db: AsyncSession):
    faqs = await db.execute(select(FAQ))
    texts = [f.search_query for f in faqs.scalars().all()]
    metadatas = [{"faq_id": f.id, ...} for f in faqs]
    faiss_service.build_index_from_texts(settings.faq_faiss_dir, texts, metadatas)
```

---

## 6. 使用しているGeminiモデル

| 用途 | モデル | 特徴 |
|------|--------|------|
| OCR・画像理解 | gemini-3-pro-preview | 高精度、PDF対応 |
| クエリ改写 | gemini-3-flash-preview | 高速 |
| テキスト回答 | gemini-3-flash-preview | 高速 |
| PDF付き回答 | gemini-3-pro-preview | 高精度、マルチモーダル |

---

## 7. データモデル

```
Document (1) ─────► (N) Page
    │                    │
    │                    └─► FAISSインデックス (chunk_faiss)
    │
Conversation (1) ─► (N) Message (1) ─► (N) MessageReference
    │                    │                        │
    └─ session_id        └─ role: user/assistant  └─► Page

FAQ ─────────────────► FAISSインデックス (faq_faiss)
    │
    └─► Page (参照)
```

---

## 8. 最適化ポイント

| カテゴリ | 実装 |
|---------|------|
| 非同期処理 | FastAPI + asyncio |
| CPU処理オフロード | asyncio.to_thread() |
| 投機的実行 | PDF処理を並列で先行開始 |
| リトライ | tenacityで指数バックオフ |
| タイムアウト | 60秒でPDF処理をキャンセル |
| 段階的UI更新 | prepare → FAQ表示 → 回答追加 |
| リクエスト中断 | AbortController |

---

## 9. セキュリティ考慮事項

- **CORS設定**: 環境変数で許可オリジンを制御
- **ファイル検証**: PDF/PPTXのみアップロード可
- **入力検証**: Pydanticで自動バリデーション
- **プロンプトインジェクション対策**: 外部知識使用禁止を明示

---

## 10. 今後の拡張案

1. **Redisキャッシュ**: 頻出クエリの検索結果をキャッシュ
2. **マルチテナント**: 顧客ごとにドキュメント・FAQを分離
3. **分析機能**: 人気質問の集計、回答精度の監視
4. **モデル選択**: ユーザーごとにPro/Flashを切り替え
5. **チャット削除**: GDPR対応の完全削除機能
