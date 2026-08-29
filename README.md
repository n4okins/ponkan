# LingoDeck mock

Google Sheets を教材DBとして使う、サーバーレスの英単語学習Webアプリのモックです。

## 特徴

- GitHub Pages で完全静的配信
- Google Sheets の「ウェブに公開」CSVを直接読み込み
- CSV取得失敗時は `sample-data/words.csv` へフォールバック
- 学習履歴はブラウザの `IndexedDB`、軽量設定は `localStorage` に保存
- カード学習 → 4択テスト
- 誤答単語を同一セッション内へ再挿入
- `stability / difficulty / dueAt` による簡易SRS
- 4段階習熟度: 苦手 / うろ覚え / ほぼ覚えた / 覚えた
- Web Speech API で発音
- PWA / Service Worker 対応
- ビルド不要（HTML/CSS/JSのみ）

## Google Sheets の列

1行目を以下のヘッダーにしてください。

```csv
id,word,meaning,pronunciation,example,example_ja,part_of_speech,level,tags,enabled
```

必須は `id`, `word`, `meaning` です。`enabled` は `false` / `0` / `off` で無効化できます。

### 公開

Google Sheets で:

1. `ファイル` → `共有` → `ウェブに公開`
2. 対象タブを選択
3. 形式を `カンマ区切り値 (.csv)` にする
4. 公開URLをコピー
5. アプリの「設定」画面へ貼り付け

URL例:

```text
https://docs.google.com/spreadsheets/d/e/2PACX-.../pub?gid=0&single=true&output=csv
```

公開したシートの内容はインターネットから閲覧可能になるため、秘密情報は置かないでください。

## ローカル実行

`file://` では `fetch()` が制限されるため、簡単なHTTPサーバーで起動してください。

```bash
python3 -m http.server 8080
```

その後 `http://localhost:8080` を開きます。

## GitHub Pages

このリポジトリを GitHub へ push し、Repository Settings → Pages → Source を `GitHub Actions` に設定します。

`.github/workflows/pages.yml` が `main` への push ごとに静的ファイルを Pages へデプロイします。

## 学習アルゴリズム（モック）

各単語に以下を保持します。

- seen / correct / wrong
- correct streak
- stability（日）
- difficulty (1..10)
- dueAt
- average response time
- mastery

想起率は概念的に:

```text
R(t) = 0.9 ^ (t / stability)
```

正解時は回答時間に応じて stability を増加、誤答時は約1/4へ低下させます。

習熟度の目安:

- `weak`: 未学習・直近誤答・stability < 1日
- `fuzzy`: 1〜4日
- `almost`: 4〜14日
- `mastered`: 14日以上 + 正解数 >= 誤答数 + 2連続正解

出題優先度は `期限超過 + 低習熟度 + 推定想起率低下 + 新規語` を合成したスコアです。

## 本番化する際の候補

このモックは意図的に依存ゼロです。本番版では必要に応じて TypeScript + Vite + Dexie.js/IndexedDB + Zod + Vitest へ移行できます。
