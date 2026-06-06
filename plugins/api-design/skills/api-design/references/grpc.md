# gRPC / Protocol Buffers 設計リファレンス

社内サービス間の RPC、強い型、双方向ストリーミングに強い。Google の API Design Guide (https://google.aip.dev/) が事実上の参照基準。

## .proto ファイル構成

- 1 サービス 1 proto ファイルが基本。複数サービスで共有する型は `common.proto` に分離。
- `package` 命名は階層的に: `com.example.users.v1`。`v1` をパッケージに含めると後の v2 共存が楽。
- `syntax = "proto3";` を明示。

## サービス / RPC 命名

```proto
service UserService {
  rpc GetUser(GetUserRequest) returns (GetUserResponse);
  rpc ListUsers(ListUsersRequest) returns (ListUsersResponse);
  rpc CreateUser(CreateUserRequest) returns (CreateUserResponse);
  rpc UpdateUser(UpdateUserRequest) returns (UpdateUserResponse);
  rpc DeleteUser(DeleteUserRequest) returns (google.protobuf.Empty);
}
```

- メソッド名は **動詞 + 対象** (PascalCase)。標準動詞は `Get`, `List`, `Create`, `Update`, `Delete`, `Batch*`, `Search`。
- Request/Response メッセージは **メソッド名 + Request/Response**。`google.protobuf.Empty` は使えるが、将来フィールド追加できないので避けて空メッセージを定義する方が安全。

## メッセージ設計

```proto
message User {
  string id = 1;
  string email = 2;
  string display_name = 3;
  UserStatus status = 4;
  google.protobuf.Timestamp created_at = 5;
  google.protobuf.Timestamp updated_at = 6;

  reserved 7, 8;
  reserved "deprecated_field_name";
}
```

- フィールド名は **snake_case**、メッセージ・enum 名は **PascalCase**。
- **フィールド番号は契約の一部**。一度割り当てたら絶対に再利用しない。削除時は `reserved` で永久に予約。
- 1–15 は 1 バイトでエンコードされるので、頻出フィールドに割り当てる。
- enum の 0 値は `UNSPECIFIED` を必ず置く（proto3 のデフォルト値ルール対応）。

```proto
enum UserStatus {
  USER_STATUS_UNSPECIFIED = 0;
  USER_STATUS_ACTIVE = 1;
  USER_STATUS_SUSPENDED = 2;
  USER_STATUS_DELETED = 3;
}
```

- enum の prefix を型名に揃えるのが Google 流（衝突防止）。

## ストリーミング種別

| 種別 | 用途 |
|---|---|
| Unary | 通常の 1:1 RPC |
| Server streaming | サーバー → クライアント連続送信（進捗、tail）|
| Client streaming | クライアント → サーバー連続送信（アップロード）|
| Bidirectional streaming | 双方向（チャット、低レイテンシ対話）|

- 双方向ストリーミングは強力だが運用難度が高い（接続管理、再接続、バックプレッシャ）。本当に必要かを問う。
- Unary で済むものを安易に streaming にしない。

## エラーハンドリング

- gRPC 標準ステータスコード (`OK`, `NOT_FOUND`, `PERMISSION_DENIED`, `RESOURCE_EXHAUSTED` 等) を使う。HTTP コードと **一対一対応しない**ことに注意。
- 詳細は `google.rpc.Status` + `details[]` (Any 型に追加情報) で表現。
- アプリ固有エラーは詳細メッセージ（`ErrorInfo`, `BadRequest`, `QuotaFailure` 等）として `details` に詰める。

## Deadline / Cancellation

- **全 RPC で deadline を設定**するのが規律。デフォルト無制限の運用は障害時の連鎖タイムアウトを生む。
- サーバー側は `context` の cancellation を尊重して途中で処理を打ち切る。

## リトライ / 冪等性

- gRPC は呼び出し失敗時に自動リトライ設定が可能 (`MethodConfig`)。**冪等な RPC のみリトライ対象**にする。
- 各 RPC のドキュメントコメントで「これは冪等か」を明示する。`Create*` は通常冪等でないので、必要なら request_id を受けて重複排除する。

## 後方互換ルール（互換性 cheatsheet）

| 変更 | 互換性 |
|---|---|
| 新フィールド追加 | 互換 |
| フィールド削除 → 番号を reserved | 互換（削除側） |
| フィールド型変更 | **非互換** |
| フィールド番号変更 | **非互換** |
| フィールド名変更 | wire 互換だがコード生成側で破壊 |
| `required` → `optional` (proto2) | 互換 |
| enum 値追加 | 互換（古いクライアントは UNSPECIFIED 扱い）|
| enum 値削除 | **非互換** |

迷ったら「フィールド削除より追加で対応」が原則。

## 命名以外のスタイル

- ID フィールドは `string` で UUID/ULID を入れることが多い。int64 にすると衝突や予測可能性の問題が出る。
- 時刻は `google.protobuf.Timestamp` を使う（独自 string にしない）。
- 金額は文字列 (decimal) または `google.type.Money`。float/double は絶対に使わない。
- リスト系レスポンスはページネーション前提に `next_page_token` (string) を入れておく。

```proto
message ListUsersResponse {
  repeated User users = 1;
  string next_page_token = 2;
}
```

## REST ゲートウェイ共存

- grpc-gateway などで gRPC → REST を生やす場合、HTTP マッピングを proto annotation で定義する形が一般的:

```proto
rpc GetUser(GetUserRequest) returns (User) {
  option (google.api.http) = {
    get: "/v1/users/{id}"
  };
}
```

- REST 経由の利用者がいるなら、REST のベストプラクティス（パス命名、ステータスコード）も同時に満たす必要がある。

## レビュー時の重点チェック

- [ ] フィールド番号の再利用がないか（`reserved` 使用）
- [ ] enum の 0 値が `*_UNSPECIFIED` か
- [ ] 時刻が `Timestamp`、金額が文字列 or `Money` か（float ではないか）
- [ ] 各 RPC に deadline 想定があるか
- [ ] ストリーミングを過剰に使っていないか
- [ ] 標準ステータスコードを誤用していないか（`INVALID_ARGUMENT` と `FAILED_PRECONDITION` の混同等）
- [ ] パッケージに `v1` が含まれているか
- [ ] 公開 API なら proto を独立リポ or 専用ディレクトリで管理しているか
