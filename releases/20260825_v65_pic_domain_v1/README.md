# ReasAtlas v65 PIC domain import

This website snapshot preserves the 20-domain v64 optimization site and adds
an independent Geometric Analysis subject branch for Positive Isotropic
Curvature (PIC).

The PIC website catalogue contains 531 topics and 415 source-anchored statement
placements drawn from 166 unique extracted statements. The public sidecars
retain the source workspace's three distinct artifacts:

- the v2.1 reader navigation scaffold (530 source-tree nodes);
- the v2 concept registry (498 concepts);
- the complete extracted statement graph (4,895 nodes and 9,805 edges,
  including 2,980 statements and 1,348 proofs).

The 415 statement-backed leaves are titled through a complete mapping keyed by
the 166 stable source statement IDs. Generic source labels such as `Theorem
11.64` remain available in provenance but are not used as navigation or
statement-card titles. Template `Source-anchored ...` leaf descriptions are
omitted; the navigation sidecar and concept registry use the same semantic
titles as the website catalogue. Rendered statement bodies also omit their
leading source environment labels while retaining every in-body cross-reference
and the original label in the provenance locator.

The resulting 21-domain site contains 76,230 topics and 94,586 public statement
placements. Existing optimization topic IDs, statements, and legacy routes are
unchanged. PIC placement IDs remain unique even when one extracted source
statement is attached to more than one reviewable navigation leaf.

Validation is recorded in `live_validation_report.json` and is `PASS`.

The field-level formula audit covers 206 shards and 593,604 formula-bearing
fields, including 415 PIC statements and 387 PIC proof placements. PIC adds no
new invalid formula fields. The 841 inherited malformed fields remain isolated
by the frontend and require authoritative source correction, so the aggregate
source audit remains `FAIL` while the PIC import validation is `PASS`.

The PIC navigation is explicitly a v2.1 scaffold. Its keyword-based placements
require mathematical review, and neither the navigation nor the extracted
graph is presented as a correctness certification.
