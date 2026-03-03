import json
import re
from src.schemas import ValidatorOutput, GeneratorOutput
from src.llm import load_prompt, call_llm


async def generate(validator_output: ValidatorOutput) -> GeneratorOutput:
    system_prompt = load_prompt("generator.md")
    user_content = json.dumps(validator_output.model_dump(), ensure_ascii=False, indent=2)
    raw = await call_llm(system_prompt, user_content)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL)
    raw = re.sub(r"<think>.*", "", raw, flags=re.DOTALL)
    summary = raw.strip()
    return GeneratorOutput.model_validate({
        "summary": summary,
        "metadata": {"total_findings_used": len(validator_output.validated_findings)},
    })
