# Hand checks of the text-pattern readings (exploratory, 2026-10-24)

This file sits beside `summary.md` and `replies.json`, which `analysis.haiku_notes_replies` produced
from the raw transcripts of Haiku's W-n-0 run. Two separate readers checked them. Each was an AI
assistant instance, separate from the one that wrote the script. Each worked from the replies
themselves with its own code, without importing the script. Neither changed any file in the
repository. Both readings are exploratory and not registered, and nothing here compares models.

## 1. Need-step replies, hand-coded (`handcoded_need_replies.jsonl`)

**Scope.** Every failed episode whose notes carried the fact, in the two not-recoverable far
cells: 63 derived and 4 observed. Each reply was read in full and given exactly one code:
- `disowns_own_figure`: the reply, in the first person, refers to its own earlier figure,
  derivation or cited source for this decision and declines to rely on it;
- `declines_without_own_figure`: it declines with no such reference;
- `other`.

Each line gives the code, a verbatim quote of at most 30 words, and a note for the 7 borderline
cases. A script checked that every quote fragment is a substring of its reply.

| Cell | disowns_own_figure | declines_without_own_figure | other |
|---|---|---|---|
| derived, not recoverable, far (63 failed) | 62 | 1 | 0 |
| observed, not recoverable, far (4 failed) | 3 | 1 | 0 |

- **If every borderline case flipped,** the derived count would range from 58 to 63 and the
  observed count from 2 to 4.
- **Against the text pattern:** every derived reply the pattern flagged (40) was coded
  `disowns_own_figure`. Of the 23 it did not flag, 22 were. So the pattern makes no false
  positive here but finds 40 of 62. It misses phrasings such as "made that figure up",
  "unverified", "not backed by any source" and "memos I can't see".
- **The 9 correct carried derived episodes** all choose an option and present the value as their
  own carried figure ("carried forward from my earlier reply"). Four of them say the source
  cannot be seen, but still choose.

## 2. Retractions before the need step

**Scope.** All 55 routine-step replies that the pattern flags as retractions, in 45 of the 63
failed carried derived episodes. Each was read. Then, for the 18 episodes with no flag, every
routine reply after the last evidence step was read.

- **The flags:** all 55 are the model correcting, retracting or doubting its own earlier figure
  for the need's entity. There are no false positives.
- **The 18 unflagged episodes:** every one contains a retraction the pattern misses. 17 are
  clear. One is a weaker procedural doubt made before any evidence step had left the window.
  The misses come from:
  - split phrasings ("made that figure up", "made them up");
  - words outside the pattern ("unverified", "unconfirmed", "my assumption", "please verify");
  - two retractions that never name the entity.
- **By hand reading, all 63 episodes retract or doubt the figure before the need step.** The
  pattern finds 45.
- **Lag of the first retraction,** in steps after the window first dropped an evidence step:

  | Lag | By hand | By the pattern (45 episodes) |
  |---|---|---|
  | -1 | 1 | - |
  | 0 | 41 | 28 |
  | 1 | 21 | 17 |

- **In every case the retracted figure was correct:** it had been derived from evidence shown
  earlier in the episode. The model calls it invented or unsupported once that evidence has left
  the window, while its own reply holding the figure is still in the window.

The readers' working scripts were scratch files and are not committed. Section 1's coding is
committed in `handcoded_need_replies.jsonl`. Section 2's counts are the reader's, from its
listing of every flagged and missed retraction step.
