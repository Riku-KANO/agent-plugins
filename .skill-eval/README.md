# skill-eval — consumer-side guide

> このディレクトリは `/skill-eval:setup` によって生成されました。

`.claude/skills/<name>/SKILL.md` の効果を CI 上で A/B 検証するための仕組みです。GitHub Copilot SDK を使って、PR の head 版 (treatment) と base 版 (control) を同じシナリオで実行し、4軸ルーブリックで匿名スコアリングします。

## ディレクトリ構成

```
.claude/skills/<skill>/
├── SKILL.md                            # 検証対象
└── skill-eval/
    └── scenarios.json                  # この skill のテストシナリオ (co-located)

.skill-eval/
├── README.md                           # このファイル
├── .version                            # インストール済みプラグイン版数 (自動管理)
├── scenario.schema.json                # scenarios.json の JSON スキーマ
├── scripts/                            # Python ランナー (CI が実行)
└── reports/<skill>/*.md                # CI が書き戻すレポート

.github/workflows/skill-eval.yml
```

## プラグインのアップグレード

新しいバージョンの skill-eval をインストールしたら、消費側リポジトリでも `/skill-eval:setup` を再実行してください。setup スクリプトは `.skill-eval/.version` で現在のインストール済みバージョンを記録しており、プラグイン側のバージョンと差分があれば「upgrade detected: 旧→新」と表示します。

```bash
/skill-eval:setup           # まず差分を検出 (上書きはせず exit 1)
# 出力に upgrade detected: 0.1.0-alpha.1 → 0.1.0-alpha.2 等が表示される
/skill-eval:setup --force   # 安全に移行
```

`--force` 時に消されるもの (= プラグイン管理の vendor ファイル):

- `.skill-eval/scripts/` 配下の Python ランナー (古いファイルが残らないよう完全に再生成)
- 旧バージョンのレガシーパス (例: 旧レイアウトの `skill-eval-scripts/`)
- `.skill-eval/{README.md, scenario.schema.json}` (テンプレートで再生成)
- `.github/workflows/skill-eval.yml` (テンプレートで再生成)

`--force` でも **消されない** もの (= ユーザーデータ):

- `.claude/skills/<skill>/skill-eval/scenarios.json` (シナリオ)
- `.skill-eval/reports/<skill>/*.md` (CI が蓄積したレポート履歴)

シナリオは検証対象の skill 自身のディレクトリに `skill-eval/scenarios.json` として置きます。skill 改修と同じ PR でシナリオも修正でき、レビューしやすくなります。

## 初回セットアップ

### 1. シークレット追加 (必須)

GitHub > Settings > Secrets and variables > Actions > New repository secret:

| Name | Value |
|---|---|
| `COPILOT_GITHUB_TOKEN` | **fine-grained** PAT (`github_pat_...`)。Account permissions → `Copilot Requests` (Access/Read) |

### 重要な注意点

