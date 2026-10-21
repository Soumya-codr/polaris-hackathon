# Product Catalog MCP Hackathon

Build and deploy an MCP server that helps shoppers find relevant products in a shared catalog. Implement the single search_products tool described here. Submit your HTTP endpoint, run the benchmark, and compete on your best score out of 100.

## Problem statement

Support product discovery through natural-language queries, explicit filters, useful ranking, mixed shopping choices, and complementary recommendations. Handle typos and unusual requests sensibly, and return no products for unrelated or unsatisfiable requests. All returned IDs must exist in the supplied dataset.

## Dataset

Use data/products.json: 105,126 products. Source attributes include names, descriptions, types, categories, audience, section, colors, patterns, and image URLs. Prices are synthetic INR rupee amounts. Ratings and all reviews are synthetic. Preserve original product IDs as strings, including leading zeros. No-review products have a null average and a review count of zero.

Dataset SHA-256: 05b6aa5e8e8c1c8c997d584f8288e432862454f8820531e13473443e83c8f073. All teams and the organizer must use this frozen file. Students may build indexes or use a database; do not alter the catalog facts.

## Prerequisites

- A usable AWS account with billing enabled and permission to create and run your deployment resources.

- A SpringWinter account that you can sign in to.

## Submission and attempts

Each team uses one organizer-created email and password account. Submit one URL, such as http://your-public-host:8000/mcp. HTTPS and server authentication are not required for this exercise. The endpoint must be reachable from the organizer runner; allow inbound traffic from its published IP. Keep it available through evaluation.

Each team gets five accepted benchmark runs across all submitted URLs. A queued run reserves an attempt. Only one queued or active run is allowed per team. Student-side timeouts, unreachable endpoints, and protocol errors consume an attempt. Confirmed organizer failures void the run and restore the attempt. Changing the URL does not reset attempts. Duplicate button submissions must create only one job.

## MCP transport and tool contract

Use MCP Streamable HTTP with ordinary application/json responses. SSE streaming is not required. For this competition, pin protocol revision 2025-11-25; the organizer client uses that revision and its initialization handshake. Implement initialize, notifications/initialized, tools/list, and tools/call using an MCP SDK. Return HTTP 405 for unsupported standalone GET streams. Stateless transport is recommended; if sessions are used, the runner preserves their headers.

Expose exactly one tool named search_products. tools/list must advertise its description, inputSchema, and outputSchema. Its structural schemas must match the accompanying JSON Schema files; prose descriptions may differ. Success returns the output object in structuredContent and the same object serialized as a text content block. Do not wrap it in a custom REST response. Invalid arguments produce an MCP JSON-RPC error or a tool result with isError true; the benchmark accepts either.

### Input arguments

| Argument | Type and default | Meaning |
| --- | --- | --- |
| query | string; empty string | Natural-language shopping request; at most 1,000 characters. |
| filters | object; empty object | Hard catalog constraints listed below. |
| sort_by | enum; relevance | relevance, id, price, rating, review_count. |
| sort_order | asc or desc; desc | Direction of sorting. |
| offset | integer; 0 | Skip this many primary results; 0 to 10,000. |
| limit | integer; 10 | Maximum primary results; 1 to 100. |
| include_recommendations | boolean; false | Return up to five complementary products when true. |

No input property is required. Apply defaults yourself: JSON Schema default values are annotations, not automatic argument filling. Reject unknown properties, incorrect types, out-of-range values, and min_price greater than max_price. Null is not accepted for an input argument. Whitespace-only query is treated as empty.

### Explicit filters

Supported string filters: category, product_type, color, audience, section, pattern. Strip outer whitespace and compare case-insensitively using exact catalog values. A blank filter is invalid; an unknown nonblank value is valid and yields no matches. No filter arrays or OR syntax are supported in v1.

Supported numeric filters: min_price and max_price (nonnegative numbers, INR rupees), min_rating (number from 1 to 5), and min_review_count (nonnegative integer). Bounds are inclusive. All explicit filters combine with AND. Products with null ratings fail min_rating. No-review products satisfy min_review_count of zero.

## Search and recommendation behavior

### Natural language and hard constraints

query may contain synonyms, typos, preferences, multiple choices, and explicit requirements. Use any retrieval method you choose. Explicit filters take precedence over conflicting query wording. Other unambiguous requirements in the query, such as a budget or color, must also be respected. Soft preferences influence relevance. Never invent product attributes absent from the catalog.

