# Ponkan 2.0

**教材ソースを混ぜて学べる、セルフホスト型の汎用SRS / 問題バンク。**

英単語アプリとして始めた Ponkan を、英語・ロシア語・中国語などの言語学習に加え、情報処理安全確保支援士（セキスペ）など資格学習にも使える汎用学習システムへ変更した版です。

## 主な機能

- 複数の教材ソースを登録 / 編集 / 削除
- 学習時に複数ソースを任意選択して混合出題
- Google Sheets / 公開CSV URLから教材を同期
- 手動教材・手動問題の登録 / 編集 / 削除
- `prompt / answer / choices / explanation / tags` の汎用問題モデル
- `prompt_lang / answer_lang` による英語・ロシア語・中国語等のWeb Speech API読み上げ
- 4択問題とカード問題の両対応
- 選択肢を省略した場合、同じ学習プールの他の正答から4択を自動生成
- 誤答を同一セッション内へ再挿入
- `stability / difficulty / due_at` を使った簡易SRS
- SQLiteに教材・問題・学習履歴を永続保存
- 外部DB・Pythonパッケージ不要
- Docker / Docker Composeで自宅サーバに常駐可能

## 起動

```bash
git clone https://github.com/n4okins/ponkan.git
cd ponkan
docker compose up -d --build
```

ブラウザで:

```text
http://<自宅サーバのIP>:8080
```

更新:

```bash
git pull
docker compose up -d --build
```

停止:

```bash
docker compose down
```

データはホスト側の `./data/ponkan.db` に保存されます。コンテナを作り直しても消えません。

## 教材モデル

言語を特別扱いせず、すべてを `Source → Question → Progress` として扱います。

```text
Source
 ├─ English
 ├─ Русский
 ├─ 中文
 └─ セキスペ
       ↓
Question
 ├─ prompt
 ├─ answer
 ├─ choices[]
 ├─ explanation
 ├─ tags[]
 ├─ prompt_lang
 └─ answer_lang
       ↓
Progress / Reviews
```

これにより、歴史、法律、資格、社内研修、暗記カードなども同じ仕組みに追加できます。

## Google Sheets / CSV教材

教材画面で「種類 = Google Sheets / CSV URL」を選び、公開CSV URLを登録します。

Google Sheetsの通常共有URLが以下の形式なら、Ponkan側でCSV export URLへ自動変換します。

```text
https://docs.google.com/spreadsheets/d/<SHEET_ID>/edit?gid=0
```

シート自体は、Ponkanサーバから認証なしでCSV取得できる共有状態にしてください。

### 推奨列

```csv
id,prompt,answer,choices,explanation,tags,prompt_lang,answer_lang,question_type,enabled
q1,你好,こんにちは,,nǐ hǎo,chinese|HSK,zh-CN,ja,auto,true
q2,CSRF対策として直接的なものは？,CSRFトークンを検証する,CSRFトークンを検証する|DNSSEC|Base64化|ポート変更,状態変更リクエストの正当性を検証する,security|web,ja,ja,multiple_choice,true
```

- `id`: ソース内で一意。同期時の更新キー
- `prompt`: 問題
- `answer`: 正答
- `choices`: `|` 区切り、またはJSON配列。省略可能
- `explanation`: 解説
- `tags`: `,` / `|` / `;` 区切り
- `prompt_lang`: 読み上げ言語（例 `en`, `ru`, `zh-CN`, `ja`）
- `answer_lang`: 解答側言語
- `question_type`: `auto`, `multiple_choice`, `card`
- `enabled`: `false`, `0`, `off` 等で無効化

### 旧英単語CSVとの互換

旧形式も自動的に読み替えます。

```csv
id,word,meaning,pronunciation,example,example_ja,part_of_speech,level,tags,enabled
```

`word → prompt`、`meaning → answer` として取り込みます。

## 学習アルゴリズム

各問題に以下を保存します。

- seen / correct / wrong
- correct_streak
- stability
- difficulty
- due_at
- last_reviewed_at / last_result
- avg_response_ms
- mastery (`weak / fuzzy / almost / mastered`)

想起率の概念モデル:

```text
R(t) = 0.9 ^ (t / stability)
```

出題優先度は、未学習・期限超過・低習熟度・推定想起率低下を合成して決めます。正解時は回答速度に応じて `stability` を伸ばし、誤答時は約1/4へ縮めます。

習熟度の目安:

- `weak`: 直近誤答、または stability < 1日
- `fuzzy`: 1〜4日
- `almost`: 4〜14日
- `mastered`: 14日以上 + 正解数 >= 誤答数 + 2連続正解

## バックアップ

SQLiteファイルをコピーすればよいです。確実に整合したコピーを取るなら一時停止します。

```bash
docker compose stop ponkan
cp data/ponkan.db data/ponkan.db.backup
docker compose start ponkan
```

## セキュリティ

現状は**単一ユーザーの自宅利用**を想定しており、アプリ自身のログイン認証はありません。インターネットへ直接公開しないでください。

外部から使う場合は、Tailscale / WireGuard / Cloudflare Access、またはCaddy/nginx等の認証・TLS付きリバースプロキシを前段に置く構成を推奨します。

公開Google Sheets/CSVを教材に使う場合、そのURLへPonkanサーバ自身がHTTPアクセスします。信頼できるURLのみ登録してください。
