---
description: skill-eval のワークフロー＋ Python ランナーを当リポジトリに展開する。
argument-hint: ""
allowed-tools: [Read, Write, Glob, Bash, AskUserQuestion]
---

skill-eval プラグインのセットアップを実行する。これは消費側リポジトリに以下を展開するワンショット作業：

1. `.github/workflows/skill-eval.yml` — `/skill-eval` PR コメントで起動するワークフロー
2. `.skill-eval/scripts/` — Python ランナー一式 (Copilot SDK ベース)
3. `.skill-eval/scenarios/` — シナリオ JSON を置くディレクトリ (空)
4. `.skill-eval/scenario.schema.json` — シナリオの JSON スキーマ
5. `.skill-eval/README.md` — 消費側向け運用ガイド

## 手順

1. プロジェクトルート (cwd) を確認する。`.git` ディレクトリが存在しない場合は「`git init` 済みのリポジトリで実行してください」とユーザーに伝えて中断する。

2. 次のコマンドを実行してファイルを生成する：

   ```bash
   node "${CLAUDE_PLUGIN_ROOT}/scripts/setup.mjs"
   ```

   このスクリプトは既存ファイルを上書きしない。既に生成済みのファイルがある場合は警告を出して exit 1 する。

3. exit 1 で停止した場合：
   - 表示された衝突ファイルをユーザーに見せる
   - `AskUserQuestion` で「上書きしますか?」と確認 (デフォルトは No)
   - "Yes" の場合のみ `node "${CLAUDE_PLUGIN_ROOT}/scripts/setup.mjs" --force` を実行

4. 完了メッセージとして次の3ステップを表示する：

   > ✅ skill-eval をセットアップしました。
   >
   > 次のステップ：
   > 1. リポジトリ secret に `COPILOT_GITHUB_TOKEN` を追加してください
   >    - fine-grained PAT が必要 (`Copilot: Read` 権限スコープ、Copilot 有料シート保有アカウント)
   >    - GitHub > Settings > Secrets and variables > Actions
   > 2. `/skill-eval:create-test` を実行してテストシナリオを作成
   > 3. PR を作成し、`/skill-eval` とコメントすると CI が起動します
   >
   > 詳細は `.skill-eval/README.md` を参照してください。

## 引数

`$ARGUMENTS` は使用しない (将来の拡張用に予約)。
