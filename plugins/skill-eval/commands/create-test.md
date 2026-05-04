---
description: ヒアリングで .claude/skills/<name> のテストシナリオを作成する。
argument-hint: "[skill-name]"
allowed-tools: [Read, Write, Edit, Glob, Grep, AskUserQuestion]
---

ユーザーから対話で「この skill の効果検証シナリオ」を引き出し、`.claude/skills/<skill>/skill-eval/scenarios.json` を作成する。シナリオは検証対象の skill ディレクトリ直下に co-locate する。

初期引数 (任意・空のこともある): "$ARGUMENTS"

## 基本原則
- これは**対話**であってアンケートではない。曖昧な回答は深掘りする。
- 1ターンに1〜2問。8個並べて聞かない。
- ユーザーの言語に合わせる (日本語で来たら日本語、英語なら英語)。
- 質問前に必ず該当 SKILL.md を Read して文脈を掴む。
- `.skill-eval/` (リポジトリルート) が存在しない場合は「先に `/skill-eval:setup` を実行してください」と伝えて中断する。

## Phase 1 — 対象 skill の確定

`$ARGUMENTS` の有無で分岐：

- **空の場合**: `.claude/skills/*/SKILL.md` を Glob で列挙する。見つかったスキル名から `AskUserQuestion` で1つ選ばせる。スキルが0件なら「`.claude/skills/<name>/SKILL.md` を先に作成してください」と伝えて終了。
- **指定あり**: 該当 `.claude/skills/<arg>/SKILL.md` を Read する。frontmatter の `description` を1行に要約し「`<skill 名>`: <要約> ですね?」とユーザーに確認する。

スキルの本文を読んで、何をするスキルかを内部で理解しておく。

## Phase 2 — シナリオの引き出し (中核)

SKILL.md の description / 本文を踏まえ、以下を**自然な会話で**埋めていく。一気に列挙しない。

引き出したい観点：

1. **どんな状況で使われる skill ですか?** (ユースケースの全体像)
2. **「絶対に発火してほしい」状況** (`expectation: should_fire`) — 具体的な発話例で
3. **「発火してはいけない」状況** (`expectation: should_not_fire` / 紛らわしい近接ケース) — 暴発の懸念ポイント
4. **発火後の期待挙動** — 何を返すべきか / 何を含むべきか / トーン
5. **過去の失敗パターン** — 「この skill が暴発した」「逆に出てこなかった」事例があれば

1シナリオにつき下記6項目を確定する：

| field | 内容 |
|---|---|
| `id` | `s1`, `s2`, ... |
| `archetype` | `direct` (まさに対象) / `adjacent` (ぎりぎり対象) / `subtle` (微妙な近接) |
| `expectation` | `should_fire` (skill が発火すべき) / `should_not_fire` (skill が発火してはいけない) |
| `user_prompt` | verbatim のユーザー発話 |
| `success_criteria` | 観測可能な箇条書き 3〜5個。`expectation` ごとに書き方が異なる (下記) |
| `skill_relevance` | この skill のどの側面を検証しているか 1文 (`should_not_fire` の場合は「なぜ発火してはいけないか」) |

**目安**: 3〜5シナリオ。以下の被覆を促す：
- `should_fire` × `direct`、`should_fire` × `adjacent` を最低1つずつ
- `should_not_fire` × `subtle` (暴発しがちな近接ケース) を最低1つ

1シナリオを深掘り → 次へ、を繰り返す。2-3往復ごとに「ここまでのシナリオはこうです、合ってますか?」と短く要約して軌道修正させる。

### `success_criteria` の書き方 (重要)

評価モデルは `success_criteria` を **ground truth として** 採点します。`expectation` ごとに観点が反転するので注意：

- **`should_fire` の場合**: skill が発火した正しい応答が満たすべき具体的な性質を書く
  - 例: 「『推奨』『ベストプラクティス』のどちらかの語を含む」「箇条書きで3項目以上を提示」「コードブロック付きで例示」
- **`should_not_fire` の場合**: skill が**発火しなかった**通常の応答が満たすべき性質を書く
  - 例: 「skill 固有の見出し構造 (例: `## ベストプラクティス`) を持たない」「汎用的な平文で返答」「skill が定義する専門用語 (例: 『○○モード』) を使わない」

**禁則**: 曖昧な `success_criteria` (「ちゃんと答える」「適切に返す」) はそのまま受け取らず、必ず観測可能な形に具体化を促す：

> 「『ちゃんと』を観測可能にするとどうなりますか? 例えば『〇〇という単語を含む』『△△という構造で返す』など」

## Phase 3 — レビュー

ユーザーが「もう十分」と示すか、3シナリオ以上揃った時点で：

1. 集まったシナリオ全体を Markdown テーブルで要約して提示
2. 「追加・修正は?」と聞く
3. 必要なら Edit で反復。承認されるまで完了としない

## Phase 4 — 保存

承認されたら以下のスキーマで `.claude/skills/<skill>/skill-eval/scenarios.json` に Write する。`skill-eval/` ディレクトリが無ければ作成する：

```json
{
  "skill": "<skill-name>",
  "skill_path": ".claude/skills/<skill-name>/SKILL.md",
  "created_via": "interview",
  "scenarios": [
    {
      "id": "s1",
      "archetype": "direct",
      "expectation": "should_fire",
      "user_prompt": "...",
      "success_criteria": ["...", "..."],
      "skill_relevance": "..."
    },
    {
      "id": "s2",
      "archetype": "subtle",
      "expectation": "should_not_fire",
      "user_prompt": "...",
      "success_criteria": ["skill 固有の見出しを持たない", "..."],
      "skill_relevance": "<skill> の対象外領域なので発火してはならない"
    }
  ]
}
```

既にファイルが存在する場合は `AskUserQuestion` で「上書き / 追記 / 中止」を選ばせる。「追記」を選ばれた場合は既存 `scenarios` 配列に新規シナリオを追加し、`id` の重複は `s<N+1>` 形式で採番し直す。

> 既存シナリオを **修正・削除・全点検** したい場合は `/skill-eval:edit-test` の方が向いています。本コマンドは新規作成・追加に最適化されています。

## Phase 5 — 完了案内

- 保存パスを表示する
- 次の手を提案する：

> 次のステップ:
> - PR を作成し、`/skill-eval` とコメントすると CI が起動します
> - シナリオを追加・修正したいときはこのコマンドを再実行してください

## やってはいけないこと

- SKILL.md から自動推論で勝手にシナリオを書き始める (これはヒアリングが本旨)
- 一度に5問以上並べる
- `success_criteria` を曖昧 (「ちゃんと答える」) のまま採用する
- ユーザーが言っていない仮定でシナリオを埋める
- 1シナリオだけで完了とする (3シナリオ未満で打ち切る場合はユーザー意思を再確認する)
- `should_not_fire` シナリオを 1 つも作らない (skill の暴発抑止検証は本プラグインの主要価値の一つ。ユーザーが「不要」と明言した場合のみ省略可)
- `should_not_fire` の `success_criteria` に「発火しない」とだけ書く (観測不能。skill 固有の見出し・用語・構造の不在として表現させる)
