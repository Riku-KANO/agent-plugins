# REST API 設計リファレンス

REST 固有の作法と、現場で踏みがちな落とし穴。SKILL.md の汎用原則に**追加**して適用する。

## リソース命名

### URL パスは kebab-case

このプラグインでは REST の **URL パスを kebab-case に統一**する（複数語をハイフンで区切る）。

```
✓ /users
✓ /user-profiles
✓ /order-items
✓ /api-keys
✓ /shipping-addresses
✓ /users/{id}/payment-methods

✗ /userProfiles     (camelCase はパスでは使わない)
✗ /user_profiles    (snake_case はパスでは使わない)
✗ /UserProfiles     (PascalCase はパスでは使わない)
```

理由:
- URL はホスト名と同じ世界の文字列で、ホスト名がハイフン区切りであることと整合する
- 一部のサーバー / クライアントが URL を大小文字で同一視するため camelCase は不安定
- アンダースコア `_` は古いブラウザのアンダーライン装飾と被って視認性が落ちる、リンクテキストとして読みづらい
- Google / Stripe / GitHub など主要公開 API も kebab-case 採用が多数派

### その他の命名規則

- **複数形 + 名詞** が基本: `/users`, `/orders`, `/invoices`。
- 階層は意味のあるオーナーシップのみ表現: `/users/{id}/sessions` は session が user に帰属するから OK。逆に `/users/{id}/posts/{post-id}/comments/{comment-id}/replies/{reply-id}` のような深いネストは避ける（2 階層を超えたら独立リソース化を検討）。パスパラメータの placeholder 名も同様に kebab-case で揃える。
- 動詞をパスに入れたくなったら、まず「これはリソースの状態遷移ではないか?」と問う。
  - `POST /orders/{id}/cancel` よりも、cancel が独立した状態遷移なら `PATCH /orders/{id}` で `status: cancelled` を送る方が REST らしい。
  - ただし副作用の重い「アクション」（メール送信、決済実行）は素直に `POST /orders/{id}/refund` のような action endpoint にして良い。例外として認識し、理由を明記する。action 名も kebab-case（`/orders/{id}/cancel-shipment` 等）。

### JSON ボディのフィールド名は別の話

URL パスを kebab-case にすることと、**レスポンス/リクエスト JSON のフィールド名をどうするかは独立した決定**。

- JSON では `kebab-case` はキーとしてアクセスしづらい言語が多い（`obj["user-name"]` のようにブラケット必須）。
- 実用的には **snake_case か camelCase** から 1 つ選び、API 全体で一貫させる。
  - snake_case 例: Stripe、GitHub
  - camelCase 例: Google Cloud、Twitter
- 既存システムの慣習があればそれに合わせる。新規ならどちらでもよいが、**JSON ボディは kebab-case にはしない**。

```json
{
  "user_id": "u_123",
  "shipping_address": { "postal_code": "100-0001" }
}
```

または

```json
{
  "userId": "u_123",
  "shippingAddress": { "postalCode": "100-0001" }
}
```

クエリパラメータ名も JSON 側の規則に揃えるのが一般的（`?sort_by=created_at` か `?sortBy=createdAt`）。

## HTTP 動詞の使い分け

| 動詞 | 用途 | 冪等性 | リクエストボディ |
|---|---|---|---|
| `GET` | 取得 | ○ | 不可（仕様上） |
| `POST` | 新規作成 / アクション | × | 可 |
| `PUT` | 全置換更新 | ○ | 可（全フィールド） |
| `PATCH` | 部分更新 | △（実装次第） | 可（差分） |
| `DELETE` | 削除 | ○ | 通常なし |

- `PUT` と `PATCH` の混在は禁物。リソースの全置換が現実的でない場合（巨大オブジェクト、サーバー側計算フィールドあり）は `PATCH` のみで運用。
- `PATCH` は JSON Merge Patch (RFC 7396) か JSON Patch (RFC 6902) を選んで明示する。独自仕様は避ける。

## ステータスコード

最低限これだけ使い分ければ実用十分。

| コード | 意味 |
|---|---|
| `200 OK` | 取得成功・更新成功（ボディあり） |
| `201 Created` | 作成成功。`Location` ヘッダで新リソース URL を返す |
| `202 Accepted` | 非同期処理開始。job ID を返す |
| `204 No Content` | 成功でボディ不要（DELETE 等） |
| `400 Bad Request` | リクエスト構文・バリデーションエラー |
| `401 Unauthorized` | 認証されていない（クレデンシャル不足/無効） |
| `403 Forbidden` | 認証済みだが認可なし |
| `404 Not Found` | リソース不在 |
| `409 Conflict` | 楽観的ロック失敗、重複作成 |
| `422 Unprocessable Entity` | 構文 OK だが意味的に無効（ビジネスルール違反） |
| `429 Too Many Requests` | レート制限。`Retry-After` 必須 |
| `500 Internal Server Error` | サーバー側の予期しない失敗 |
| `503 Service Unavailable` | 一時的に処理不可。`Retry-After` 推奨 |

