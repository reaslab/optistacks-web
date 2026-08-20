# ReasAtlas

ReasAtlas is a public, static browser for structured knowledge in optimization
and analysis. The live site is <https://atlas.reaslab.io/>.

The current `20260819_v64_major_tracks_v1` snapshot contains 20 website domains
backed by the v64 extracted-major-track candidate. After First-Order Methods,
Manifold, Derivative-Free, and Distributed Optimization are published as independent
domains while preserving their original stable topic IDs. It contains 75,699
topic entries and 94,171 public statements, delivered through lazy chapter
shards. The data retains 115 convergence candidates. The interface does not
display review state.

The v64 structural synchronization changes directory ownership and navigation;
it does not duplicate public statements. Robust and Simulation Optimization
retain the inherited content coverage of the v1.5 website snapshot.

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

The checked-in snapshot combines the v64 directory candidate, all prior
ReasAtlas statements, current
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
The v64 major-track synchronization is materialized with:

```bash
python scripts/sync_v64_major_tracks.py
```

Legacy A07 and A16 links into the five moved subtrees are redirected to their
independent domains. Statement cards render convergence regimes, rates,
complexity bounds, boundary notes, variant relations, and evidence without
displaying review status. Validate the snapshot with:

```bash
python scripts/validate_v64_major_tracks.py
```

The broader convergence refinement is incomplete. Only its 12 PASS shards are
included; the failed shard and 115 unstarted shards remain excluded.
