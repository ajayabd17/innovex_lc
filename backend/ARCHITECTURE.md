# Multi-LLM Enterprise Intelligence Engine

## Enforced 5-Step Flow

1. Input `company_name`
2. Run configured generation providers (default: `fireworks`, `groq`, `baseten`) and enforce success quorum
3. If at least 2 providers succeed, run 4th consolidation LLM to produce one reconciled 10-field JSON
4. Validate with Pydantic against exact canonical 10-field contract
5. Insert into Supabase `innovex_lc` as (`company_name`, `company_json`)

## Contract Guarantees

- Canonical output contract is exactly 10 fields.
- Any missing/extra key fails generation/consolidation validation.
- `company_id` is internal and excluded from stored output payload.
- `cross_field_rules.json` remains in repo but is non-blocking for the main 5-step path.

## Main Components

- `main.py`: strict 5-step orchestration
- `orchestration/generator.py`: parallel generation with strict 3/3 + shape checks
- `orchestration/consolidator.py`: 4th-LLM reconciliation with strict shape checks
- `validators/pydantic_model.py`: exact key validation + strict Pydantic model
- `database/db_writer.py`: Supabase writer for `innovex_lc`