過剰に細かいコード（418, 451 等）は避ける。クライアント実装が分岐できないコードは害でしかない。

## ページネーション

3 方式の特徴:

| 方式 | 長所 | 短所 |
|---|---|---|
| Cursor | 一貫性、追加/削除に強い | 任意ページジャンプ不可 |
| Offset/Limit | 直感的、任意ジャンプ可 | 大きい offset で重い、追加/削除で重複/欠落 |
| Page/Size | UI が組みやすい | offset と同じ問題 |

**第一選択は Cursor**。レスポンス例:

```json
{
  "items": [...],
  "page_info": {
    "next_cursor": "eyJpZCI6MTIzfQ==",
    "has_more": true
  }
}
```

- カーソルは不透明な文字列（base64 等）にして、フィールド意味を露出しない（将来の内部実装変更を許容するため）。
- `total` を返すかは別判断。重ければ省略 or 概算（"about 10,000+"）に。

## フィルタ / 並び替え

- クエリパラメータで標準的な形に: `?status=active&sort=-created_at&fields=id,name`。
- 多次元クエリ（`?filter[status][in]=a,b&filter[created_at][gte]=...`）は便利だがパース複雑性とインジェクション面が増える。本当に必要になるまで導入しない。
- どのフィールドで filter/sort できるかは仕様で明示。`/users?email=...` で必ずヒットすると思って実装した結果インデックス無しで全件スキャン、はよくある事故。

## エラーレスポンス

```json
{
  "error": {
    "code": "ORDER_NOT_FOUND",
    "message": "Order with id 'abc' was not found",
    "request_id": "req_01HX2...",
    "details": [
      {"field": "items[0].quantity", "issue": "must be >= 1"}
    ]
  }
}
```

- `code` は安定したスネークケース or アッパースネーク。仕様の一級市民として変更時は破壊的変更扱い。
- `details[]` はバリデーション失敗の構造化情報用（人間メッセージとは別レイヤ）。
- スタックトレースは絶対に返さない（情報漏洩）。

RFC 7807 (Problem Details) を選ぶのも有力 — 形式が標準化されているので公開 API 向け。

## コンテンツネゴシエーション

- `Content-Type: application/json` を既定にし、それ以外（CSV、Protobuf）は `Accept` ヘッダで切り替え。
- バージョンを `Accept: application/vnd.example.v2+json` で表現する流派もあるが、運用と理解の難しさから **URL パスでバージョンする方が公開 API では推奨**（`/v1/users`）。

## 冪等性キー (Idempotency-Key)

- POST のリトライを安全にしたい場合に必須。
- Stripe の慣習: `Idempotency-Key: <client-generated-uuid>` ヘッダ → サーバー側で 24 時間程度キャッシュし、同じキー + 同じパスで来たら前回レスポンスを返す。
- キャッシュ衝突（同じキーで異なるボディ）は `409` で拒否。

## キャッシュ

- `Cache-Control`, `ETag`, `Last-Modified` を活用すると CDN/ブラウザ層で大きく効く。
- `ETag` + `If-None-Match` で 304 を返せると帯域節約。
- 認証付きエンドポイントは `Cache-Control: private` を忘れない。

## HATEOAS

- 理論上は美しいが、現実の REST API の多くは採用していない。導入するなら全エンドポイントで一貫させる必要があり、半端な採用は混乱を呼ぶ。
- 採用しない場合は素直に「URL パターンはドキュメントで提供する」と割り切る。

## レビュー時の重点チェック

- [ ] パスに動詞が入っていないか（例外は理由付きで OK）
- [ ] ステータスコードと body の整合性（404 なのに body にデータが入っている、等）
- [ ] エラー code が安定した識別子になっているか
- [ ] ページネーション方式が一貫しているか
- [ ] 認可チェックがミドルウェアレベルで漏れなく書けているか
- [ ] バージョニング方針が決まっているか
- [ ] レート制限ヘッダが定義されているか
- [ ] 同期で重い処理を `200 OK` で返していないか（`202 Accepted` + job が適切な場合）
