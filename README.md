# ReasAtlas

ReasAtlas is a public, static browser for structured knowledge in optimization
and analysis. The live site is <https://atlas.reaslab.io/>.

The current `20260819_framework_sync_v1_4` snapshot contains all 15 Parts from
A02 through A16. The reviewed Distributed Optimization revision is installed
directly at A07.C03, replacing the older duplicate compatibility domain. It
contains 75,699 topic entries and 94,171 public statements, delivered through
lazy chapter shards. The data retains 115 convergence candidates: 74 from the
completed core pass and 41 from 12 validated shards of the broader pass. The
interface does not display review state.

The left rail has a major-domain selector above the existing subject-domain
list. Published optimization collections are separated into Continuous
Optimization and Discrete Optimization; Numerical Analysis, Numerical Linear
Algebra, and Algebraic Geometry are reserved for future collections. The
middle outline and right content panel keep their existing behavior.

## Run locally

With Docker:

```bash
docker compose up --build
```

Open <http://localhost:8000/>. For a lightweight static preview:

```bash
python3 -m http.server 8000 --directory site
```

## Repository map

- `site/index.html` contains the page structure.
- `site/styles.css` contains the visual design and responsive layout.
- `site/app.js` contains navigation, rendering, search, and submission history.
- `site/data/` contains the catalogue, manifest, and lazily loaded JSON shards.
- `Dockerfile`, `compose.yaml`, and `nginx.conf` provide the container runtime.
- `scripts/` contains the data import, shard build, and naming utilities.
- `.github/workflows/` contains the Pages and Docker image workflows.

## Handoff for the next agent

Keep website changes inside `site/`. Preserve the paths and schema under
`site/data/` unless a data update is explicitly requested. After changing CSS
or JavaScript, update its `?v=` value in `site/index.html` so deployed browsers
do not reuse an old asset. Submission history is stored only in the current
browser's `localStorage`.

Before handing off, run `node --check site/app.js` and preview the site locally.
Pushing reviewed files to `main` triggers the configured deployment workflows.

## Data refresh

The checked-in snapshot covers OptiStacks Parts A02–A16. It combines the v62
framework-sync candidate, all prior ReasAtlas statements, current
topic-complete layers, mechanically validated records from both textbook
campaign roots, the completed 74-record core convergence candidate layer, and
41 records from the mechanically validated prefix of the broader convergence
run.
Public textbook placement is deliberately conservative. In addition to exact
reviewed placements, v1.4 resolves proposed topics when the title exactly
matches a direct child, when it has a unique same-Part title match, or when at
least two textbook campaigns independently propose the same title under the
same live parent. This adds 50 cross-source-supported topic containers and
recovers 247 formerly quarantined candidates (230 public statements plus 17
duplicates suppressed). The remaining 40,507 builder-only, missing-container,
affected-node, or unresolved candidates stay in
`site/data/campaign_placement_quarantine.json`, now with their proposed-node and
directory-assessment evidence.
The importer preserves the reviewed A07.C03 revision from the current website
snapshot and installs it in Part A07. Rebuild it with:

```bash
python scripts/import_source_domains.py --source /root/workspace/lcy/optistacks
python scripts/build_lazy_shards.py
```

Legacy `#distributed_optimization/...` links and the merged A07 node are
resolved through the audited mapping sidecar. The subject navigation exposes
Derivative-Free Optimization, Manifold Optimization, and Distributed
Optimization as separate A07 shortcuts while retaining one canonical A07 data
source. Statement cards render convergence regimes, rates, complexity bounds,
boundary notes, variant relations, and evidence without displaying review
status. Validate the rebuilt snapshot and its statement placement with:

```bash
python scripts/validate_distributed_unification.py
python scripts/validate_framework_sync.py
```

The broader convergence refinement is incomplete. Only its 12 PASS shards are
included; the failed shard and 115 unstarted shards remain excluded.
