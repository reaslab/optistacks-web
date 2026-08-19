# ReasAtlas framework sync 20260819 v1.3

This snapshot addresses numbering, performance, and unsafe textbook-statement
placement.

- Outline chapter numbers are hidden; stable internal topic IDs remain intact.
- Statement cards render 24 records initially and expose additional records on
  demand.
- Public campaign statements are restricted to published exact existing-node
  placements and reviewed exact/preferred-home placements.
- 40,754 candidates that are builder-only, need an absent specific container,
  use an affected node as a proxy owner, or have no live target are retained in
  a quarantine ledger instead of being mounted to a misleading topic.

The public statement count falls from 118,750 to 93,941. This is a precision
correction, not source deletion. The quarantine ledger retains the source item,
campaign, stage, attempted target, placement hints, and exclusion reason.

Performance changes:

- generated site size falls from about 426 MiB to 338 MiB;
- chapter-shard payload totals 314.92 MiB;
- the largest shard falls from 7.68 MiB to 4.19 MiB;
- the largest direct statement list falls from 220 to 42, with only 24 rendered
  initially.
