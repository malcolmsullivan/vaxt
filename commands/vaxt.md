---
name: vaxt
description: Ask the VAXT heritage-grain warehouse a question and get a grounded, cited answer (defaults to a zone-3 winter-wheat demo).
---

Answer the following heritage-grain question **strictly from the VAXT warehouse**,
using the `vaxt_*` MCP tools and following the `vaxt-grounding` skill: answer in
prose, cite every fact inline as `[table:key]`, and refuse with `[[REFUSED]]` if the
warehouse cannot answer.

Question: $ARGUMENTS

If the question is empty, answer this demo question instead: **"Which heritage
varieties suit a USDA zone 3 winter-wheat grower, and what are their cold-tolerance
traits?"** — call `vaxt_match_varieties` and `vaxt_search_varieties`, then cite each
recommended variety as `[varieties:<name>]`.
