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

   このスクリプトは既存ファイルを上書きしない。既に生成済みのファイル、または旧バージョンのレガシーパス (例: 旧レイアウトの `skill-eval-scripts/`) を検出した場合は警告を出して exit 1 する。

3. exit 1 で停止した場合：
   - 出力に **「upgrade detected: <旧>→<新>」** が含まれていれば、これはプラグイン更新による移行ケース。`--force` で安全に再展開すべき (古いランナーを掃除して新しいファイル一式を入れる) 旨をユーザーに伝える
   - そうでない (初回設定で既存ファイルがある) 場合も `--force` で上書きする選択肢を提示
   - `AskUserQuestion` で「`--force` で再生成しますか?」と確認 (デフォルトは No)
   - "Yes" の場合のみ `node "${CLAUDE_PLUGIN_ROOT}/scripts/setup.mjs" --force` を実行
   - **重要**: ユーザーが書いたデータ (`.claude/skills/<skill>/skill-eval/scenarios.json`, `.skill-eval/reports/`) は `--force` でも消されない旨をユーザーに伝えて安心させる

4. 完了メッセージとして次の3ステップを表示する：

   > ✅ skill-eval をセットアップしました。
   >
   > 次のステップ：
   > 1. リポジトリ secret に `COPILOT_GITHUB_TOKEN` を追加してください
   >    - **fine-grained PAT** (`github_pat_` 始まり) が必要。classic PAT (`ghp_`) は silently 無視されます
   >    - Resource owner: **個人アカウント** (組織所有 NG — `Copilot Requests` パーミッションが選べない)
   >    - Account permissions → **`Copilot Requests`** (= Access/Read)
   >    - アクティブな Copilot subscription (Free / Pro / Business / Enterprise いずれか) が必要
   >    - 作成: https://github.com/settings/personal-access-tokens/new
   >    - secret 設定: GitHub > Settings > Secrets and variables > Actions
   > 2. `/skill-eval:create-test` を実行してテストシナリオを作成
   > 3. PR を作成し、`/skill-eval` とコメントすると CI が起動します
   >
   > 詳細は `.skill-eval/README.md` を参照してください。

## 引数

`$ARGUMENTS` は使用しない (将来の拡張用に予約)。
