# Ask VAXT — a walkthrough

This is the spoken-interview version of the system: what problem it solves, how a
question becomes a grounded answer, the two or three decisions that were actually
hard, and the production concerns I'd expect to be asked about. It's meant to be
read top to bottom in about ten minutes.

---

## The problem

The data needed to breed cold-hardy grain is scattered across a dozen
incompatible public sources — FAO, Eurostat, USDA GrainGenes, T3/BrAPI, GBIF,
ISRIC SoilGrids, and more. VAXT unifies them under one typed schema in a 27-table
DuckDB warehouse. **Ask VAXT** is the natural-language layer on top: a breeder or
grower asks a question in plain English and gets an answer that is grounded in
that warehouse and cites the rows it came from — or a refusal when the warehouse
can't answer.

The hard requirement isn't "answer questions." It's **never invent an answer.**
For an agricultural decision-support tool, a confident hallucination is worse than
"I don't know." So the whole system is built around making hallucination a
*detectable, testable event* rather than a matter of trust.

## How a question becomes an answer

```
  "Which winter wheat tolerates the most cold?"
        │
        ▼
   Claude (claude-sonnet-5)  ──calls tools──▶  ToolCore → VaxtClient → DuckDB
        │   search_varieties, get_variety, get_disease_resistance, …
        │   each result tagged with its (table, key) provenance
        ▼
   Claude answers in prose with inline [table:key] citations
        │
        ▼
   Parse the citations, resolve each against DuckDB (no model call)
        │
        ▼
   Grounded, cited Transcript  →  streamed to the browser over SSE
```

1. The question goes to a real Claude agent (a manual tool-use loop, so every
   tool call and token is observable and the loop can be driven by a stub in
   tests).
2. Claude calls the read-only data tools it needs. Every row that comes back is
   tagged with a machine-checkable `(table, key)` — its provenance.
3. Claude answers **in prose**, with inline `[table:key]` citations, and refuses
   with a `[[REFUSED]]` token when the warehouse can't support an answer.
4. The citations are parsed out and each is resolved against DuckDB — with **no
   model call**. A citation is `(table, key)`; a fabricated key resolves to zero
   rows and fails. That is the whole trick: grounding becomes a deterministic
   check, not a judgment call.

## The decisions that were actually hard

**Grounding as a deterministic check, not an LLM judge.** The tempting design is
to have a second model grade whether the answer is supported. That's slow, costs
tokens, and can be wrong in correlated ways with the first model. Instead, a
citation is a structural fact — `(table, key)` — that either resolves against the
warehouse or doesn't. A single read-only SQL check per citation turns "is this
grounded?" into a boolean. The live eval *also* runs a semantic judge (on a
different model, Opus 4.8, to avoid correlated blind spots), but that's a bonus
signal on top of the deterministic gate, not the gate itself.

**Forcing a `submit_answer` tool degraded the answers — so I stopped forcing it.**
The first version (M1) made the model call a `submit_answer` contract tool whose
schema *required* a citation per claim. Schema-enforced grounding sounds ideal,
but forcing every answer through a rigid tool call measurably hurt answer quality
— the model wrote to satisfy the schema instead of to answer the question. The
pivot (M2) was to let the model answer naturally in prose and **parse and verify**
the `[table:key]` citations afterward. Same guarantee — every cited fact resolves
to a real row — but the model writes a genuinely better answer, and verification
is a post-processing step I fully control. The lesson: enforce the invariant at
the checkpoint you own, not by constraining the model's generation.

**The `>= 1 row` invariant.** Citation resolution is defined as "at least one row
in `table` where the key column matches." Exactly-one would be cleaner, but the
real data has a few legitimately non-unique natural keys (`varieties` has a
duplicate "Aurora"; two `eppo_code`s repeat; `markers` has no unique key). So the
honest invariant is `>= 1`. It still makes a *fabricated* key — the thing that
actually matters — a hard failure, and the UI's citation chips say "a matching
row," not "the row," so the interface doesn't over-claim.

## Production concerns

**Tests that passed by testing nothing.** The MCP client tests `skip` when the
DuckDB isn't present. In CI that read as green while exercising nothing. I
committed a prebuilt warehouse so the suite runs against real data, and added a
fail-loud guard (`VAXT_REQUIRE_DB=1`) so a missing warehouse *fails* the run
instead of silently skipping. A green badge has to mean the tests ran.

**Two advertised tools that crashed on their documented usage.** Writing tests for
previously-untested tools surfaced two real bugs — invisible precisely because
they had no test. `search_qtl` ordered by a column that didn't exist (`trait_name`
vs the real `trait`), so *every* call threw. `match_varieties`' coordinate path
used an aggregate with no `GROUP BY`, so coordinate-based matching *always* threw.
Both are fixed and covered. The takeaway I'd give an interviewer: the value of the
coverage pass wasn't the coverage number, it was finding the two tools that were
shipping broken.

**Failures never fabricate.** The HTTP service has exactly two honest failure
channels. If there's no API key, `/chat` returns a pre-stream **503** with
`{"code": "no_key"}` and the UI still shows tools, health, and citations working —
a real system with the model turned off, not a fake demo. If the model API fails
after retries, the stream ends with a terminal **`error` event**. An `answer`
event only ever carries a real transcript. (The distinction matters and I'm
careful to state it precisely: it's 503 *before* the stream opens, an `error`
event *after* — an SSE stream can't change its HTTP status once bytes flow.)

**Retries and idempotency.** Model calls retry (the SDK's `max_retries`) with a
per-call timeout. Tool calls **don't** retry — they're local, deterministic reads,
so a retry would just repeat a deterministic failure; instead they degrade to an
error envelope the agent can see and route around. Every warehouse operation is
read-only, so replays and retries are naturally idempotent — there's no write path
to make unsafe.

**What I redact.** Tool-call logs mask location-bearing arguments (`lat`, `lon`,
`location`, `station`) — a grower's question can carry their farm's coordinates —
and the question itself is logged by length only, never as text. Cost is an
estimate from a static price table, explicitly labeled as an estimate; an unknown
model logs `null` rather than a guess.

## How it scales, and what's next

The current build is a single-user demo: each `/chat` stream holds one thread, so
concurrency is bounded by the ASGI threadpool. The path to scale is an async agent
loop (or a worker pool) so streams don't each pin a thread, plus a cancellation
signal so a dropped browser stops the run instead of finishing it. The warehouse
is read-only and the DuckDB is baked into the container, so horizontal replicas
are trivial — there's no shared write state. Next steps I'd prioritize:
token-streaming the final model turn (so the answer types out rather than
appearing at once), and promoting the citation resolver to a first-class API other
consumers (the BrAPI clients) can call.

## Try it

```bash
docker compose run --rm eval    # the <2-min keyless proof: grounding holds, no API key
docker compose up               # serve the chat UI + /health + /ready on :8000
```

The eval grades 17 committed transcripts against the baked-in warehouse with no
model call — every citation must resolve, every answer must be anchored to the
known-correct row, and out-of-scope questions must refuse. That's the reproducible
proof. A live answer (set `ANTHROPIC_API_KEY`) is the key-gated bonus on top.
