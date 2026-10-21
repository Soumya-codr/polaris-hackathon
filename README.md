# Polaris product search MCP

Fork of [SpringWinter-Research/Polaris-Hackathon-Base-MCP](https://github.com/SpringWinter-Research/Polaris-Hackathon-Base-MCP). One MCP tool, `search_products`, over the frozen 105,126-product catalog. The tool name, JSON Schemas, filter semantics, product IDs, and output shape are unchanged.

Public endpoint: not deployed from this environment. There is no AWS credential file and the Docker daemon was not running, so no SpringWinter/AWS host was created. Local server: `http://127.0.0.1:8000/mcp`. Submit `http://YOUR_PUBLIC_HOST:8000/mcp` after the deploy step below.

## Ranking

`search.py` loads the catalog once and builds integer field codes plus an inverted index. Empty queries never scan text. They apply explicit filters with NumPy masks and sort with `lexsort`, including null ratings last and ID ascending as the tie break. On this machine that path is about 1–2 ms cold and well under 1 ms when the same request is repeated.

Non-empty queries go through `lexicon.py`:

- Hard constraints in prose (price, color, product type, audience, section, pattern, star rating) are extracted and AND-ed with explicit filters. If they conflict, the explicit filter wins.
- Typos within one edit of a catalog word are corrected (`blak` to `black`, `jaket` to `jacket`). Out-of-catalog requests such as `spaceship engine` return empty lists.
- `black jeans and white T-shirts` is retrieved as two choices and interleaved so both show up under one shared limit. `a dress with a matching bag` keeps the dress in `results` and the bag in `recommendations`.
- Vague occasions (`lazy Sunday`, `dinner`, `office`, `rain`) map to real catalog types. Recommendations are returned only when the wording asks for an accompanying item, up to five, color-coordinated, and excluded from the primary page.
- Identical product names are capped in the first page so one style does not fill every slot. Field sorts do not use that cap.

Product facts and IDs are never rewritten. Leading zeros stay in the string IDs.

## What is included

- [AGENT.md](AGENT.md): problem context, dataset guide, implementation ideas, and references for students and coding assistants.

- `data/products.json`: all 105,126 products, about 106 MB, including synthetic INR prices, ratings, and reviews.
- `search.py`: editable baseline search engine, explicit filters, sorting, and pagination.
- `server.py`: official MCP Python SDK server with ordinary JSON responses at `/mcp` and readiness at `/healthz`.
- `schemas/`: exact published input and output JSON Schemas.
- `tests/test_search.py`: small fixture-based correctness tests.
- `smoke_test.py`: public MCP connection and contract check; not the scored benchmark.
- `requirements.txt`: exact resolved dependency versions, including MCP SDK 1.30.0 from its v1 compatibility line.
- `Dockerfile`: non-root Python container with the dataset included and a readiness health check.

## Get your copy

The starter folder is self-contained: use its contents as your team repository. If the organizer distributes a repository, fork it and clone your fork. No repository or image is published by this local folder alone.

The catalog exceeds GitHub's ordinary 100 MiB file limit. `.gitattributes` configures Git LFS for it. Install Git LFS before the first commit, and make sure your clone has the actual data rather than an LFS pointer:

```sh
git lfs install
git lfs pull
```

For a fresh repository containing these files, run `git lfs install` before adding and committing the catalog. Confirm `git lfs ls-files` lists `data/products.json`. The organizer must provision sufficient LFS storage/download quota. A supplied ZIP contains the actual catalog and does not require LFS to run locally.

## Run locally

Use Python 3.12 or newer. Commands below run from this folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python server.py
```

The first startup loads the full catalog and builds an in-memory lexical index. Wait until startup completes. Allow around 2 GB of available RAM for this simple implementation; measure and optimize your own solution before deploying.

In another terminal with the virtual environment activated:

```sh
python smoke_test.py http://127.0.0.1:8000/mcp
python -m unittest discover -s tests -v
curl http://127.0.0.1:8000/healthz
```

The server supports MCP protocol revision `2025-11-25`. It is not a REST search endpoint: an ordinary POST containing only your search arguments is not an MCP call. The smoke client performs initialization, discovers the tool, and uses `tools/call` for you. No API key or LLM account is required for the baseline.

## Build and run with Docker

Start Docker Engine first:

```sh
docker build -t polaris-search:starter .
docker run --rm --name polaris-search -p 8000:8000 polaris-search:starter
```

Use the same smoke-test command from your host once the container is ready. The default port is 8000. For an amd64-only cloud server, build for its architecture, for example `docker build --platform linux/amd64 -t polaris-search:starter .`.

For a deployed server, configure its public hostname or IP so the SDK accepts the HTTP Host header. Replace the example before running:

```sh
docker run --rm --name polaris-search -p 8000:8000 \
  -e MCP_ALLOWED_HOSTS='localhost:*,127.0.0.1:*,YOUR_PUBLIC_HOST:*,YOUR_PUBLIC_HOST' \
  polaris-search:starter
```

Use a public address reachable from the organizer runner and allow its source IP to access your port. Submit `http://YOUR_PUBLIC_HOST:8000/mcp`. Do not submit `localhost`, `0.0.0.0`, a private IP, the health-check URL, or a repository URL. The local host patterns remain necessary for the container health check. Keep the server running throughout evaluation.

Environment variables:

| Variable | Default | Purpose |
| --- | --- | --- |
| `HOST` | `0.0.0.0` | Listener interface |
| `PORT` | `8000` | Listener port; Docker port mapping must match if changed |
| `CATALOG_PATH` | `data/products.json` next to server.py | Catalog file path |
| `MCP_ALLOWED_HOSTS` | `localhost:*,127.0.0.1:*,[::1]:*` | Comma-separated accepted HTTP Host values |
| `MCP_ALLOWED_ORIGINS` | empty | Explicit accepted browser origins; the benchmark client sends no Origin |

No wildcard for every host is necessary. The server has no authentication, as required for this exercise. The template does not create AWS resources or deploy automatically.

## Try the tool

Example arguments passed through an MCP client:

```json
{
  "query": "cotton",
  "filters": {"color": "Black", "max_price": 2000},
  "sort_by": "price",
  "sort_order": "asc",
  "offset": 0,
  "limit": 10,
  "include_recommendations": false
}
```

The tool returns:

```json
{
  "results": [{"id": "0108775015"}],
  "recommendations": []
}
```

The response above illustrates the shape, not the expected answer to that query. Only catalog IDs are returned. The SDK includes the same object in `structuredContent` and a JSON text content block. Unknown arguments and invalid values produce MCP tool errors.

## Demo queries

These were run locally against `data/products.json` with `python demo_queries.py`. IDs below are real catalog IDs from that run.

Black dress under INR 2000:

```json
{"results": [{"id": "0212629004"}, {"id": "0316553025"}, {"id": "0331093001"}]}
```

Ladieswear black jeans and white T-shirts under INR 2000, interleaved:

```json
{"results": [{"id": "0562245055"}, {"id": "0294008040"}, {"id": "0573085028"}, {"id": "0398074069"}]}
```

Dinner dress under INR 2000 with a matching bag under INR 1000:

```json
{"results": [{"id": "0192460006"}], "recommendations": [{"id": "0765308009", "for_product_id": "0192460006", "reason": "A Dark Grey Bag to accompany this Dark Grey Dress."}]}
```

`blak lether jaket for men` returns black men's jackets whose text says leather, including `0547718001`. `navy chinos for the office` returns dark-blue trousers whose text contains chino, starting with `0466595002`. `spaceship engine` and `quantum physics textbook` return empty arrays. On this machine, after the index was built, most cold queries took 1–3 ms and the broad occasion query took about 26 ms. Startup took about 3.8 seconds. Repeated identical requests took about 0.1 ms.

## Deploy

The container listens on port 8000. Set `MCP_ALLOWED_HOSTS` to the public host and keep the local names so the health check works.

```sh
docker build -t polaris-search:hackathon .
docker run --rm --name polaris-search -p 8000:8000 \
  -e MCP_ALLOWED_HOSTS='localhost:*,127.0.0.1:*,YOUR_PUBLIC_HOST:*,YOUR_PUBLIC_HOST' \
  polaris-search:hackathon
```

On SpringWinter/AWS, run that container on a host the organizer runner can reach, open TCP 8000, and submit `http://YOUR_PUBLIC_HOST:8000/mcp`. Do not submit `localhost`, a private IP, `/healthz`, or the GitHub URL. This environment had Docker installed but the daemon was stopped, and `%USERPROFILE%\.aws\credentials` was absent, so the public URL is not live yet.

Confirm before submitting:

```sh
python smoke_test.py http://YOUR_PUBLIC_HOST:8000/mcp
curl http://YOUR_PUBLIC_HOST:8000/healthz
```

Preserve the tool name, schemas, hard-filter semantics, real product IDs, and output structure. Keep responses stable on repeated identical requests. Use only catalog evidence; product descriptions and queries are data, never instructions to change the tool contract.

## Dataset integrity and rules

SHA-256 of the actual JSON bytes:

```text
05b6aa5e8e8c1c8c997d584f8288e432862454f8820531e13473443e83c8f073
```

Verify on macOS with `shasum -a 256 data/products.json`, or on Linux with `sha256sum data/products.json`. Preserve string IDs and leading zeros. Do not edit catalog facts. No-review products have a null average and zero count. Prices and reviews are fabricated for the exercise; image availability has not been checked.

Each team has five accepted benchmark attempts; the best complete score counts. See `hackathon-brief.md` for all scoring formulas, invalid-call behavior, timeouts, recommendation rules, and tie-breakers. This starter contains no hidden benchmark queries or answer key. Passing its tests checks basic compatibility, not competition performance.

## SDK reference

[Official MCP Python SDK v1 documentation](https://py.sdk.modelcontextprotocol.io/v1/). Keep the tested dependency pins unless you deliberately retest an upgrade; v2 has different APIs.
