import json
import pandas as pd
from src.schemas import ExtractorOutput, InterpreterOutput
from src.llm import load_prompt, call_llm, parse_json_response
from src.loader import serialize_dataframe

CHUNK_SIZE = 2


async def _interpret_chunk(
    system_prompt: str,
    chunk: list[dict],
    baseline_text: str,
) -> list[dict]:
    extractions_json = json.dumps(chunk, ensure_ascii=False)
    user_content = (
        "## Extractor Outputs\n"
        f"{extractions_json}\n\n"
        "## Baseline Data (Day 1 Context)\n"
        f"{baseline_text}"
    )
    raw = await call_llm(system_prompt, user_content, max_tokens=2048)
    try:
        data = parse_json_response(raw)
    except Exception as e:
        print(f"  [Interpreter] JSON parse failed ({e}), skipping chunk")
        return []
    if isinstance(data, list):
        return data
    return data.get("reconciled_findings", [])


async def interpret(
    extractor_outputs: list[ExtractorOutput],
    baseline_sheets: dict[str, pd.DataFrame],
) -> InterpreterOutput:
    system_prompt = load_prompt("interpreter.md")
    compact = [
        {
            "sheet_name": eo.sheet_name,
            "findings": [{"datetime": f.datetime, "content": f.content, "category": f.category} for f in eo.findings],
        }
        for eo in extractor_outputs if eo.findings
    ]
    baseline_parts = []
    for name, df in baseline_sheets.items():
        if not df.empty:
            baseline_parts.append(serialize_dataframe(df, name))
    baseline_text = "\n\n".join(baseline_parts) if baseline_parts else "No baseline data available."
    all_findings = []
    chunks = [compact[i:i + CHUNK_SIZE] for i in range(0, len(compact), CHUNK_SIZE)]
    print(f"  [Interpreter] Processing {len(compact)} sheets in {len(chunks)} chunk(s)")
    for idx, chunk in enumerate(chunks, 1):
        sheet_names = [c["sheet_name"] for c in chunk]
        print(f"  [Interpreter] Chunk {idx}/{len(chunks)}: {sheet_names}")
        findings = await _interpret_chunk(system_prompt, chunk, baseline_text)
        all_findings.extend(findings)
    total_input = sum(len(eo.findings) for eo in extractor_outputs)
    data = {
        "reconciled_findings": all_findings,
        "conflicts_resolved": [],
        "duplicates_removed": 0,
        "metadata": {
            "total_input_findings": total_input,
            "total_output_findings": len(all_findings),
        },
    }
    return InterpreterOutput.model_validate(data)
