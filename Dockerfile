# Ask VAXT — the grounded, cited agent as an HTTP service.
#
# The 8.76 MiB heritage-grain DuckDB is baked into the image (read-only), so a
# clean clone starts with no volume wiring and the keyless demo works offline.
# ANTHROPIC_API_KEY is passed through at run time (never baked in); without it
# the UI still serves tools/health/citations and shows the honest "no key" state.
FROM python:3.11-slim

WORKDIR /app

# Install the packages first (their sources rarely change) for a warm layer.
COPY packages/ ./packages/
RUN pip install --no-cache-dir -e packages/vaxt -e "packages/vaxt-agent[web]"

# The committed warehouse and the eval harness (for the keyless `eval` profile).
COPY data/ ./data/
COPY eval/ ./eval/

ENV VAXT_DUCKDB_PATH=/app/data/datasets/heritage-grain/heritage-grain.duckdb \
    VAXT_REQUIRE_DB=1 \
    VAXT_WEB_HOST=0.0.0.0 \
    VAXT_WEB_PORT=8000

EXPOSE 8000

# /health is process + DB + SELECT 1; no model call, safe to poll.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

CMD ["uvicorn", "vaxt_agent.web:app", "--host", "0.0.0.0", "--port", "8000"]