- **必ず fine-grained PAT** を使うこと。classic PAT (`ghp_...`) は silently 無視されて「Authorization error」を出します
- **Resource owner は個人アカウント** にすること。組織所有の fine-grained PAT には `Copilot Requests` パーミッションが表示されません ([copilot-cli#223](https://github.com/github/copilot-cli/issues/223))
- 権限名は **`Copilot Requests`** (Account permissions タブ)。「Copilot: Read」「Copilot Chat」等の似た名前のスコープは別物
- アクティブな Copilot subscription (Free / Pro / Business / Enterprise いずれか) が必要。`GITHUB_TOKEN` だけでは Copilot 推論を呼べません

トークン作成: https://github.com/settings/personal-access-tokens/new

参考: [Authenticating with Copilot SDK (GitHub Docs)](https://docs.github.com/en/copilot/how-tos/copilot-sdk/authenticate-copilot-sdk/authenticate-copilot-sdk)

### 2. シナリオ作成

`.claude/skills/<name>/SKILL.md` を持つリポジトリで Claude Code を開き、

```
/skill-eval:create-test
```

を実行。ヒアリング形式で 3〜5 シナリオを作成すると `.claude/skills/<name>/skill-eval/scenarios.json` が生成されます。

### シナリオの保守 (仕様変更時)

skill の仕様変更で期待挙動が変わったときは、

```
/skill-eval:edit-test
```

で既存シナリオを **修正 / 削除 / 追加 / 全点検** できます。`/skill-eval:create-test` は新規作成専用、`/skill-eval:edit-test` は既存シナリオの保守用、と使い分けます。

### 3. PR で起動

skill を変更する PR を作成し、PR コメントに `/skill-eval` と書くと CI が起動します (10分前後)。完了すると：

- PR コメントに **改善 ✅ / 退行 ❌ / 同等 ➖** の判定 + 4 軸スコアテーブルが投稿される
- `.skill-eval/reports/<skill>/` に詳細レポート (transcript 抜粋付き) が追加コミットされる

## モード別の挙動

| skill の変化 | mode | 評価 |
|---|---|---|
| 新規追加 | `addition` | treatment-only の絶対スコア (control なし) |
| 修正 | `modification` | A/B 比較 → 改善/退行/同等 判定 |
| 削除 | `removal` | base 版を treatment、head なしを control とした比較 |

## シナリオの `expectation`

各シナリオは `expectation` フィールドで「skill が発火すべきか」を明示します：

| `expectation` | 意味 | `success_criteria` の書き方 |
|---|---|---|
| `should_fire` | この発話で skill が発火・適用されるべき | skill が効いた応答が満たすべき性質を書く |
| `should_not_fire` | この発話で skill が発火してはいけない (近接ケース・暴発抑止) | skill 固有の見出し・用語・構造を**持たない**ことを書く |

評価モデルは `expectation` を読んで採点方向を切り替えます。**スコアは常に「高いほど良い (= expectation に沿っている)」** に統一されています。

## 4 軸ルーブリック (1〜5 整数, 全て higher = better)

- `success` — シナリオの `success_criteria` を満たしているか (`success_criteria` は ground truth として扱われる)
- `completeness` — ユーザー要求を漏らさずカバーできているか
- `skill_engagement` — `expectation` に沿った挙動か：
  - `should_fire` → skill が明確に効いていれば高
  - `should_not_fire` → skill が漏れずに通常応答していれば高
- `conciseness` — 適切に簡潔か

評価モデル (デフォルト `claude-sonnet-4.5`) は `run_1..run_N` の匿名 ID で transcript を受け取り、どれが treatment / control か知らずにスコアリングします。

## 判定ロジック (決定的)

- treatment 平均 vs control 平均の差分 Δ を全シナリオで計算
- `Δ ≥ +0.5` かつ全シナリオで treatment ≥ control → **改善 ✅**
- `Δ ≤ -0.5` → **退行 ❌**
- それ以外 → **同等 ➖**

ペアごとの勝敗カウント (3 treat × 3 ctrl = 9 ペア / シナリオ) も表示されます。

## コスト見積もり

- 1 skill につき **約 (シナリオ数 × samples_per_arm × 2 + 1) セッション** を消費
- 既定 (3 シナリオ × 3 samples × 2 arms + 1 evaluator-per-scenario) ≈ **21 セッション/skill**
- セッション = Copilot Premium Request 1〜数回相当。組織の weekly quota を圧迫するので注意

`/skill-eval --smoke` (将来追加予定) で `samples-per-arm 1` に絞り、約 7 セッション/skill に圧縮できます。

## トラブルシュート

| 症状 | 対処 |
|---|---|
| `user_weekly_rate_limited` | quota 復活待ち、または別アカウントの PAT に切り替え |
| `Commenter @... lacks write permission` | リポジトリの write 以上の権限が必要 |
| シナリオ未作成スキップ | `/skill-eval:create-test <skill>` で `.claude/skills/<skill>/skill-eval/scenarios.json` を作る |
| fork PR でレポートが追加されない | 仕様 (fork に push できないため、PR コメントのみ投稿) |
| 判定が毎回揺らぐ | LLM-as-judge は確率的。ブロッキングではなく参考情報として運用すること |

## 既知の制限

- **Copilot SDK は public preview** (v0.3.0)。SDK 破壊変更時は `.skill-eval/scripts/copilot_runner.py` の更新が必要
- **シナリオはユーザー作成**。skill 改修時にシナリオも更新しないと検証品質が落ちます
- 実装は alpha (`0.1.0-alpha.1`)。フィードバック・バグ報告は marketplace 元 (`personal-agents`) のリポジトリへ
