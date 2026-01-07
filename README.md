# テナント入居者向けAIアシスタント＆FAQ検索システム（MVP）

技術スタック: **Next.js 14 (App Router) + FastAPI + MUI + MySQL + FAISS (ローカル) + OpenAI Embeddings + Gemini**

---

## 1. 起動方法（Docker）

### 1) 環境変数を用意
`.env.example` を `.env` にコピーして、APIキーを設定してください。

```bash
cp .env.example .env
```

### 2) 起動
```bash
docker compose up --build
```

- Frontend: http://localhost:3000  
- Backend (Swagger): http://localhost:8000/docs  
- Backend (OpenAPI): http://localhost:8000/openapi.json  

---

## 2. 使い方（MVP）

### チャット画面
- URL: http://localhost:3000  
- 質問すると、FAQ候補（上位3件）とAI回答（参照ページ最大3件）が表示されます。

### 管理画面
- URL: http://localhost:3000/admin  
- **ドキュメント管理**: PDF/PPTXをアップロードして取り込み（PPTXはLibreOfficeでPDF変換してから処理）
- **FAQ管理**: FAQの追加/編集/削除（FAQ FAISSを自動再構築）

---

## 3. ストレージ構成

バックエンドの `backend/storage` 配下に保存します（docker-compose でホストへマウント）。

```
backend/storage/
  uploads/   # アップロードファイル
  images/    # ページ画像
  faiss/
    chunk_faiss/
    faq_faiss/
  tmp/
```

---

## 4. 注意事項

- OpenAI / Gemini APIキーが必須です（`.env` に設定）。
- 本MVPは「同期処理」でPDFのページ分割→OCR/画像理解→DB登録→FAISS登録を行います。大きいPDFでは時間がかかります。
- 本番ではキュー（Celery/RQ等）やジョブ管理（ステータス進捗）を導入してください。

---

## 5. ライセンス

社内検証用サンプル（MVP）です。
