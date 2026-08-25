You are the query author for a blind theorem-search benchmark. Read
`artifacts/rewrite_inputs.jsonl`, which contains exactly 200 mathematical
targets. For each target, write three English search queries and return exactly
one JSON object matching `schemas/rewrites.schema.json`.

The three query regimes are:

1. `short_query`: 5--12 whitespace-delimited words. It should name the central
   mathematical object and desired fact, definition, or procedure, while a
   realistic user may omit a secondary assumption.
2. `medium_query`: 18--35 words. It should preserve the important assumptions
   and desired conclusion or algorithmic operation as a natural search request.
3. `long_query`: 45--80 words. It should give realistic mathematical context,
   all load-bearing assumptions, and what the user wants to find. Added context
   must remain entailed by the input; do not invent applications, bounds,
   regularity assumptions, or algorithm steps.

Semantic and anti-leakage rules:

- Preserve the target's mathematical meaning. Variables may be renamed only
  consistently. Do not change quantifiers, inequality directions, convergence
  modes, domains, assumptions, outputs, or complexity rates.
- Phrase each item as a user's information need, not as an answer copied from
  the target. Do not begin with "Theorem", "Definition", "Algorithm", "Find
  the statement", or similar type labels.
- Do not mention ReasAtlas, a sample ID except in `sample_id`, a source/book,
  a domain label, a topic path, or any database metadata.
- Avoid copying four or more consecutive ordinary-language words from
  `statement_title` or `statement_plain`. Standard mathematical terms and
  displayed formulas may of course recur when they have no faithful synonym.
- For definitions, ask for the precise criterion or construction. For
  theorems, ask for the result under its assumptions. For algorithms, ask for
  the update rule/procedure and its required inputs or stopping condition.
- Every input sample ID must appear exactly once, in the same order. Do not add
  commentary outside the JSON object.

Before returning, silently check the word bounds and semantic consistency for
all 600 queries.
