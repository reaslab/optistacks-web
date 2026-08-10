# ReasAtlas

Static knowledge atlas for Convex Analysis, Variational Analysis, Nonlinear
Programming, First-Order Methods, and Distributed Optimization. This repository
snapshot contains 18,883 topics and 26,912 statements.

## Run locally with Docker

```bash
docker compose up --build
```

Open <http://localhost:8000>.

Without Compose:

```bash
docker build -t optistacks-web .
docker run --rm -p 8000:80 optistacks-web
```

## GitHub Container Registry

Pushes to `main` build Linux AMD64 and ARM64 images and publish them to:

```text
ghcr.io/reaslab/optistacks-web:latest
```

Pull requests run the same multi-platform build without publishing. Tags such
as `v1.0.0` additionally publish semantic-version image tags.

The workflow uses the repository `GITHUB_TOKEN`; no registry password secret is
required. The repository or organization must allow Actions to write packages.

## GitHub Pages

Pushes to `main` also deploy the contents of `site/` as the public ReasAtlas at
<https://reaslab.github.io/optistacks-web/>.

## Static snapshot

The `site/` directory is self-contained and includes:

- the browser interface;
- the Convex Analysis directory and statements;
- the Variational Analysis directory and statements;
- the Nonlinear Programming directory and statements;
- the First-Order Methods directory and statements;
- the Distributed Optimization directory and statements;
- the build manifest.

The nginx image serves JSON with gzip enabled. The manifest is revalidated on
every load. A lightweight domain catalogue is loaded first; chapter payloads
are fetched only when visited and then reused from memory and the versioned
browser/CDN cache.

To refresh A03/A05 and the validated `0809_optimize` campaign snapshot from the
source knowledge workspace, then rebuild the lazy chapter payloads, run:

```bash
python scripts/import_source_domains.py \
  --source /root/workspace/lcy/optistacks
python scripts/build_lazy_shards.py
```

Then review and commit the changed files in this standalone repository.

## Directory-name polishing workflow

Export every domain label and topic-directory name into stable-ID JSON batches
that can be edited with Web GPT:

```bash
python3 scripts/manage_directory_names.py export --zip
```

The generated `directory_names_workbook/README.md` contains the upload prompt,
validation, dry-run apply, write-back, and restoration commands. The importer
changes only `new_title` mappings, synchronizes repeated catalogue/shard/manifest
copies, and rejects edits to IDs or hierarchy fields.

## Publishing the repository

After authenticating GitHub CLI with an account that can create repositories
in `reaslab`:

```bash
gh auth login
gh repo create reaslab/optistacks-web --public --source=. --remote=origin --push
```

GitHub Actions builds and stores the image and deploys the static snapshot to
GitHub Pages. A separate container host is only needed for the container image.