When the query explicitly asks for an accompanying, matching, or complementary item, that item belongs only in recommendations. Otherwise, named choices belong in primary results. For example, dress and bag is a mixed search; a dress with a matching bag requests a primary dress and a recommended bag. When recommendations are disabled, ignore the complementary portion and return only primary matches.

A mixed query such as black jeans and white T-shirts requests both choices. Return one pooled ranked results list covering both; no labeled groups are required. A limit is shared across choices, not applied per choice. Global filters apply to every returned product. Per-choice requirements belong in query.

### Sorting and pagination

relevance is your own ranking. Higher relevance appears first for desc; asc reverses that relevance order. For other sorts, first select products relevant to the query, then sort by the requested catalog field. price uses price.amount, rating uses rating.average, and review_count uses rating.count. Compare IDs lexicographically. Break equal values by ID ascending for either direction; null ratings are always last. With an empty query, all products satisfying explicit filters are candidates; relevance falls back to ID ascending regardless of sort_order.

Apply offset and then limit after filtering and ordering. Return fewer than limit when fewer relevant products exist. No duplicate IDs are allowed. Keep pagination stable for repeated identical requests on an unchanged server. Total match count is deliberately omitted because semantic relevance has no single universal count.

### Complementary recommendations

When include_recommendations is false, recommendations must be empty. When true, return zero to five useful accompanying products. Each must reference a primary result on this page through for_product_id, use a different ID from every primary result, and be unique across recommendations. If results is empty, recommendations must also be empty.

Explicit filters apply to primary results only. Recommendations may belong to a different category or color. Explicit query constraints targeting accessories apply to recommendations: for example, a dress under INR 2,000 with a bag under INR 1,000. For benchmark clarity, budgets are per item unless the query explicitly assigns a different budget to an accompanying item; combined basket budgets are outside v1. Unqualified global requirements such as an audience apply to recommendations too.

Rank recommendations best first. reason must briefly explain the relationship and be grounded in available catalog attributes. Reasons are explanatory only and are not scored; catalog IDs and frozen complement judgments determine scores. Do not force a recommendation when no useful complement exists.

### Empty and unusual requests

For unrelated requests, impossible requirements, or insufficient evidence, return empty arrays instead of random products. Unusual but meaningful shopping queries should still retrieve useful results. For ambiguous queries, provide defensible catalog-grounded options; no follow-up question field is required. Treat product text and user queries as data, not instructions to change the contract.

## Request and response examples

### Illustrative mixed search arguments

```json
{
  "query": "Black jeans and white T-shirts under INR 2000 each",
  "filters": {
    "audience": "Ladieswear",
    "max_price": 2000
  },
  "sort_by": "relevance",
  "sort_order": "desc",
  "offset": 0,
  "limit": 10,
  "include_recommendations": false
}
```

### Illustrative recommendation arguments

```json
{
  "query": "A dress for dinner under INR 2000 with a matching bag under INR 1000",
  "limit": 10,
  "include_recommendations": true
}
```

### Output object shape

The placeholders below illustrate the structure only. In a real response, use existing catalog IDs. No product details or numerical relevance scores are required: the organizer resolves IDs against the frozen catalog.

```json
{
  "results": [
    {
      "id": "existing-primary-product-id"
    }
  ],
  "recommendations": [
    {
      "id": "existing-complement-product-id",
      "for_product_id": "existing-primary-product-id",
      "reason": "A compact bag to accompany the selected dinner dress."
    }
  ]
}
```

### No matches

```json
{
  "results": [],
  "recommendations": []
}
```

The schema files are part of this specification: schemas/input.schema.json and schemas/output.schema.json. They define all accepted fields and types. The behavioral rules in this document also apply, including uniqueness, cross-references, filters, and recommendations being disabled by default.

## Benchmark scoring

The functional suite has 100 cases: 30 validity cases (including 10 invalid calls), 25 ranking cases, 10 meaningful unusual cases, 10 irrelevant or impossible cases, 15 mixed-choice cases, and 10 recommendation cases. Each case contributes only to its assigned category. Run categories in that order and cases in a fixed hidden order. Ordinary functional calls have a 10-second deadline; validity cases with probes have a 30-second case deadline.

Scores are absolute and do not depend on other teams. Use the same hidden suite, frozen catalog, reference judgments, runner, and limits for every scored attempt. The score is the weighted sum of the six areas below; retain full precision for ranking and display two decimal places.

