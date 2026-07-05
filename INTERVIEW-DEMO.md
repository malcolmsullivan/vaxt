# INTERVIEW-DEMO — the VAXT plugin, live and un-brickable

The goal: show a **fresh Claude Code session install the VAXT plugin and give a
grounded, machine-verified answer** — without the live outcome ever depending on a
network fetch in the room. "Fresh session" means a fresh *conversation*, not a fresh
*machine*: pre-warm everything, then run the visible steps from cache.

## Pre-warm (before the interview, on the demo laptop)

```bash
# 1. uv + Python present (the plugin does NOT bootstrap them)
uv --version && uv python install 3.11

# 2. Warm the MCP server build + its deps into uv's cache
uvx --from "D:/repos/vaxt/packages/vaxt" vaxt-mcp </dev/null   # builds + starts + exits on EOF

# 3. Warm the hook's env (duckdb)
uv run --no-project --with duckdb python -c "import duckdb; print('warm')"

# 4. Pre-add the marketplace + install the plugin so the room step is cache-only
claude plugin marketplace add malcolmsullivan/vaxt      # (or: add ./  from the repo)
claude plugin install vaxt@vaxt
```

## The ladder — flashy first, irrefutable last. Never degrade to broken.

**Rung 1 — live, from warm cache (the show).**
Open a fresh Claude Code session with the plugin enabled and run:

```
/vaxt Which heritage varieties suit a USDA zone 3 winter-wheat grower, and what are their cold-tolerance traits?
```

Expected: a prose answer citing each variety as `[varieties:<name>]`, then the Stop
hook's verdict line — **`VAXT grounding ✓ N/N citations resolve against the warehouse`**.
The point to say out loud: *"that checkmark is stamped by code I control — a Stop hook
that resolves every citation against DuckDB with no model call. Watch a fabricated one
get caught."* Then ask something out of scope (e.g. wheat futures price) to show the
honest `[[REFUSED]]`.

**Rung 2 — insurance (if the live `add`/`install` hiccups on schema drift).**
Have a second terminal already showing the plugin installed and one grounded answer +
verdict. Pivot to it instantly; the story is identical to the viewer.

**Rung 3 — irrefutable (if the room can't reach Anthropic at all).**
```bash
docker compose run --rm eval        # 17/17 keyless — no model, no network
```
This proves grounding holds deterministically over the 17 committed transcripts with
no API key. For an FDE audience this is arguably the most impressive rung.

**Rung 0 — ultimate (capture BEFORE the interview).**
A 30–60s screen recording of the real cold install → answer → verdict. It happened,
it's honest, and it's immune to the laptop misbehaving. **Record this the day before.**

## Failure modes → covered by

| If… | …then |
|---|---|
| `uv` missing on the box | pre-warm step 1; it is a stated prerequisite |
| cold `uvx`/clone on venue wifi | pre-warm builds are cached; Rung 1 is cache-only |
| plugin-marketplace schema drift between build day and interview day | Rung 2 (pre-installed terminal) + Rung 0 (recording) |
| room can't reach Anthropic | Rung 3 (`docker compose run eval`, keyless) |
| a citation is questioned as unchecked | that is the strength: `vaxt_verify_citation` + the Stop hook resolve it in code — show the fabricated-key flag |

## One-line talk track

> "I built the plugin, realized my grounding guarantee wasn't *composable* — it was
> coupled to the agent, so only the agent could produce checkable citations — and
> fixed **where the invariant lived**: I pushed provenance down into the data tier and
> made the plugin enforce it with a Stop hook. Now any consumer gets verifiable
> provenance for free."
