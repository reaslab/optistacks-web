# ReasAtlas

ReasAtlas is a public, static browser for structured knowledge in optimization
and analysis. The live site is <https://stacks.reaslab.io/>.

The current snapshot contains all 15 Parts from A02 through A16. The reviewed
Distributed Optimization revision is installed directly at A07.C03, replacing
the older duplicate compatibility domain. It contains 75,646 topic entries and
88,753 statements, delivered through 197 lazy chapter shards.

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

The checked-in snapshot covers OptiStacks Parts A02–A16. It combines the last
complete full-depth directory, all prior ReasAtlas statements, current
topic-complete layers, and mechanically validated records from both textbook
campaign roots. The importer preserves the reviewed A07.C03 revision from the
current website snapshot and installs it in Part A07. Rebuild it with:

```bash
python scripts/import_source_domains.py --source /root/workspace/lcy/optistacks
python scripts/build_lazy_shards.py
```

Legacy `#distributed_optimization/...` links and the merged A07 node are
resolved through the audited mapping sidecar. The subject navigation exposes
Distributed Optimization as the fifth shortcut while keeping A07.C03 as its
single data source. Validate the rebuilt snapshot and its statement placement
with:

```bash
python scripts/validate_distributed_unification.py
```
