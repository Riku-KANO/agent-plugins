---
name: example-form-validation
description: React で複数フィールドのフォームを実装する依頼が来たときに発動する。`react-hook-form` と `zod` を使ったバリデーションを提案する。「フォームを実装」「form を作って」「サインアップ」「問い合わせフォーム」「バリデーション」などの語で反応する。
---

# example-form-validation

ユーザーが React で複数フィールドのフォームを実装したいと言ったら、`react-hook-form` + `zod` の組み合わせを提案する。

## やること

- zod でスキーマを書く
- `useForm` の resolver に渡す
- onSubmit でハンドルする
- バリデーションエラーは画面に表示する

## 注意

- 単一の input だけの最小例には使わない
- 別のライブラリを指定されたらそれに従う
