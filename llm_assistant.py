"""LLM Assistant for literature review screening using Ollama."""

import json
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from ollama import AsyncClient

from db_schema import DB_PATH


@dataclass
class LLMSuggestion:
    """Represents an LLM suggestion for a paper."""

    decision: str  # 'include', 'exclude', 'uncertain'
    reasoning: str
    confidence: float
    exclusion_codes: list[str] = field(default_factory=list)
    raw_response: str = ""
    error: str | None = None
    log_id: int | None = None  # Reference to llm_request_log.id
    domain: str | None = None  # 'health' or 'ecological'
    # Metadata from the LLM run
    model: str | None = None
    thinking_mode: bool | None = None
    response_time_ms: int | None = None
    requested_at: str | None = None  # ISO format timestamp


def get_active_prompts(db_path: Path = DB_PATH) -> dict[str, tuple[int, str]]:
    """Load most recent version of each prompt from database.

    Returns: {prompt_name: (version_id, content)}
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get the latest version of each prompt
    cursor.execute("""
        SELECT pv.id, pv.prompt_name, pv.content
        FROM prompt_version pv
        INNER JOIN (
            SELECT prompt_name, MAX(id) as max_id
            FROM prompt_version
            GROUP BY prompt_name
        ) latest ON pv.id = latest.max_id
    """)

    prompts = {}
    for row in cursor.fetchall():
        prompts[row['prompt_name']] = (row['id'], row['content'])

    conn.close()
    return prompts


def log_llm_request(
    db_path: Path,
    document_id: int,
    pass_number: int,
    model: str,
    thinking_mode: bool,
    prompt_ids: dict[str, int],
    full_system_prompt: str,
    full_user_prompt: str,
    suggestion: LLMSuggestion,
    response_time_ms: int,
) -> int:
    """Log LLM request to database and return log ID."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Serialize exclusion codes as JSON
    exclusion_codes_json = json.dumps(suggestion.exclusion_codes) if suggestion.exclusion_codes else None

    cursor.execute("""
        INSERT INTO llm_request_log (
            document_id, pass_number, model, thinking_mode,
            system_prompt_id, inclusion_criteria_id, exclusion_criteria_id, user_prompt_id,
            full_system_prompt, full_user_prompt, raw_response,
            decision, confidence, reasoning, exclusion_codes, domain, error, response_time_ms
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        document_id,
        pass_number,
        model,
        int(thinking_mode),
        prompt_ids.get('system_prompt', 0),
        prompt_ids.get('inclusion_criteria', 0),
        prompt_ids.get('exclusion_criteria', 0),
        prompt_ids.get('user_prompt', 0),
        full_system_prompt,
        full_user_prompt,
        suggestion.raw_response,
        suggestion.decision if not suggestion.error else None,
        suggestion.confidence if not suggestion.error else None,
        suggestion.reasoning if not suggestion.error else None,
        exclusion_codes_json,
        suggestion.domain if not suggestion.error else None,
        suggestion.error,
        response_time_ms,
    ))

    conn.commit()
    log_id = cursor.lastrowid
    conn.close()
    return log_id


def _build_paper_metadata(
    title: str,
    year: str | None,
    keywords: str | None,
    venue: str | None,
    abstract: str | None = None,
) -> str:
    """Build paper metadata string for prompt."""
    parts = [f"Title: {title}"]
    if year:
        parts.append(f"Year: {year}")
    if keywords:
        parts.append(f"Keywords: {keywords}")
    if venue:
        parts.append(f"Venue: {venue}")
    if abstract is not None:
        if abstract:
            parts.append(f"\nAbstract:\n{abstract}")
        else:
            parts.append("\nAbstract: Not available")
    return "\n".join(parts)


def _parse_llm_response(response: str) -> dict[str, Any]:
    """Parse LLM response, handling potential formatting issues."""
    # Try to extract JSON from the response
    text = response.strip()

    # Remove markdown code blocks if present
    if text.startswith("```"):
        lines = text.split("\n")
        # Find the JSON content between code blocks
        json_lines = []
        in_block = False
        for line in lines:
            if line.startswith("```") and not in_block:
                in_block = True
                continue
            elif line.startswith("```") and in_block:
                break
            elif in_block:
                json_lines.append(line)
        text = "\n".join(json_lines)

    # Try to find JSON object in the text
    start = text.find("{")
    end = text.rfind("}") + 1
    if start != -1 and end > start:
        text = text[start:end]

    return json.loads(text)


# Fallback prompts (used when database has no prompts)
FALLBACK_INCLUSION_CRITERIA = """
INC.1: Peer-reviewed publication
INC.2: Published 2022-2025
INC.3: Custom development (not COTS-assembled)
INC.4: Embedded wireless sensing (~<=100mW, microprocessor-based)
INC.5: In-situ deployment (real-world, situated)
INC.6: Health or ecology domain
INC.7: Target specificity (specific population or environmental context)
"""

FALLBACK_EXCLUSION_CRITERIA = """
EX.1: High-power processing (video, audio, RF requiring ~>=500mW)
EX.2: COTS-primary (smartphones, smartwatches, commercial devices)
EX.3: Out-of-scope platforms (vehicles, UAVs, drones)
EX.4: Out-of-scope applications (VR/AR, entertainment, general-purpose tech)
EX.5: Application-agnostic (no targeted application, e.g., wireless security)
"""

FALLBACK_SYSTEM_PROMPT = """You are an expert research assistant helping with a systematic literature review.
The review focuses on embedded wireless sensing systems for health monitoring or ecological applications.

Your task is to screen papers based on their title, metadata, and (when available) abstract.

INCLUSION CRITERIA (paper must meet ALL of these):
{inclusion_criteria}

EXCLUSION CRITERIA (paper is excluded if it matches ANY of these):
{exclusion_criteria}

IMPORTANT GUIDELINES:
- Give benefit of the doubt: Only exclude if clearly out of scope
- When uncertain, choose "uncertain" to defer to human review
- For Pass 1 (title/metadata only), be more lenient since you lack the abstract
- For Pass 2 (with abstract), you can make more confident decisions

Respond ONLY with valid JSON in this exact format:
{{
  "decision": "include|exclude|uncertain",
  "confidence": 0.0-1.0,
  "reasoning": "Brief explanation (1-2 sentences)",
  "exclusion_codes": ["EX.1"]
}}

The exclusion_codes array should only be populated if decision is "exclude".
Use the codes from the exclusion criteria list above."""

FALLBACK_PASS1_USER_PROMPT = """PASS 1 SCREENING (Title and Metadata Only)

Paper Information:
{paper_metadata}

Note: In Pass 1, you only have the title and metadata. Be lenient - if there's any chance
the paper could be relevant based on this limited information, mark it as "include" or "uncertain".
Only exclude if clearly out of scope.

Provide your assessment as JSON:"""

FALLBACK_PASS2_USER_PROMPT = """PASS 2 SCREENING (Full Metadata with Abstract)

Paper Information:
{paper_metadata}

Now that you have the abstract, you can make a more informed decision.
Still give benefit of the doubt, but you can be more confident in exclusions
if the abstract clearly indicates the paper is out of scope.

Provide your assessment as JSON:"""


class LLMAssistant:
    """Handles LLM interactions for paper screening."""

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "qwen3:8b",
        db_path: Path = DB_PATH,
    ):
        self.host = host
        self.model = model
        self.db_path = db_path
        self.client = AsyncClient(host=host)

    def _get_prompts(self) -> tuple[dict[str, tuple[int, str]], dict[str, str]]:
        """Get prompts from database or fallback.

        Returns: (prompt_ids, prompt_contents)
            prompt_ids: {prompt_name: version_id} (0 for fallback)
            prompt_contents: {prompt_name: content}
        """
        db_prompts = get_active_prompts(self.db_path)

        prompt_ids = {}
        prompt_contents = {}

        # System prompt
        if 'system_prompt' in db_prompts:
            prompt_ids['system_prompt'] = db_prompts['system_prompt'][0]
            prompt_contents['system_prompt'] = db_prompts['system_prompt'][1]
        else:
            prompt_ids['system_prompt'] = 0
            prompt_contents['system_prompt'] = FALLBACK_SYSTEM_PROMPT

        # Inclusion criteria
        if 'inclusion_criteria' in db_prompts:
            prompt_ids['inclusion_criteria'] = db_prompts['inclusion_criteria'][0]
            prompt_contents['inclusion_criteria'] = db_prompts['inclusion_criteria'][1]
        else:
            prompt_ids['inclusion_criteria'] = 0
            prompt_contents['inclusion_criteria'] = FALLBACK_INCLUSION_CRITERIA

        # Exclusion criteria
        if 'exclusion_criteria' in db_prompts:
            prompt_ids['exclusion_criteria'] = db_prompts['exclusion_criteria'][0]
            prompt_contents['exclusion_criteria'] = db_prompts['exclusion_criteria'][1]
        else:
            prompt_ids['exclusion_criteria'] = 0
            prompt_contents['exclusion_criteria'] = FALLBACK_EXCLUSION_CRITERIA

        # Pass 1 user prompt
        if 'pass1_user_prompt' in db_prompts:
            prompt_ids['pass1_user_prompt'] = db_prompts['pass1_user_prompt'][0]
            prompt_contents['pass1_user_prompt'] = db_prompts['pass1_user_prompt'][1]
        else:
            prompt_ids['pass1_user_prompt'] = 0
            prompt_contents['pass1_user_prompt'] = FALLBACK_PASS1_USER_PROMPT

        # Pass 2 user prompt
        if 'pass2_user_prompt' in db_prompts:
            prompt_ids['pass2_user_prompt'] = db_prompts['pass2_user_prompt'][0]
            prompt_contents['pass2_user_prompt'] = db_prompts['pass2_user_prompt'][1]
        else:
            prompt_ids['pass2_user_prompt'] = 0
            prompt_contents['pass2_user_prompt'] = FALLBACK_PASS2_USER_PROMPT

        return prompt_ids, prompt_contents

    async def suggest_pass1(
        self,
        document_id: int,
        title: str,
        year: str | None = None,
        keywords: str | None = None,
        venue: str | None = None,
        thinking_mode: bool = True,
    ) -> LLMSuggestion:
        """Get LLM suggestion for Pass 1 screening (title/metadata only)."""
        paper_metadata = _build_paper_metadata(title, year, keywords, venue)
        return await self._get_suggestion(
            document_id=document_id,
            pass_number=1,
            paper_metadata=paper_metadata,
            thinking_mode=thinking_mode,
        )

    async def suggest_pass2(
        self,
        document_id: int,
        title: str,
        year: str | None = None,
        keywords: str | None = None,
        venue: str | None = None,
        abstract: str | None = None,
        thinking_mode: bool = True,
    ) -> LLMSuggestion:
        """Get LLM suggestion for Pass 2 screening (with abstract)."""
        paper_metadata = _build_paper_metadata(title, year, keywords, venue, abstract)
        return await self._get_suggestion(
            document_id=document_id,
            pass_number=2,
            paper_metadata=paper_metadata,
            thinking_mode=thinking_mode,
        )

    async def _get_suggestion(
        self,
        document_id: int,
        pass_number: int,
        paper_metadata: str,
        thinking_mode: bool,
    ) -> LLMSuggestion:
        """Send prompt to LLM and parse response."""
        prompt_ids, prompt_contents = self._get_prompts()

        # Build full system prompt
        full_system_prompt = prompt_contents['system_prompt'].format(
            inclusion_criteria=prompt_contents['inclusion_criteria'],
            exclusion_criteria=prompt_contents['exclusion_criteria'],
        )

        # Build full user prompt
        user_prompt_template = (
            prompt_contents['pass1_user_prompt']
            if pass_number == 1
            else prompt_contents['pass2_user_prompt']
        )
        full_user_prompt = user_prompt_template.format(paper_metadata=paper_metadata)

        # Set up prompt IDs for logging
        log_prompt_ids = {
            'system_prompt': prompt_ids['system_prompt'],
            'inclusion_criteria': prompt_ids['inclusion_criteria'],
            'exclusion_criteria': prompt_ids['exclusion_criteria'],
            'user_prompt': prompt_ids['pass1_user_prompt' if pass_number == 1 else 'pass2_user_prompt'],
        }

        # Add thinking mode tag if enabled (Qwen3 specific)
        llm_user_prompt = full_user_prompt
        if thinking_mode:
            llm_user_prompt = "/think\n" + llm_user_prompt
        else:
            llm_user_prompt = "/no_think\n" + llm_user_prompt

        start_time = time.time()
        requested_at = datetime.now().isoformat()
        raw_response = ""

        try:
            response = await self.client.chat(
                model=self.model,
                messages=[
                    {"role": "system", "content": full_system_prompt},
                    {"role": "user", "content": llm_user_prompt},
                ],
            )

            raw_response = response["message"]["content"]
            response_time_ms = int((time.time() - start_time) * 1000)

            # Parse the JSON response
            parsed = _parse_llm_response(raw_response)

            # Parse domain, normalizing to allowed values
            domain = parsed.get("domain")
            if domain not in ("health", "ecological"):
                domain = None

            suggestion = LLMSuggestion(
                decision=parsed.get("decision", "uncertain"),
                reasoning=parsed.get("reasoning", ""),
                confidence=float(parsed.get("confidence", 0.5)),
                exclusion_codes=parsed.get("exclusion_codes", []),
                raw_response=raw_response,
                domain=domain,
                model=self.model,
                thinking_mode=thinking_mode,
                response_time_ms=response_time_ms,
                requested_at=requested_at,
            )

        except json.JSONDecodeError as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            suggestion = LLMSuggestion(
                decision="uncertain",
                reasoning="",
                confidence=0.0,
                raw_response=raw_response,
                error=f"Failed to parse LLM response as JSON: {e}",
                model=self.model,
                thinking_mode=thinking_mode,
                response_time_ms=response_time_ms,
                requested_at=requested_at,
            )

        except Exception as e:
            response_time_ms = int((time.time() - start_time) * 1000)
            suggestion = LLMSuggestion(
                decision="uncertain",
                reasoning="",
                confidence=0.0,
                error=f"LLM request failed: {e}",
                model=self.model,
                thinking_mode=thinking_mode,
                response_time_ms=response_time_ms,
                requested_at=requested_at,
            )

        # Log the request
        try:
            log_id = log_llm_request(
                db_path=self.db_path,
                document_id=document_id,
                pass_number=pass_number,
                model=self.model,
                thinking_mode=thinking_mode,
                prompt_ids=log_prompt_ids,
                full_system_prompt=full_system_prompt,
                full_user_prompt=full_user_prompt,
                suggestion=suggestion,
                response_time_ms=response_time_ms,
            )
            suggestion.log_id = log_id
        except Exception as log_error:
            # Don't fail if logging fails, just note it
            if suggestion.error:
                suggestion.error += f"; Logging failed: {log_error}"
            else:
                suggestion.error = f"Logging failed: {log_error}"

        return suggestion

    async def test_connection(self) -> tuple[bool, str]:
        """Test connection to Ollama server."""
        try:
            # Try to list models to verify connection
            models = await self.client.list()
            model_list = models.get("models", [])
            model_names = [m.get("name", m.get("model", "")) for m in model_list]

            if self.model in model_names or any(self.model in m for m in model_names):
                return True, f"Connected. Model '{self.model}' available."
            else:
                available = ", ".join(model_names) if model_names else "none"
                return False, f"Connected but model '{self.model}' not found. Available: {available}"
        except Exception as e:
            return False, f"Connection failed: {e}"
