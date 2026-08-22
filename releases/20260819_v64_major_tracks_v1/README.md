# ReasAtlas v64 major-track synchronization

This local website snapshot synchronizes
`opt_stacks_v64_extracted_major_tracks_candidate` from the OptiStacks directory.

The five extracted tracks are published as independent website domains, with
the original root node promoted directly and no same-title wrapper:

- A26 Manifold Optimization
- A25 Derivative-Free Optimization
- A27 Distributed Optimization
- A28 Robust Optimization
- A29 Simulation Optimization

The moved topic subtrees keep their original stable topic IDs. Existing A07 and
A16 routes redirect to the corresponding independent domain. Public statement
content is preserved in place: the snapshot contains 75,699 topics and 94,171
statements, with no statement duplication introduced by the structural move.

Validation is recorded in `live_validation_report.json` and is `PASS`.

Formula rendering compatibility is validated across all 20 domains. The
field-level source audit is recorded in `math_rendering_audit.json`; it reports
841 malformed source formula fields that are isolated by the frontend and
still require authoritative content correction.
