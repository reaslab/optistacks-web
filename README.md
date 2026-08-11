# ReasAtlas

ReasAtlas is a public, static browser for structured knowledge in optimization
and analysis. The live site is <https://stacks.reaslab.io/>.

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