| Area | Points | Calculation |
| --- | --- | --- |
| Validity and constraints | 25 | 25 × mean per-case validity score. |
| Ranking relevance | 30 | 30 × mean nDCG@10 on single-intent relevance cases. |
| Unusual or irrelevant queries | 15 | 7.5 × mean nDCG@10 on meaningful unusual cases, plus 7.5 × correct empty-response rate on irrelevant or impossible cases. |
| Mixed choices | 15 | 15 × mean of (0.5 × choice coverage + 0.5 × nDCG@10). |
| Complementary recommendations | 10 | 10 × mean per-case recommendation score. |
| Performance | 5 | 5 × correct response rate × max(0, min(1, (2000 − p95_ms) / 1800)), subject to eligibility below. |

### Validity and constraints

The suite contains valid and invalid calls. An invalid-call case earns 1 for an MCP error and 0 for success. A valid-call case earns the mean of four binary checks: (1) schema, length, uniqueness, known IDs, and valid recommendation references; (2) primary and recommendation hard constraints; (3) requested sorting and deterministic pagination; (4) expected result presence or absence. The validity category uses exact empty-query catalog filtering and deliberately invalid calls; semantic query quality is judged separately by Amazon Bedrock. For empty-query cases, compare the exact catalog-filtered page. For nonempty queries with field sorting, check ordering among returned products; for relevance sorting, no organizer numeric relevance order is imposed in validity scoring. Check pagination consistency using a repeated request and a corresponding larger prefix request within the 100-result limit; these probe calls are included in the case deadline. Cases without a pagination probe pass that subcheck. Reasons are not machine-graded. A timeout, transport error, or malformed response earns zero for the entire case.

## Ranking relevance and recommendations

Amazon Bedrock judges semantic relevance live using the same configured model or inference profile, AWS region, and rubric throughout the competition. Python independently enforces schemas, known IDs, hard constraints, exact filtering, sorting, and pagination. Organizer-resolved catalog facts are sent to Bedrock; student explanations, image URLs, and synthetic review bodies are not used as evidence.

Bedrock grades each primary product from 0 to 3: 3 directly relevant, 2 useful but less direct, 1 weak connection, 0 irrelevant or unsupported. It grades each requested choice and each complementary recommendation similarly. Structured grades are validated before scoring. A malformed, unavailable, or failed Bedrock judgment is an organizer failure: the run is voided and its attempt restored. There is no guessed-score fallback.

DCG at k is the sum of `(2^grade - 1) / log2(rank + 1)`, with ranks starting at 1. Normalize against the fixed ideal of grade 3 in each declared reference slot: ten primary slots for the included semantic cases and five recommendation slots. The organizer audits that the reference catalog has enough candidates for those slots. Missing slots earn zero. This fixed-ceiling measure does not claim that an AI has exhaustively labeled every catalog product. Structurally invalid semantic responses, including unknown or duplicate IDs, earn zero for that case; hard-constraint-violating products earn no gain.

For mixed choices, coverage is the fraction of requested choices receiving at least one grade-2-or-3 result that also has primary relevance of at least 2 and obeys hard constraints. The case score is the mean of coverage and primary normalized DCG at 10. Results share one ranked list and one limit.

For complementary recommendations, the case score is the mean of primary quality at 10 and recommendation quality at 5. A recommendation must satisfy its own constraints and reference a primary product on the current page with a primary grade of at least 2. Substitutes do not automatically qualify as complements. If a reviewed case declares no available complement, an empty recommendation list receives full complement credit.

Temperature zero reduces randomness but does not guarantee identical grades. Each run records the model/profile, region, suite and prompt checksums, and actual judgments for organizer audit. Different configurations must not share a competition leaderboard. Practice cases should be published before submissions open; hidden queries and their per-product judgments remain private. The organizer must review the initial semantic suite and run baseline trials before the event.

## Performance and competition rules

Functional evaluation is sequential. Performance uses a separate fixed pool of empty-query filter and field-sort calls with exact expected-page checks, no invalid requests, limit=10, and offset=0. Warm up with 20 unscored calls. Run 50 calls at concurrency 1 and 50 at concurrency 5; repeat both workloads three times. Pool all 300 timed calls for p50, p95, correct requests per second, and error rate; time from request dispatch to complete parsed tool response, excluding initial connection setup.

