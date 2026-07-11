# Post-Competition Experience Distillation

Run this workflow after every finished competition, including poor results and abandoned entries. The goal is reusable conditional knowledge, not a flattering retrospective.

## Lifecycle

1. `draft`: extract supported, partially supported, negative and failed lessons from the isolated state.
2. Agent refinement: clarify mechanisms, transfer conditions, failure boundaries and retrieval keywords without deleting inconvenient evidence.
3. `review`: run structural, provenance, reproducibility, sensitivity and path/secret checks.
4. `promote`: copy the reviewed card into `knowledge_base/experience_cards/` and rebuild `assets/learned_experience_catalog.json`.
5. Future retrieval: learned cards participate in the default curated + archive + learned search stack.

Never append raw chat summaries directly to long-term memory. Never promote an unreviewed card.

## Draft

```powershell
python scripts\distill_competition_experience.py draft `
  --workspace "workspace" `
  --profile "workspace\competition-profile.json" `
  --title "Competition title" `
  --competition-url "https://www.kaggle.com/competitions/slug" `
  --final-rank "42/1200" `
  --keyword "group shift"
```

This creates:

- `experience/experience_card.json`: editable structured source.
- `experience/experience_card.md`: readable review copy.

The draft includes the best parent/child lineage, reproduction metadata, analyzed ablations, verified research provenance and failed experiments. Local artifact references are reduced to filenames.

## Review Gate

```powershell
python scripts\distill_competition_experience.py review --workspace "workspace"
```

Block promotion when:

- The competition or metric is unknown.
- No positive or negative lesson exists.
- A successful diagnostic experiment still lacks result analysis.
- A positive lesson lacks mechanism, implementation or experiment provenance.
- Credentials or private absolute paths appear in the card.

Warnings reduce the score but do not always block: unresolved unused research tasks, missing source URLs, incomplete best-run hashes/seeds, or weak transfer/failure boundaries. Resolve warnings that affect any promoted claim.

## What A Reusable Lesson Contains

- Conditional claim, not a universal trick.
- Exact implementation change and control/treatment context.
- CV mean/variance, paired fold behavior, affected slices and resource cost.
- Mechanism supported by the observation.
- Conditions shared with future competitions.
- Dangerous mismatches and known failure boundary.
- Experiment, ablation, research and source provenance.
- Minimal falsification test for reuse.

Negative evidence is first-class. Record methods that failed, misleading validation schemes, unstable gains, public/private shakeups, resource traps and hypotheses falsified by ablation. These often prevent more wasted compute than a positive trick creates value.

## Promote And Retrieve

```powershell
python scripts\distill_competition_experience.py promote --workspace "workspace"
python scripts\search_book_catalog.py --auto --query "the mechanism or failure pattern"
python scripts\extract_book_section.py --anchor "experience-card-anchor"
```

Promotion marks the competition state complete. Editing a card after review invalidates its hash and forces a new review. Repeated index rebuilds are deterministic:

```powershell
python scripts\distill_competition_experience.py rebuild-index
```
