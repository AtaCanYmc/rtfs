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

## 4. Print `ScriptDocument` JSON Schema (`rtfs schema`)

```bash
rtfs schema
```

Output (abbreviated):

```json
{
  "$defs": {
    "Action": {
      "properties": {
        "type": {
          "const": "action",
          "default": "action",
          "title": "Type",
          "type": "string"
        },
        "text": {
          "title": "Text",
          "type": "string"
        }
      },
      "required": ["text"],
      "title": "Action",
      "type": "object"
    }
  }
}
```

## 5. Character-Normalized Analytics (Python SDK)

`compute_stats()` automatically merges character aliases such as `ALICE`, `ALICE (V.O.)`, and `ALICE (CONT'D)`:

```python
from rtfs.core.models import Dialogue, Scene, ScriptDocument, ScriptMetadata
from rtfs.exporters.stats_exp import compute_stats

doc = ScriptDocument(
    metadata=ScriptMetadata(title="Diner", source="local", url="file://diner.fountain"),
    scenes=[
        Scene(
            scene_number=1,
            heading="INT. DINER - NIGHT",
            elements=[
                Dialogue(character="ALICE", lines="Did you bring the drive?"),
                Dialogue(character="ALICE (V.O.)", lines="She knew he had it."),
                Dialogue(character="ALICE (CONT'D)", lines="Put it on the table."),
                Dialogue(character="BOB ^", lines="Right here."),
            ],
        )
    ],
)

stats = compute_stats(doc)
for c in stats.top_characters:
    print(c.character, c.dialogue_turns, c.word_count)
```

Output:

```text
ALICE 3 15
BOB 1 2
```

## 6. Live Multi-Provider Search (`rtfs search`)

```bash
rtfs search "Interstellar"
```

Output (abbreviated):

```text
                         Search Results: 'Interstellar'
┏━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━┓
┃ Index ┃ Title                      ┃ Type  ┃ Source     ┃ Format     ┃ Score ┃
┡━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━┩
│     1 │ Interstellar (2014)        │ movie │ scriptslug │ screenplay │ 112.0 │
│     2 │ Interstellar               │ movie │ imsdb      │ screenplay │ 107.0 │
│     3 │ ER                         │ tv    │ tvwriting  │ screenplay │ 102.0 │
│     4 │ The Interpreter (2005)     │ movie │ scriptslug │ screenplay │  81.6 │
│     5 │ Winters Tale (2014)        │ movie │ scriptslug │ screenplay │  78.7 │
└───────┴────────────────────────────┴───────┴────────────┴────────────┴───────┘
```

## 7. Live Script Analytics (`rtfs stats`)

```bash
rtfs stats "The Matrix"
```

Output:

```text
Script Overview: The Matrix (scriptslug)
┏━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━┓
┃ Metric                  ┃      Value ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━┩
│ Format                  │ screenplay │
│ Total Scenes            │        225 │
│ INT. Scenes             │        180 │
│ EXT. Scenes             │         44 │
│ INT / EXT Ratio         │       4.09 │
│ Dialogue Words          │      15872 │
│ Action Words            │       6202 │
│ Dialogue / Action Ratio │       2.56 │
└─────────────────────────┴────────────┘
            Top Speaking Characters
┏━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━┓
┃ Rank ┃ Character   ┃ Dialogue Turns ┃ Words ┃
┡━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━┩
│    1 │ NEO         │            219 │  3083 │
│    2 │ MORPHEUS    │            181 │  4482 │
│    3 │ TRINITY     │            133 │  1698 │
│    4 │ TANK        │             70 │   949 │
│    5 │ AGENT SMITH │             68 │  1612 │
│    6 │ CYPHER      │             66 │  1471 │
│    7 │ ORACLE      │             23 │   461 │
│    8 │ MOUSE       │             16 │   264 │
│    9 │ APOC        │             13 │   113 │
│   10 │ SWITCH      │             12 │   106 │
└──────┴─────────────┴────────────────┴───────┘
```

## 8. Live Filtered Fetch (`rtfs get --character --scene-range --format fountain`)

Matches `MORPHEUS` including parenthetical variants such as `MORPHEUS (V.O.)`:

```bash
rtfs get "The Matrix" --character "MORPHEUS" --scene-range "1-40" --format fountain
```

Output (abbreviated):

```fountain
Title: The Matrix
Source: scriptslug
Draft date: 1999

INT. HEART O' THE CITY HOTEL

Trinity is on the phone, pacing. The other end is answered.

MAN (V.O.)
Operator.
...
TRINITY
Are there any Agents?

MORPHEUS (V.O.)
Yes.
```

## 9. Live Streaming JSONL Export (`rtfs get --format jsonl`)

```bash
rtfs get "The Matrix" --scene-range "1-2" --format jsonl
```

Output (first 4 records):

```json
{"title": "The Matrix", "source": "scriptslug", "scene_number": 1, "heading": "PROLOGUE", "element_index": 0, "type": "action", "text": "by Larry and Andy Wachowski"}
{"title": "The Matrix", "source": "scriptslug", "scene_number": 1, "heading": "PROLOGUE", "element_index": 1, "type": "transition", "text": "NUMBERED SHOOTING SCRIPT"}
{"title": "The Matrix", "source": "scriptslug", "scene_number": 1, "heading": "PROLOGUE", "element_index": 2, "type": "action", "text": "March 29, 1998"}
{"title": "The Matrix", "source": "scriptslug", "scene_number": 1, "heading": "PROLOGUE", "element_index": 3, "type": "transition", "text": "FADE IN:"}
```
