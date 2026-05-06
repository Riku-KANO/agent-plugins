---
name: example-form-validation
description: React で複数フィールドのフォームを実装する依頼が来たときに発動する。`react-hook-form` + `zod` で「スキーマ → 型推論 → useForm → onSubmit」の固定順テンプレートを提示する。「フォームを実装」「form を作って」「サインアップ」「問い合わせフォーム」「バリデーション」「複数の入力欄」などで反応するが、単一 input の最小例や別ライブラリ指定では発動しない。
---

# example-form-validation

ユーザーが React で複数フィールドのフォームを実装したいと言ったら、`react-hook-form` + `zod` の組み合わせを **以下の固定順** で提示する。

## 出力テンプレート

```tsx
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

// 1. スキーマ
const schema = z.object({
  email: z.string().email("メールアドレスの形式が正しくありません"),
  password: z.string().min(8, "8文字以上で入力してください"),
});

// 2. 型推論 — z.infer で導出 (手書きしない)
type FormValues = z.infer<typeof schema>;

// 3. コンポーネント
export function SignupForm() {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
  });

  // 4. onSubmit
  const onSubmit = async (values: FormValues) => {
    // …
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      <input {...register("email")} />
      {errors.email && <span>{errors.email.message}</span>}

      <input type="password" {...register("password")} />
      {errors.password && <span>{errors.password.message}</span>}

      <button type="submit" disabled={isSubmitting}>送信</button>
    </form>
  );
}
```

## ルール

1. **順序を守る**: スキーマ → `z.infer` で型 → `useForm<FormValues>` → `onSubmit` の順で提示する。
2. **`zodResolver` を必ず通す**: `useForm` 単体で `register` のオプション側に validation を書かない (スキーマ側で完結させる)。
3. **型は `z.infer` で導出**: `interface FormValues { ... }` のように手書きしない (スキーマと二重管理になる)。
4. **エラー表示**: `errors.<field>?.message` を該当 input の直下に置く。fieldset 末尾でまとめて出さない。
5. **`isSubmitting`** を submit ボタンの `disabled` に繋ぐ (二重送信防止)。
6. **エラーメッセージは zod 側に書く**: `z.string().email("メアドの形式が…")` のようにスキーマ第2引数で日本語化する (UI 側で if 分岐しない)。

## 暴発抑止

- 単一の `<input>` だけのスニペット要求や HTML だけのフォーム雛形では発動しない (例: 「`<input type="email" />` だけ見せて」)
- 「最小例で」「サンプルコードでいい」「ただの form タグでいい」と言われたら、ライブラリを持ち込まない
- ユーザーが別ライブラリ (`Formik`, `Final Form`, `TanStack Form` 等) を明示している場合は本 skill を発動させず、指定ライブラリで書く
- バックエンド/Server Actions 系の話題 (Next.js の `useFormState`, Server Action の `formData` ハンドリング等) では、本 skill のクライアント側テンプレートを押し付けない
- すでに `react-hook-form` + `zod` で書かれたコードへのレビュー/修正依頼では、テンプレートを丸ごと書き直さずフィードバックに留める
- バリデーション要件がない単純な input 1 個 ( = フォームと呼ぶには小さい) では発動しない

## 設計意図 (なぜこの構成か)

- `zod` でスキーマ・型・バリデーションを一元化 → サーバー側スキーマと共有しやすい
- `register` でなく `Controller` を最初から持ち出すと冗長になるため、まずは `register` ベースで提示する (custom component が必要になったときに `Controller` に切り替える)
- ペイロードの取り回しは `handleSubmit(onSubmit)` 一択 — 自前で `e.preventDefault()` から `FormData` を組むパターンは本 skill では出さない
