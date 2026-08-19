# ReasAtlas framework sync 20260819 v1.4

This snapshot performs a first fast, evidence-constrained remount of textbook
statements that v1.3 had quarantined because their proposed specific container
did not yet exist.

- 17 proposed-topic groups match one existing direct child by normalized title.
- 50 new web candidate containers are materialized where at least two textbook
  campaigns independently propose the same normalized title under the same live
  parent.
- 62 additional groups have one unique title match inside the same Part and are
  routed to that existing topic.
- Cross-Part title matches, broad parent fallbacks, single affected-node hints,
  builder-only records, and unresolved records remain quarantined.

The pass handles 247 formerly quarantined candidates: 230 become public
statements and 17 duplicate titles are suppressed. The public snapshot now has
75,699 topics and 94,171 statements. The quarantine contains 40,507 records and
retains each record's proposed node, directory assessment, confidence, source,
and attempted placement.

This is a web candidate refinement only. It does not mutate the canonical v62
directory tree, and it does not claim that single-source proposed nodes have
been globally reconciled.
