# Examples

[Back to docs index](README.md)

Verified, runnable examples using a sample `.fountain` screenplay (`diner_v1.fountain`).

## Sample Input (`diner_v1.fountain`)

```fountain
Title: Diner
Author: Jane Doe

INT. DINER - NIGHT

Rain taps the window.

ALICE
(quietly)
Did you bring the drive?

BOB ^
Right here.
```

## 1. Export to Streaming JSONL

```bash
rtfs parse diner_v1.fountain --format jsonl
```

Output:

```json
{"title": "Diner", "source": "local", "scene_number": 1, "heading": "INT. DINER - NIGHT", "element_index": 0, "type": "action", "text": "Rain taps the window."}
{"title": "Diner", "source": "local", "scene_number": 1, "heading": "INT. DINER - NIGHT", "element_index": 1, "type": "dialogue", "character": "ALICE", "parenthetical": "quietly", "text": "Did you bring the drive?", "dual": false}
{"title": "Diner", "source": "local", "scene_number": 1, "heading": "INT. DINER - NIGHT", "element_index": 2, "type": "dialogue", "character": "BOB", "parenthetical": null, "text": "Right here.", "dual": true}
```

## 2. Convert Fountain to Final Draft (`.fdx`)

```bash
rtfs parse diner_v1.fountain --format fdx
```

Output (abbreviated):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<FinalDraft DocumentType="Script" Template="No" Version="5">
  <TitlePage>
    <Content>
      <Paragraph Alignment="Center" Type="Title">
        <Text>Diner</Text>
      </Paragraph>
      <Paragraph Alignment="Center">
        <Text>Written by</Text>
      </Paragraph>
      <Paragraph Alignment="Center" Type="Writer">
        <Text>Jane Doe</Text>
      </Paragraph>
    </Content>
  </TitlePage>
  <Content>
    <Paragraph Type="Scene Heading">
      <Text>INT. DINER - NIGHT</Text>
    </Paragraph>
    ...
```

## 3. Compare Two Drafts (`rtfs diff`)

```bash
rtfs diff diner_v1.fountain diner_v2.fountain
```

Output:

```diff
--- Diner
+++ Diner
@@ -1,3 +1,3 @@
 INT. DINER - NIGHT
-ALICE: Did you bring the drive?
+ALICE: Did you bring the encrypted drive?
 BOB: Right here.
```
