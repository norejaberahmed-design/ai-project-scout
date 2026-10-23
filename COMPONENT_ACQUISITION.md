# Component acquisition workflow

AI Project Scout can inspect a public GitHub repository and stage a bounded copy of eligible source/document files for review.

## What it does

1. Resolves a repository to an immutable commit SHA.
2. Requires a declared SPDX license from the explicit allowlist: MIT, Apache-2.0, BSD-2-Clause, BSD-3-Clause, ISC, or 0BSD.
3. Reads the upstream license text and checks that it matches the declared license family.
4. Copies eligible text files (source, documentation, and configuration) into `components/proposed/<owner>__<repo>-<commit>/`.
5. Writes `ACQUISITION_MANIFEST.json` with source URLs, exact commit, file SHA-256 hashes, license evidence, copied sizes, and review checklist.

## Important limits

- It does not copy every repository on GitHub. A repository must be selected for review.
- It deliberately skips binaries, symlinks, secrets, hidden directories, dependency lockfiles, build output, and common generated/vendor directories.
- Limits: 60 eligible files, 80 KB per file, and 1 MB total. GitHub tree truncation causes a fail-closed refusal.
- A declared license is not legal advice. Verify the full license obligations and file-level notices before redistribution.
- The import is a quarantined proposal. No downloaded code is installed, executed, imported into the running agent, or activated automatically.
- Dependencies must be reviewed separately. A copied `package.json` or `pyproject.toml` is metadata, not permission to install its dependencies.
- The importer does not download model weights or claim to clone this assistant's private model parameters.

## API

### Inspect only

`POST /api/components/inspect`

JSON body:

```json
{"repository_url":"https://github.com/OWNER/REPOSITORY"}
```

This performs a bounded public metadata/tree/license inspection and does not copy files.

### List staged proposals

`GET /api/components`

Returns manifests for staged proposals without executing them.

### Acquire into quarantine

Set `SCOUT_COMPONENT_IMPORT_TOKEN` as a server-side environment secret. Do not place it in GitHub Pages JavaScript, HTML, a public config file, or a chat message.

`POST /api/components/acquire`

```json
{"repository_url":"https://github.com/OWNER/REPOSITORY"}
```

Send the admin token in the HTTP header `Authorization: Bearer <token>`. The server checks the token and only then copies eligible files into the proposal quarantine. Rotate the token if exposed.

Example from a trusted terminal:

```sh
curl -X POST "$SCOUT_API_URL/api/components/acquire" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $SCOUT_COMPONENT_IMPORT_TOKEN" \
  -d '{"repository_url":"https://github.com/OWNER/REPOSITORY"}'
```

For local CLI use, from the project root:

```sh
python component_acquisition.py https://github.com/OWNER/REPOSITORY --inspect-only
python component_acquisition.py https://github.com/OWNER/REPOSITORY --confirm-copy
```

## Required next step before integration

A maintainer must review the copied files, licensing, dependency chain, threat model, and tests. Only a separate reviewed change may integrate accepted code. Do not execute repository scripts directly on the production server. Keep a rollback path and run tests in a disposable environment.
