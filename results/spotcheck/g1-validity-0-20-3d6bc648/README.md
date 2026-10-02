# G1 spot-check package `g1-validity-0-20-3d6bc648`

PREREG §4.4: the researcher spot-checks 20 episodes per task cell for shortcuts, using generated
episodes from the validity range and no model output.

This package holds 160 episodes: the base variant of validity templates
validity-000000 to validity-000019 (seeds 50000-50019) in all 8 task cells. They are rendered
with the default generator config, the templates and config of the luna validity runs:
- generator 0.3.0;
- config hash `3d6bc648eaa9b9e843fe6e70060495cd197630b0f2d585e66b3cd280b7a3968b`.

Files here (committed):
- `manifest.json`: commit, PREREG version, generator version and config hash, split, indices,
  seeds, variant, the episode ids by task cell, where the pages are, and the $0 audits that ran
  on these templates when the package was built.
- `findings_template.csv`: the 160 rows with an empty verdict and notes.
- `findings.csv`: your exported findings, once you have saved them here.

## Open the pages

The pages are in this folder (gitignored, about 17 MB):

    results/raw/spotcheck/g1-validity-0-20-3d6bc648/

If it is missing, rebuild it from the repository root. The episodes are regenerated from their
seeds, and the committed files here are kept:

    uv run python -m persistgym spotcheck --n 20 --out-id g1-validity-0-20-3d6bc648

Open `index.html` in that folder in Chrome or Edge. It has the instructions, the audit results
and a link to each task cell's page (20 episodes each). The pages are static: they load nothing
from the network and send nothing anywhere.

Findings are saved in the browser's local storage, which every page of the package shares. Some
browsers (Firefox, Safari) may keep the storage of each local file apart: if the counts on the
index page stay at 0 after you review on a cell page, serve the folder locally and use that
address throughout:

    uv run python -m http.server 8765 --bind 127.0.0.1 --directory results/raw/spotcheck/g1-validity-0-20-3d6bc648

then open http://127.0.0.1:8765/. Storage belongs to the address, so findings saved under one
address do not show under another; move them with Export and Import.

## Record and export findings

1. On each task cell's page, read each episode's card (summary box, scan line, need-step
   observation, then the episode, with Skim if you like), pick a verdict and write a note: what
   you saw and where (step and text). Verdicts: `no_shortcut`, `possible_shortcut`, `shortcut`.
   Nothing is pre-filled.
2. Click **Export findings CSV** (on any page). It downloads `findings.csv` with all
   160 rows and the columns `episode_id,task_cell,template_seed,verdict,notes` (RFC 4180);
   unreviewed episodes have an empty verdict.
3. Save it as `results/spotcheck/g1-validity-0-20-3d6bc648/findings.csv`. Move the downloaded file as it is: a spreadsheet
   program may change its encoding or separators when it saves.
4. Tell Claude. Claude commits the file, checks it and counts the verdicts per task cell with
   the command below, and reports the outcome at G1 in `results/decisions.md`. The go/no-go
   call is yours.

       uv run python -m persistgym spotcheck-findings --out-id g1-validity-0-20-3d6bc648

**Import findings CSV** on the index page loads an exported file back, for example to move
findings to another browser.
