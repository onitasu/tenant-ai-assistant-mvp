# Vercel + Railway デプロイ手順

## 構成

```
┌─────────────────┐      ┌─────────────────────────┐
│     Vercel      │      │        Railway          │
│   (Frontend)    │ ───→ │  Backend + MySQL        │
│    Next.js      │      │  FastAPI + FAISS        │
└─────────────────┘      │  + Volume (storage)     │
                         └─────────────────────────┘
```

---

## Step 1: Railway でバックエンドをデプロイ

### 1.1 Railway アカウント作成

1. https://railway.app にアクセス
2. GitHub アカウントでサインアップ

### 1.2 新規プロジェクト作成

1. 「New Project」をクリック
2. 「Deploy from GitHub repo」を選択
3. このリポジトリを選択

### 1.3 MySQL サービス追加

1. プロジェクト画面で「+ New」→「Database」→「MySQL」を選択
2. MySQL サービスが作成される
3. `MYSQL_URL` 変数が自動で設定される

### 1.4 バックエンドサービスの設定

1. backend サービスをクリック
2. 「Settings」タブで以下を設定:
   - **Root Directory**: `backend`
   - **Builder**: Dockerfile

3. 「Variables」タブで環境変数を追加:

| 変数名 | 値 |
|--------|-----|
| `MYSQL_URL` | (MySQL サービスから参照: `${{MySQL.MYSQL_URL}}`) |
| `OPENAI_API_KEY` | あなたの OpenAI API キー |
| `GEMINI_API_KEY` | あなたの Gemini API キー |
| `BACKEND_PUBLIC_URL` | (後で設定 - デプロイ後のURL) |
| `CORS_ORIGINS` | (後で設定 - Vercel URL) |
| `STORAGE_DIR` | `/app/storage` |

### 1.5 永続ボリュームの追加 (FAISSインデックス用)

1. backend サービスの「Settings」タブ
2. 「Volumes」セクションで「+ Add Volume」
3. Mount Path: `/app/storage`
4. これでFAISSインデックスとアップロードファイルが永続化される

### 1.6 デプロイ確認

1. 自動でデプロイが開始される
2. 「Deployments」タブでログを確認
3. デプロイ完了後、「Settings」→「Networking」→「Generate Domain」でURLを取得

### 1.7 環境変数の更新

デプロイ後のURLを取得したら:

```
BACKEND_PUBLIC_URL=https://your-backend.up.railway.app
```

---

## Step 2: Vercel でフロントエンドをデプロイ

### 2.1 Vercel アカウント作成

1. https://vercel.com にアクセス
2. GitHub アカウントでサインアップ

### 2.2 新規プロジェクト作成

1. 「Add New...」→「Project」
2. GitHub リポジトリをインポート
3. 以下の設定:
   - **Framework Preset**: Next.js
   - **Root Directory**: `frontend`

### 2.3 環境変数の設定

「Environment Variables」で以下を追加:

| 変数名 | 値 |
|--------|-----|
| `NEXT_PUBLIC_API_BASE_URL` | `https://your-backend.up.railway.app/api/v1` |
| `NEXT_PUBLIC_STATIC_BASE_URL` | `https://your-backend.up.railway.app` |

### 2.4 デプロイ

1. 「Deploy」をクリック
2. デプロイ完了後、Vercel URL を取得

### 2.5 Railway の CORS 設定を更新

Vercel URL を取得したら、Railway の環境変数を更新:

```
CORS_ORIGINS=["https://your-app.vercel.app"]
```

---

## Step 3: 動作確認

1. Vercel の URL にアクセス
2. ドキュメントをアップロードしてみる
3. チャット機能を試す

---

## トラブルシューティング

### CORS エラーが出る

- Railway の `CORS_ORIGINS` が正しく設定されているか確認
- JSON 配列形式 `["https://..."]` またはカンマ区切り形式 `https://...,https://...` で設定

### データベース接続エラー

- Railway の MySQL サービスが起動しているか確認
- `MYSQL_URL` が正しく参照されているか確認

### ファイルアップロードが失敗する

- Railway の Volume が正しくマウントされているか確認
- `/app/storage` ディレクトリに書き込み権限があるか確認

### 画像が表示されない

- `BACKEND_PUBLIC_URL` が正しいか確認
- `NEXT_PUBLIC_STATIC_BASE_URL` が Railway の URL と一致しているか確認

---

## ローカル開発に戻る場合

```bash
docker-compose up -d
```

ローカルでは従来通り `docker-compose.yml` の設定が使われます。

---

## 料金目安

| サービス | 無料枠 |
|----------|--------|
| Railway | $5/月分 (Hobbyプラン) |
| Vercel | 100GB 帯域幅/月 |

小規模な利用であれば無料枠内で運用可能です。
