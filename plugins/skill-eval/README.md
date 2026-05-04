# skill-eval (alpha)

> **Status**: `0.1.0-alpha.1` — まだ完成度が低い PoC 段階です。SDK の破壊変更や評価ロジックの調整が今後入ります。

`.claude/skills/<name>/SKILL.md` の効果を CI 上で A/B 検証するための Claude Code プラグイン。GitHub Copilot SDK (Python `github-copilot-sdk==0.3.0`) を LLM-as-judge として使用し、treatment (PR head 版) と control (base 版) を匿名比較して **改善 ✅ / 退行 ❌ / 同等 ➖** を判定します。

参考実装: [`C:\Users\81903\projects\skill-eval-sample`](file:///C:/Users/81903/projects/skill-eval-sample) — sample のマルチエージェント構成 (Implementer→Evaluator→Reporter) を継承し、シナリオだけは「ヒアリング型 `/skill-eval:create-test`」で事前作成する形に置き換えています。

## コマンド

| コマンド | 用途 |
|---|---|
| `/skill-eval:setup` | 当リポジトリにワークフロー＋ Python ランナーを展開 |
| `/skill-eval:create-test [skill]` | ヒアリングで**新規**テストシナリオを作成 |
| `/skill-eval:edit-test [skill]` | 既存シナリオを修正・削除・追加・全点検 (仕様変更時に使用) |

## 使い方の流れ

```
/skill-eval:setup                  # 1回だけ。ファイルを展開
# → COPILOT_GITHUB_TOKEN secret を追加 (Copilot 有料シート + Copilot:Read PAT)
/skill-eval:create-test <skill>    # シナリオ作成 (3〜5シナリオを対話で)
git commit && git push             # PR を作成
# PR コメントに "/skill-eval" と書くと CI 起動

# --- skill の仕様変更後 ---
/skill-eval:edit-test <skill>      # 既存シナリオを修正・削除・追加・全点検
```

詳細は `.skill-eval/README.md` (セットアップ後に展開される) を参照。

## 動作要件

- 消費側リポジトリが GitHub 上にあり、PR ベースで運用されている
- **Copilot 有料シート** を持つアカウントの fine-grained PAT (`Copilot: Read` スコープ)
- `.claude/skills/<name>/SKILL.md` が存在するか、PR で追加・修正される

## 保存場所

- **シナリオ**: `.claude/skills/<skill>/skill-eval/scenarios.json` — 検証対象の skill ディレクトリに co-locate
- **レポート**: `.skill-eval/reports/<skill>/*.md` — CI が書き戻す履歴 (リポジトリルート集約)

## 何ができないか (alpha 制限)

- シナリオの自動生成は意図的に行わない (`/skill-eval:create-test` のヒアリングが本旨)
- LLM-as-judge は確率的。同じ PR で何度実行しても同じ verdict にはならないことがある — ブロッキングではなく参考情報として運用すること
- Copilot Premium Quota を 1 PR あたり 20+ セッション消費する。組織で運用する際は実行頻度を制御すること

## できること (alpha-1 で対応済み)

- **発火検証** (`expectation: should_fire`) — skill が効くべき発話で実際に効いているか
- **暴発抑止検証** (`expectation: should_not_fire`) — 近接ケースで skill が誤発火しないか
- skill 改修の **A/B 効果比較** — base 版 vs head 版を匿名スコアリング

## ファイル構成

```
plugins/skill-eval/
├── .claude-plugin/plugin.json
├── README.md                       # このファイル
├── commands/
│   ├── setup.md                    # /skill-eval:setup
│   ├── create-test.md              # /skill-eval:create-test
│   └── edit-test.md                # /skill-eval:edit-test
├── scripts/
│   └── setup.mjs                   # 消費側へ vendor copy する Node スクリプト
└── templates/                      # /setup で展開される雛形
    ├── workflow.yml.template       # → .github/workflows/skill-eval.yml
    ├── scenario.schema.json        # シナリオ JSON Schema
    ├── README.template.md          # → .skill-eval/README.md
    └── runner/                     # → skill-eval-scripts/
        ├── requirements.txt
        ├── skill_eval.py           # オーケストレーター
        ├── copilot_runner.py       # SDK ラッパー
        ├── load_scenarios.py       # scenarios/<skill>.json ローダー
        ├── pr_data.py              # PR diff から SKILL.md を取得
        ├── persist_report.py       # レポート永続化 + index.md 再構築
        ├── agents/
        │   ├── implementer.py      # A/B run via skill_directories
        │   ├── evaluator.py        # 4軸ルーブリック匿名スコア
        │   └── reporter.py         # 決定的集計 + verdict
        └── prompts/
            └── evaluator.md
```