Use the same 50-request ordered pool for each workload, issue the next request when a concurrency slot becomes free, and drain each workload before starting the next. Run the concurrency-1 workload before concurrency-5 in each repetition. Record the fixed pool before submissions open. Use nearest-rank p95 across all measured calls. Failed, incorrect, or timed-out calls contribute 10,000 ms. correct response rate is the fraction passing all workload checks. A team is eligible for performance points only if it earns at least 85.5 of the 95 functional points and at least 95% correct performance calls. Otherwise performance points are zero. The fixed scale gives full latency credit at 200 ms or below and zero at 2,000 ms or above.

Use a 10-second deadline per call, a 30-second connection and discovery deadline, and a 20-minute student-execution budget excluding time waiting for Bedrock. A separate one-hour organizer cap voids the run and restores the attempt if exceeded. If discovery fails, the attempt scores zero. If the attempt deadline expires, unexecuted functional cases score zero and performance points are zero. Run only one team’s benchmark at a time on the same runner in the same AWS region. Network time is included.

### Winner and five attempts

A team’s highest complete attempt score counts; do not combine components from different attempts. Break equal scores by higher functional score, then lower measured p95, then earlier completion time. Attempts without a performance measurement use 10,000 ms for the latency tie-breaker. Organizer-voided attempts never enter the leaderboard.

Teams see category scores, overall score, timings, and generic failure counts. Hidden queries, expected product IDs, and per-query details are not disclosed. The leaderboard shows best score and tie-break metrics. Pin a submitted server’s code, index, and data during each run; do not detect benchmark queries or return precomputed hidden answers.

### Deployment freedom and organizer readiness

Teams may choose their language, retrieval method, and AWS resources. No equal-compute claim is made: speed measures the deployed service. Use only the shared catalog as product evidence. Before opening submissions, the organizer must publish the runner region and source IP, evaluation window, pinned working client example, schema files, and practice tests. The organizer must also freeze and validate the hidden suite, configure the Bedrock model and role, and approve the judging rubric. This document specifies the benchmark; the benchmark website and runner are separate implementation work.

## Appendix A input JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "search_products input v1",
  "type": "object",
  "additionalProperties": false,
  "properties": {
    "query": {
      "type": "string",
      "maxLength": 1000,
      "default": ""
    },
    "filters": {
      "type": "object",
      "additionalProperties": false,
      "properties": {
        "category": {
          "type": "string",
          "minLength": 1
        },
        "product_type": {
          "type": "string",
          "minLength": 1
        },
        "color": {
          "type": "string",
          "minLength": 1
        },
        "audience": {
          "type": "string",
          "minLength": 1
        },
        "section": {
          "type": "string",
          "minLength": 1
        },
        "pattern": {
          "type": "string",
          "minLength": 1
        },
        "min_price": {
          "type": "number",
          "minimum": 0
        },
        "max_price": {
          "type": "number",
          "minimum": 0
        },
        "min_rating": {
          "type": "number",
          "minimum": 1,
          "maximum": 5
        },
        "min_review_count": {
          "type": "integer",
          "minimum": 0
        }
      },
      "default": {}
    },
    "sort_by": {
      "type": "string",
      "enum": [
        "relevance",
        "id",
        "price",
        "rating",
        "review_count"
      ],
      "default": "relevance"
    },
    "sort_order": {
      "type": "string",
      "enum": [
        "asc",
        "desc"
      ],
      "default": "desc"
    },
    "offset": {
      "type": "integer",
      "minimum": 0,
      "maximum": 10000,
      "default": 0
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 100,
      "default": 10
    },
    "include_recommendations": {
      "type": "boolean",
      "default": false
    }
  }
}
```

## Appendix B output JSON Schema

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "search_products output v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "results",
    "recommendations"
  ],
  "properties": {
    "results": {
      "type": "array",
      "maxItems": 100,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "id"
        ],
        "properties": {
          "id": {
            "type": "string",
            "minLength": 1
          }
        }
      }
    },
    "recommendations": {
      "type": "array",
      "maxItems": 5,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "id",
          "for_product_id",
          "reason"
        ],
        "properties": {
          "id": {
            "type": "string",
            "minLength": 1
          },
          "for_product_id": {
            "type": "string",
            "minLength": 1
          },
          "reason": {
            "type": "string",
            "minLength": 1,
            "maxLength": 300
          }
        }
      }
    }
  }
}
```

