# OptiStacks Web

Static knowledge atlas for Convex Analysis and Nonlinear Programming. This
repository snapshot contains 6,794 topics and 12,645 statements.

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

Pushes to `main` also deploy the contents of `site/` as the public OptiStacks
Knowledge Atlas at <https://reaslab.github.io/optistacks-web/>.

## Static snapshot

The `site/` directory is self-contained and includes:

- the browser interface;
- the Convex Analysis directory and statements;
- the Nonlinear Programming directory and statements;
- the build manifest.

The nginx image serves JSON with gzip enabled. The manifest is revalidated on
every load, while versioned domain payloads can be cached by the browser.

To refresh this snapshot from the source OptiStacks workspace, run there:

```bash
python scripts/build_knowledge_site.py \
  --output standalone/optistacks-web/site
```

Then review and commit the changed files in this standalone repository.

## Publishing the repository

After authenticating GitHub CLI with an account that can create repositories
in `reaslab`:

```bash
gh auth login
gh repo create reaslab/optistacks-web --public --source=. --remote=origin --push
```

GitHub Actions builds and stores the image and deploys the static snapshot to
GitHub Pages. A separate container host is only needed for the container image.
