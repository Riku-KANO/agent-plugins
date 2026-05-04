---
description: 既存のテストシナリオを対話で修正・削除・追加・全点検する。仕様変更時に使用。
argument-hint: "[skill-name]"
allowed-tools: [Read, Write, Edit, Glob, Grep, AskUserQuestion]
---

既存の `.claude/skills/<skill>/skill-eval/scenarios.json` を対話で保守する。skill の仕様変更や挙動の見直しに伴いシナリオを **修正 / 削除 / 追加 / 全点検** したいときに使う。

新規作成は `/skill-eval:create-test` を使うこと (このコマンドは「既にシナリオが存在する状態」を前提とする)。

初期引数 (任意・空のこともある): "$ARGUMENTS"

## 基本原則
- これは**対話**。シナリオの「意味」が変わる修正は必ず `success_criteria` の整合性も同時に確認する。
- 1ターンに1〜2問。8個並べない。
- 質問前に SKILL.md と scenarios.json を Read して現状把握する (skill の現状と既存シナリオが整合しているかを判定するため)。
- 変更履歴は git に任せる (このコマンドは diff 表示や revert は持たない)。
- ユーザーの言語に合わせる。

## Phase 1 — 対象 skill の確定

- **`$ARGUMENTS` 空**: `.claude/skills/*/skill-eval/scenarios.json` を Glob で列挙。シナリオファイルが 0 件なら「`/skill-eval:create-test` で先に作成してください」と伝えて終了。1件以上なら `AskUserQuestion` で対象を選ばせる。
- **指定あり**: 該当 `scenarios.json` を Read。存在しなければ「`/skill-eval:create-test` で作成してください」と伝えて中断。

同時に `.claude/skills/<skill>/SKILL.md` も Read して skill の **現在の** 挙動を把握する。シナリオ作成当時から skill が大きく変わっていれば、Phase 2 でユーザーに警告する。

## Phase 2 — 概観の提示

以下を簡潔に提示する：

1. **現在の skill の description** (frontmatter から1行要約)
2. **既存シナリオ一覧** (テーブル形式):

| ID | archetype | expectation | 発話 (40字) | success_criteria (要約) |
|---|---|---|---|---|

3. (任意) skill が大幅改修されたと判断できる場合は注意を促す:
   > ⚠️ skill description が「<旧>」から「<新>」に変わっています。シナリオの user_prompt や success_criteria が古くなっている可能性があります。「全シナリオを再点検」を推奨します。

4. **何をしたいか** を `AskUserQuestion` で聞く:
   - **特定シナリオを修正** (1件の id を指定)
   - **特定シナリオを削除** (1件の id を指定)
   - **新規シナリオを追加** (`/skill-eval:create-test` の Phase 2 相当)
   - **全シナリオを順に再点検** (skill 大幅改修後向け)
   - **終了**

## Phase 3 — 操作の実行

### A. 修正 (modify)

1. `AskUserQuestion` でどの id を修正するか聞く (既存 id 一覧から選択)
2. 該当シナリオの **全フィールド** を整形して表示
3. どのフィールドを変更するか聞く:
   - `archetype` / `expectation` / `user_prompt` / `success_criteria` / `skill_relevance`
   - (`id` は変更不可。リネーム相当が必要なら削除→追加で対応)
4. フィールドごとの対話:
   - **`archetype`**: direct / adjacent / subtle から選ばせる
   - **`expectation`**: should_fire / should_not_fire から選ばせる。
     **⚠️ 変更時は警告する**: 「expectation を反転すると `success_criteria` の書き方も反転します (発火すべき条件 ↔ 発火していない条件)。続けて success_criteria も見直しますか?」と聞き、Yes なら直後に success_criteria 編集に入る
   - **`user_prompt`**: 新しい発話を verbatim で受け取る
   - **`success_criteria`**: 既存を箇条書きで表示し、項目ごとに 「維持 / 書き換え / 削除」 を聞く。最後に「追加する項目はありますか?」と聞く。`expectation` と整合する書き方になっているかを毎回確認 (should_fire なら「skill が効いた応答が満たすべき性質」、should_not_fire なら「skill が**漏れていない**通常応答が満たすべき性質」)
   - **`skill_relevance`**: 1文で書き直し
5. 全変更を要約して提示し、`AskUserQuestion` で確定するか聞く
6. 確定なら `scenarios.json` を Edit で更新

### B. 削除 (delete)

1. `AskUserQuestion` でどの id を削除するか聞く
2. 該当シナリオの user_prompt と success_criteria を表示し、`AskUserQuestion` で「本当に削除しますか?」と最終確認
3. 確定なら `scenarios` 配列から除去
4. **残りの id は採番し直さない** (id の安定性を優先 — git history・レポート過去ログとの突き合わせのため)

### C. 追加 (add)

`/skill-eval:create-test` の Phase 2 (中核ヒアリング) と同じ流れを実施する：

1. シナリオの観点を 1 件ずつ深掘り (用途 / 発話例 / 期待挙動 / success_criteria)
2. 既存 id を避けて連番採番 (`s1`〜`sN` が埋まっていれば `s<N+1>`)
3. expectation を聞き、それに沿って success_criteria の書き方を案内する
4. 確定後 `scenarios` 配列に append

### D. 全シナリオの再点検 (review-all)

skill が大幅改修された後に向く一括点検モード：

1. 各シナリオを 1 件ずつ順に表示。各シナリオで `AskUserQuestion` の 4 択：
   - **このまま維持** (次へ)
   - **修正する** → A. 修正フローへ
   - **削除する** → B. 削除フローへ
   - **あとで考える (スキップ)** (この回では触らない)
2. 全件処理が終わったら「**新規シナリオを追加しますか?**」と聞く。Yes なら C. 追加フローへ (連続追加可)
3. 全操作完了後にまとめて `scenarios.json` に Write

## Phase 4 — 保存と継続確認

各操作の最後に必ず `scenarios.json` を Write する。Write 後は「他に修正・追加はありますか?」と聞き、Yes なら Phase 2 へ戻る、No なら Phase 5 へ。

## Phase 5 — 完了案内

変更した id の一覧を分類して表示する：

```
✅ 変更内容
- modified: s1, s3
- deleted: s2
- added: s4, s5
```

次の手を提案：

> 次のステップ:
> - 変更を `git commit` して PR を作成し、PR コメントで `/skill-eval` を実行すると CI が走ります
> - skill 自体の修正と同じ PR にまとめると、A/B 比較が「skill 改訂 + 新シナリオ」の組み合わせで評価されます (シナリオだけ変えた場合は treatment/control に同じ skill が入るので Δ ≈ 0 になることに注意)

## やってはいけないこと

- ユーザーに確認せず `scenarios.json` を更新する (削除・修正は最終確認必須)
- 一度に複数シナリオの修正提案を並列で出す (混乱の元、1件ずつ深掘り)
- `expectation` を反転したのに `success_criteria` を見直さないまま保存する
- `id` を勝手に振り直す (`s2` を消した後に `s3 → s2` のリネームをしない)
- 削除を確認なしで実行する
- スキル本体 (SKILL.md) を読まずに「シナリオが古い」と判断する
- 全点検モードで「スキップ」を選ばれた件を勝手に削除する
