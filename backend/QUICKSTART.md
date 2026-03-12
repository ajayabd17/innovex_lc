# Quick Start Guide

## Install

```bash
cd c:\\Projects\\Innovex_lc
python -m venv venv
.\\venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
```

## Configure `.env`

```bash
GEMINI_API_KEY=...
GROQ_API_KEY=...
GITHUB_TOKEN=...
SUPABASE_URL=...
SUPABASE_ANON_KEY=...
```

## Run

```bash
python main.py --company "OpenAI"
```

Or interactive:

```bash
python main.py
```

## Enforced Runtime Flow

1. Input company name
2. Run configured generator providers sequentially (default: `fireworks`, `groq`, `baseten`) and enforce quorum
3. If at least 2 providers succeed, 4th LLM consolidates. If only 1 succeeds, consolidation is skipped
4. Pydantic validates exact 10-field contract
5. Pytest runtime gate validates payload rules (`tests/test_runtime_generated_payload.py`)
6. Writes to Supabase `innovex_lc(company_name, company_json)`

## Output

Result JSON is written to `output/{company}_result.json` and includes:
- `status`
- `company_name`
- `company_json` (10 fields)
- `comparison`
- `validation_report`
- `database_id`
