---
name: example-haiku
description: Use when the user asks for a haiku, a 5-7-5 poem, or wants a short 3-line poetic response on a given topic. Triggers on phrases like "write a haiku", "haiku about X", "5-7-5 poem", "短い詩で", "俳句を作って". Does NOT engage for factual questions, code help, or general prose.
version: 0.1.0
---

# example-haiku skill

Generate a haiku (5-7-5 syllable poem in 3 lines) on the topic the user requests.

## Output format

Always:

- Produce **exactly 3 lines**.
- Line 1: 5 syllables (5 morae for Japanese).
- Line 2: 7 syllables (7 morae for Japanese).
- Line 3: 5 syllables (5 morae for Japanese).
- **No preamble** ("Here's a haiku:") and **no postamble** ("I hope you enjoyed it!").
- Match the language of the user's request: English request → English haiku, Japanese request → Japanese haiku.
- Reflect the user's topic in **concrete imagery**, not abstract description.

## Examples

User: "Write a haiku about coffee."

You:

```
Steam curls from the cup
Bitter promise of morning
The day finally starts
```

User: "コーヒーで俳句を作って"

You:

```
湯気立つカップ
苦き約束朝の影
今日が始まる
```

## When NOT to engage

Do not produce a haiku for:

- Factual questions ("what is the boiling point of water?")
- Code help ("debug this function for me")
- Conversation that doesn't explicitly ask for a poem
- Prose summary or explanation requests

In those cases, respond normally without invoking the haiku format.
