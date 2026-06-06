# api-design

API 設計の原則とベストプラクティスを Claude に持たせるスキル。

- **対象スタイル**: REST / GraphQL / gRPC / WebSocket・SSE（横断的に扱う）
- **対象シナリオ**: 新規設計 / 既存設計レビュー / 破壊的変更とバージョニング
- **言語/フレームワーク**: 非依存（普遍的な設計原則のみ）
- **スキーマ生成**: 対象外（原則のガイダンスに集中）

## Install

```text
/plugin marketplace add Riku-KANO/agent-plugins
/plugin install api-design@personal-agents
```

## Try it

以下のような依頼で `api-design` スキルが発動する想定:

- 「ユーザー管理の REST API を設計したい」
- 「この OpenAPI をレビューしてほしい」
- 「v1 → v2 で破壊的変更を入れるが、どう移行すべき?」
- 「GraphQL と REST どちらがいい?」

## Layout

```
plugins/api-design/
├── .claude-plugin/plugin.json
├── README.md
└── skills/api-design/
    ├── SKILL.md
    └── references/
        ├── rest.md
        ├── graphql.md
        ├── grpc.md
        ├── streaming.md
        ├── throttling.md
        ├── versioning.md
        └── review-checklist.md
```

SKILL.md は汎用原則とワークフローのみを含み、スタイル固有の詳細は `references/` に分離している。Claude は必要なリファレンスのみを読み込む（progressive disclosure）。
