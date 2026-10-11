from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas import AIPlanTask


class GeminiPlanOutput(BaseModel):
    tasks: list[AIPlanTask] = Field(min_length=1, max_length=12)


def generate_gemini_plan(
    *,
    api_key: str,
    model: str,
    goal: str,
    current_time: datetime,
    timezone_name: str,
) -> GeminiPlanOutput:
    """Ask Gemini for a structured task proposal; this function never writes data."""
    from google import genai
    from google.genai import types

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=30_000),
    )
    prompt = f"""Create a practical task plan for this goal.

Return 3 to 6 ordered tasks when the goal needs multiple steps, otherwise return
the smallest useful plan. Every task must have a concise title, an optional
short description, and a priority of low, medium, or high. Set due_at to an
ISO 8601 date-time with an explicit UTC offset when the user states a deadline;
use null when no deadline is stated. Use the supplied timezone for every date.
For a day part such as 'tomorrow afternoon' without a clock time, use 3:00 PM
in the supplied timezone. Schedule intermediate steps before the final deadline.
Create tasks only. Do not propose or execute email, calendar, or other actions.

Current local time: {current_time.isoformat()}
Timezone: {timezone_name}

User goal:
<goal>
{goal}
</goal>"""

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=GeminiPlanOutput,
            max_output_tokens=2048,
            thinking_config=types.ThinkingConfig(thinking_level="low"),
        ),
    )
    if not response.text:
        raise ValueError("Gemini returned an empty plan.")
    return GeminiPlanOutput.model_validate_json(response.text)
