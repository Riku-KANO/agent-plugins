# GraphQL API 設計リファレンス

REST と前提が違うので、REST の感覚を持ち込みすぎないこと。

## スキーマ設計の基本

- **クライアント駆動**: 「フロントエンドが必要なフィールドを選ぶ」が前提。サーバーは必要そうなものを最大限露出する代わりに、過剰な事前カスタマイズを避ける。
- 命名は **camelCase**（フィールド・引数）+ **PascalCase**（型）+ **UPPER_SNAKE_CASE**（enum）。
- スキーマファースト（SDL を先に書く）かコードファースト（ジェネレータ）かはチームで選択。SDL を**契約の唯一の真実**として扱うのが理想。

## 型設計の原則

- **null 設計を明確に**: `String!` (non-null) と `String` (nullable) は API 契約の最重要部分。エラー時に null を返したいなら nullable、必須なら non-null。
- **Object と Interface と Union を使い分ける**: 共通フィールドがあるが型は違う → Interface。完全に別物だが返却位置が同じ → Union。
- **ID 型を使う**: スカラ ID は `ID!`。文字列とは区別する。
- **Enum を活用**: 状態・カテゴリは String ではなく Enum に。スキーマ進化時の影響範囲が明確になる。

## クエリ設計

```graphql
type Query {
  user(id: ID!): User
  users(first: Int, after: String, filter: UserFilter): UserConnection!
  currentUser: User
}
```

- **Connection 規約 (Relay) を採用**: ページネーションは `edges`/`node`/`pageInfo` の Relay Cursor Connection で。生の配列を返すと後付けでページネーション入れるとき破壊的変更になる。
- **filter / sort は専用 input 型**にまとめる。引数羅列は読みづらく拡張も辛い。

## ミューテーション設計

- **動詞 + 対象** で命名: `createUser`, `updateOrder`, `cancelSubscription`。
- **input 型を 1 つ受ける**形に統一: `createUser(input: CreateUserInput!): CreateUserPayload!`。
  - 引数を増やすときに破壊的変更を避けられる。
- **payload で affected entities を返す**: `{user: User, errors: [UserError!]!}` のような形。クライアントが reload せずに状態更新できる。
- **エラーを payload に含めるか throw するか**を最初に決める（後述）。

## サブスクリプション設計

- 「リアルタイムで変化が必要」な対象に限定（チャット、ライブ通知、価格 tick）。
- WebSocket 経由が一般的だが、運用負荷は高い。本当に必要か検討してから入れる。
- 認可は接続時 + イベント発生時の二段で考える。

## N+1 問題

これは GraphQL の宿命の一つ。

```graphql
{
  users {
    posts {
      author {  # users 件数 × posts 件数 の author 取得 が走る
        name
      }
    }
  }
}
```

- **DataLoader パターン必須**: バッチング + キャッシュで 1 リクエスト内の重複読み出しをまとめる。
- リゾルバを書く前に「これは N+1 を起こすか」をチェックする習慣を。

## エラー戦略

2 つの流派 — どちらか一貫させる。

### 1. GraphQL errors 配列で返す（throw 方式）

- リゾルバが throw → `errors` 配列に入る。
- 利点: 構造が単純。
- 欠点: クライアントは GraphQL errors と payload を別レイヤで処理する必要があり、型推論が効きにくい。

### 2. payload 内に errors フィールド（union 方式 / errors-as-data）

```graphql
type CreateUserPayload {
  user: User
  errors: [CreateUserError!]!
}

union CreateUserError = EmailAlreadyTakenError | InvalidPasswordError | RateLimitedError
```

- 利点: 型安全に「想定済みエラー」を扱える。クライアントが switch で網羅できる。
- 欠点: スキーマがやや膨らむ。
- **公開 API・複雑なフロント向けには errors-as-data 方式を強く推奨**。

予期しない例外（500 系）は throw でよい — それらは扱いが共通だから。

## 認可

- リゾルバ内で `context.user` を見てチェック、が基本。
- フィールドレベル認可（このユーザーは `User.email` を見れない等）は GraphQL の強み。`null` を返すか、エラーにするか方針を決める。
- スキーマディレクティブ (`@auth(role: ADMIN)`) でメタ的に表現すると一貫しやすい。

## バージョニング

- GraphQL の流儀は **非破壊的進化**: フィールド追加 / Deprecate → 削除はクライアント追従を待ってから。
- `@deprecated(reason: "Use newField instead")` ディレクティブを必ず使う。
- v2 を別エンドポイントで切る運用も可能だが、GraphQL の長所を捨てる方向なので最後の手段。

## クエリ複雑度制御

- 公開 GraphQL では、深さ制限・複雑度スコア・タイムアウトの 3 段で守る。
- 「全 user → 全 post → 全 comment → 全 author」のような攻撃的クエリで DoS が起きる。
- `graphql-cost-analysis` などのライブラリで複雑度上限を設定。

## レビュー時の重点チェック

- [ ] null/non-null が意味通りに設計されているか
- [ ] Connection 規約でページネーションされているか
- [ ] mutation が input 型 + payload 型の規約に従っているか
- [ ] errors-as-data か throw か、戦略が一貫しているか
- [ ] N+1 を起こすリゾルバに DataLoader が入っているか
- [ ] フィールドレベル認可が必要な箇所で漏れていないか
- [ ] deprecated フィールドに reason が書かれているか
- [ ] 公開エンドポイントの場合、複雑度/深さ制限が入っているか
