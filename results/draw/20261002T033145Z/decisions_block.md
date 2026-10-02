## 2026-10-02: ARC game draw (D15, D17, D18, D32)
- **Freeze commit:** `ed340a1cda91153dafe78772861c40343b53dafa` ("Merge pull request #4 from raimondasl/m0/prereg-draft"), PREREG.md Version 1.0, status "Frozen on 2026-10-01 by Raimondas Lencevicius (sign-off in PR #4).". Committer time 2026-10-01T23:20:28-04:00; T = committer time + 10 min = 2026-10-02T03:30:28.000Z.
- **Seed source:** NIST Randomness Beacon 2.0 pulse https://beacon.nist.gov/beacon/2.0/chain/2/pulse/1966405 (timeStamp 2026-10-02T03:31:00.000Z, statusCode 0), fetched from https://beacon.nist.gov/beacon/2.0/pulse/time/1790911828000; the preceding pulse is before T. `outputValue[:16]` = `38B7BD1E97A12D5E`, so SEED = 4086943125952605534.
- **Permutation:** `random.Random(SEED).sample(['FT09', 'SB26', 'R11L', 'CD82'], 4)` = R11L, SB26, FT09, CD82 (Python 3.12.13). The recorded output is authoritative.
- **Truncated-pilot game (D17):** perm[0] = R11L. **Dropped under the 3-game fallback (D32):** perm[3] = CD82.
- **Block 2 order (D18, SEED + 2):** 1. CD82 S4 r1, 2. FT09 S0 r1, 3. SB26 S4 r1, 4. SB26 S0 r1, 5. CD82 S0 r1, 6. R11L S0 r1, 7. R11L S4 r1, 8. FT09 S4 r1.
- **Block 3 order (D18, SEED + 3):** 1. SB26 S1 r1, 2. R11L S2 r2, 3. FT09 S2 r1, 4. FT09 S1 r1, 5. SB26 S1 r2, 6. R11L S2 r1, 7. SB26 S2 r1, 8. FT09 S1 r2, 9. SB26 S0 r2, 10. CD82 S2 r2, 11. CD82 S1 r2, 12. CD82 S4 r2, 13. FT09 S4 r2, 14. SB26 S4 r2, 15. R11L S4 r2, 16. FT09 S0 r2, 17. CD82 S1 r1, 18. FT09 S2 r2, 19. CD82 S2 r1, 20. CD82 S0 r2, 21. R11L S1 r1, 22. SB26 S2 r2, 23. R11L S0 r2, 24. R11L S1 r2.
- **Output:** `results/draw/20261002T033145Z/` from `arc/draw_games.py` at commit `ed340a1cda91153dafe78772861c40343b53dafa`, drawn 2026-10-02T03:31:45.183Z.
- **Spend:** $0 (no paid calls).
