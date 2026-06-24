# Preciso Agent

`preciso-agent` is a local chat agent that uses:
- **OpenBB** as the data provider layer
- **Groq** as the orchestration and extraction model
- **Preciso** from the parent repo as the graph ingestion and query engine

## Workflow

1. Ask the agent to fetch finance data.
2. The agent pulls SEC-oriented source material through OpenBB.
3. It writes normalized Markdown files to `workspace/to_be_extracted/`.
4. It generates Preciso-compatible extraction JSON into `workspace/extractions/`.
5. It calls Preciso ingestion tools from the parent repo.
6. It can optionally run a graph query after ingestion.

## Current v1 data path

- SEC filing metadata
- Management discussion and analysis text
- Earnings context placeholder document

This keeps the provider layer source-first and compatible with Preciso's parser-free contract.

## OpenBB as the source layer

OpenBB is the data provider for the agent in this repo. The workflow uses the OpenBB SEC fetchers to pull structured source material, then converts that into normalized Markdown and Preciso extraction JSON.

In practice:

1. The agent reads your prompt and decides whether it needs to fetch data or query the existing graph.
2. If it needs data, `providers/openbb_provider.py` calls OpenBB fetchers for SEC filings, management discussion, and optional earnings context.
3. The fetched material is written into `workspace/to_be_extracted/` as Markdown and `workspace/manifests/` as provenance records.
4. Groq converts the source text into Preciso-compatible graph extraction JSON.
5. Preciso ingests the JSON and the agent can optionally query the graph afterward.

This is a good fit when you want one standardized source layer for finance workflows instead of wiring each vendor directly into the graph pipeline.

## Environment

Create `preciso-agent/.env` with:

```bash
GROQ_API_KEY=your_key_here
GROQ_MODEL=llama-3.3-70b-versatile
```

Optional:

```bash
PRECISO_REPO_ROOT=/absolute/path/to/preciso-graphrag
PRECISO_AGENT_WORKSPACE=/absolute/path/to/workspace
OPENBB_SEC_FORM_TYPES=10-K,10-Q,8-K
PRECISO_QUERY_MODE=mix
```

## Run

```bash
cd preciso-agent
python3 main.py
```

If you want the agent to use a different workspace or a different Preciso checkout, set `PRECISO_AGENT_WORKSPACE` and `PRECISO_REPO_ROOT` in `.env` before running.

## Example prompts

- `Fetch AAPL latest filing data from OpenBB, ingest it into Preciso, and stop after ingestion.`
- `Fetch NVDA filing and management discussion data, ingest it, then tell me the main strategic themes.`
- `Query the existing graph for TSLA risk factors.`

## Workspace

- `workspace/to_be_extracted/`: normalized source Markdown files
- `workspace/extractions/`: graph extraction JSON files
- `workspace/manifests/`: provenance manifests for stored documents

## Notes

- The current OpenBB install in this environment uses the newer package-builder layout, so the agent integrates with the SEC fetchers directly.
- The agent uses a local `HOME` override while fetching OpenBB data so OpenBB cache/settings stay inside this project instead of trying to write to the global home directory.
- Streamlit is intentionally out of scope for v1. The primary entrypoint is the CLI chat loop.

## LinkedIn blog draft

See [OPENBB_LINKEDIN_BLOG.md](OPENBB_LINKEDIN_BLOG.md) for a ready-to-post LinkedIn draft and a longer blog version.

