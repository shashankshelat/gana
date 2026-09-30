import json
import logging
from typing import Optional

from app.core.schema_manager import schema_manager

logger = logging.getLogger(__name__)

AI_PROVIDERS = {
    "claude": {
        "display_name": "Anthropic Claude",
        "models": ["claude-opus-5-5", "claude-sonnet-5-5", "claude-haiku-4-5"],
        "default_model": "claude-opus-5-5",
    },
    "openai": {
        "display_name": "OpenAI ChatGPT",
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
        "default_model": "gpt-4o",
    },
    "gemini": {
        "display_name": "Google Gemini",
        "models": ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.0-flash"],
        "default_model": "gemini-1.5-pro",
    },
}


def _ocsf_class_catalog() -> str:
    classes = sorted(schema_manager._iter_classes(), key=lambda c: c.get("uid", 0))
    if not classes:
        return "  (class list not loaded; use standard OCSF class uids)"
    return "\n".join(f"  {c.get('uid')}: {c.get('caption') or c.get('name')} ({c.get('category_name', '')})" for c in classes)


def _build_prompt(sample_logs: str, connector_type: str, ocsf_class_uid: int) -> str:
    # Filled by schema_manager.get_class_attributes, which the async entry points call first
    ocsf_fields = schema_manager.get_ocsf_class_fields(ocsf_class_uid)

    schema_hint = "\n".join(f"  - {f}" for f in ocsf_fields[:80]) if ocsf_fields else "  (schema not loaded)"

    return f"""You are an expert in the Open Cybersecurity Schema Framework (OCSF).

I have sample log events from a "{connector_type}" source. The OCSF class must be chosen per event, from what
each event describes; do not force every event into one class. Your task is to:
1. Find the field that distinguishes event types (e.g. eventType, type, action, event.name) and group the samples by it.
2. Give each group a route: the most specific OCSF class and activity_id for that kind of event (e.g. a login is
   Authentication 3002 / Logon 1; a password reset is Account Change 3001 / Password Reset 4; adding a user to a
   group is Group Management 3006 / Add User 3; a configuration change is Entity Management 3004 / Update 3).
3. For each route, map source fields to that class's OCSF attributes.
4. Also give fallback mapping rules for events that match no route, and a default_class_uid for them
   (use 0 = Base Event when they don't clearly fit a class).
5. Identify source fields with NO suitable OCSF equivalent, and explain your decisions briefly.

## OCSF classes (uid: name):
{_ocsf_class_catalog()}

## Attributes of class {ocsf_class_uid}, this source's usual class (for reference; other classes have their own):
{schema_hint}

## Sample Logs:
```
{sample_logs[:4000]}
```

## Response Format (return ONLY valid JSON, no markdown, no extra text):
{{
  "mapping": {{
    "time": "timestamp",
    "actor.user.name": "user.login",
    "_default_class_uid": 0,
    "_routes": [
      {{
        "name": "logon",
        "when": {{"field": "eventType", "in": ["user.session.start"]}},
        "class_uid": 3002,
        "mapping": {{"activity_id": "$const:1", "activity_name": "$const:Logon", "time": "timestamp",
                     "user.name": "user.login", "src_endpoint.ip": "client_ip"}}
      }}
    ]
  }},
  "unknown_fields": [
    {{
      "field_name": "custom_vendor_field",
      "field_path": "metadata.vendor_specific.custom_field",
      "sample_values": ["value1", "value2"],
      "description": "Vendor-specific field with no OCSF equivalent. Represents X.",
      "suggested_ocsf_path": "unmapped.custom_vendor_field"
    }}
  ],
  "explanation": "Brief explanation of the event types found, the class chosen for each, and key mapping decisions."
}}

Rules:
- Use dot notation for nested paths (e.g. actor.user.name); list items as items[0].name or items[type=User].name
- Use $const:VALUE for static constant values
- A route's "when" uses "equals": value, "in": [values], or "prefix": [value prefixes]; the first matching route wins
- Every route sets activity_id and activity_name as constants from its class's activity list
- A route's rules REPLACE the fallback rules for matching events, so each route must be complete on its own:
  include time, actor/user, source endpoint, status and severity rules in every route where the data exists
- Only map fields where you are reasonably confident
- List in unknown_fields any source field that doesn't fit any OCSF field
- For timestamps, always map to "time" (OCSF epoch_ms)
- For the severity field, map to a 0-6 integer scale (0=Unknown,1=Informational,2=Low,3=Medium,4=High,5=Critical)"""


def _build_fix_prompt(
    failed_events: list[dict], errors: list[str], current_mapping: dict, connector_type: str, ocsf_class_uid: int,
    reason: str = "failed",
) -> str:
    base = _build_prompt(json.dumps(failed_events[:10], indent=2, default=str), connector_type, ocsf_class_uid)
    intro, fmt = base.split("## Response Format", 1)
    error_list = "\n".join(f"  - {e}" for e in sorted(set(errors))[:10]) or "  (no error message recorded)"
    why = (
        "These sample logs FAILED in the pipeline and were sent to the dead-letter queue. The errors were:\n" + error_list
        if reason == "failed" else
        "An analyst provided these sample logs from the source so the mapping can cover them. Extend the "
        "current mapping (add or adjust routes) so each event type maps to the right OCSF class."
    )
    return f"""{intro}## Why these events are here
{why}

The connector's CURRENT mapping (OCSF path -> source path) is:
```
{json.dumps(current_mapping, indent=1)[:30000]}
```

Produce a corrected mapping that would let these events map cleanly:
- Return the COMPLETE mapping, not just the changes: approving it replaces the current mapping.
- Keep existing rules and routes that are correct; fix or remove ones that don't match these events' structure.
- If these events are a type no route covers, add a route for them with the right OCSF class and activity.
- If the connector has no mapping yet, build one from scratch.
- If the error is not caused by the mapping (e.g. an internal code error), keep the mapping as-is and say so in the explanation.
- In the explanation, state what you changed and why, referencing the errors above.

## Response Format{fmt}"""


# Structured-output schema for Claude. Objects need fixed keys, so the mapping (an arbitrary-key
# dict elsewhere in the app) is returned as a list of rules and converted back in _rules_to_mapping.
_RULE_LIST_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "ocsf_path": {"type": "string"},
            "source": {"type": "string"},
            "transform": {"type": "string", "enum": ["", "lower", "upper", "int", "str", "bool", "epoch_ms", "list"]},
        },
        "required": ["ocsf_path", "source", "transform"],
        "additionalProperties": False,
    },
}

_CLAUDE_MAPPING_SCHEMA = {
    "type": "object",
    "properties": {
        "routes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "field": {"type": "string"},
                    "match": {"type": "string", "enum": ["equals", "in", "prefix"]},
                    "values": {"type": "array", "items": {"type": "string"}},
                    "class_uid": {"type": "integer"},
                    "activity_id": {"type": "integer"},
                    "activity_name": {"type": "string"},
                    "mapping_rules": _RULE_LIST_SCHEMA,
                },
                "required": ["name", "field", "match", "values", "class_uid", "activity_id", "activity_name", "mapping_rules"],
                "additionalProperties": False,
            },
        },
        "default_class_uid": {"type": "integer"},
        "mapping_rules": _RULE_LIST_SCHEMA,
        "unknown_fields": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "field_name": {"type": "string"},
                    "field_path": {"type": "string"},
                    "sample_values": {"type": "array", "items": {"type": "string"}},
                    "description": {"type": "string"},
                    "suggested_ocsf_path": {"type": "string"},
                },
                "required": ["field_name", "field_path", "sample_values", "description", "suggested_ocsf_path"],
                "additionalProperties": False,
            },
        },
        "explanation": {"type": "string"},
    },
    "required": ["routes", "default_class_uid", "mapping_rules", "unknown_fields", "explanation"],
    "additionalProperties": False,
}

_CLAUDE_FORMAT_NOTE = """## Response format
Return routes (one per event type or family, each with its own class_uid, activity and mapping_rules),
default_class_uid for events matching no route (0 = Base Event if unsure), and fallback mapping_rules.
A route matches when its field "equals" values[0], is "in" values, or starts with one of values ("prefix").
Route rules replace the fallback rules, so give every route complete rules (time, actor/user, endpoint, status).
Each mapping rule has:
- ocsf_path: the OCSF field in dot notation (e.g. actor.user.name)
- source: the source field path in dot notation (list items as items[0].name or items[type=User].name),
  or $const:VALUE for a constant
- transform: "" for none, or one of lower, upper, int, str, bool, epoch_ms, list (wrap a value for array attributes)"""

# Models that accept the server-side refusal fallback and effort settings
_CLAUDE_FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}


def _rules_to_mapping(rules: list[dict]) -> dict:
    mapping = {}
    for r in rules:
        path, source = r.get("ocsf_path", "").strip(), r.get("source", "").strip()
        if not path or not source:
            continue
        mapping[path] = {"path": source, "transform": r["transform"]} if r.get("transform") else source
    return mapping


async def _call_claude(prompt: str, model: str, api_key: str) -> str:
    import anthropic

    # Claude gets a schema instead of the free-form JSON instructions used for other providers
    if "## Response Format" in prompt:
        prompt = prompt[:prompt.index("## Response Format")] + _CLAUDE_FORMAT_NOTE

    client = anthropic.AsyncAnthropic(api_key=api_key)
    kwargs = dict(
        model=model,
        max_tokens=16000,
        messages=[{"role": "user", "content": prompt}],
        output_config={"format": {"type": "json_schema", "schema": _CLAUDE_MAPPING_SCHEMA}},
    )
    if model in _CLAUDE_FALLBACK_MODELS:
        # Mapping quality matters more than latency; Opus 5.5 would otherwise default to medium
        kwargs["output_config"]["effort"] = "high"
        # If a safety classifier declines, the API re-runs the request on a suitable fallback model
        message = await client.beta.messages.create(
            betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs,
        )
    else:
        message = await client.messages.create(**kwargs)

    if message.stop_reason == "refusal":
        raise ValueError("The AI model declined to generate a mapping for these logs")
    if message.stop_reason == "max_tokens":
        raise ValueError("AI response was cut off (max_tokens); try fewer or smaller sample events")

    text = next(b.text for b in message.content if b.type == "text")
    data = json.loads(text)
    mapping = _rules_to_mapping(data["mapping_rules"])
    routes = []
    for r in data["routes"]:
        values = r["values"]
        when = {"field": r["field"]}
        if r["match"] == "prefix":
            when["prefix"] = values
        elif r["match"] == "equals" and len(values) == 1:
            when["equals"] = values[0]
        else:
            when["in"] = values
        routes.append({
            "name": r["name"], "when": when, "class_uid": r["class_uid"],
            "mapping": {"activity_id": f"$const:{r['activity_id']}", "activity_name": f"$const:{r['activity_name']}",
                        **_rules_to_mapping(r["mapping_rules"])},
        })
    if routes:
        mapping["_routes"] = routes
    mapping["_default_class_uid"] = data["default_class_uid"]
    return json.dumps({
        "mapping": mapping,
        "unknown_fields": data["unknown_fields"],
        "explanation": data["explanation"],
    })


async def _call_openai(prompt: str, model: str, api_key: str) -> str:
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key)
    response = await client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": "You are an OCSF schema expert. Always respond with valid JSON only."},
            {"role": "user", "content": prompt},
        ],
        max_tokens=4096,
        response_format={"type": "json_object"},
    )
    return response.choices[0].message.content


async def _call_gemini(prompt: str, model: str, api_key: str) -> str:
    import google.generativeai as genai
    genai.configure(api_key=api_key)
    gemini_model = genai.GenerativeModel(
        model_name=model,
        generation_config={"response_mime_type": "application/json"},
    )
    response = await gemini_model.generate_content_async(prompt)
    return response.text


async def generate_mapping(
    sample_logs: str,
    connector_type: str,
    ocsf_class_uid: int,
    provider: str,
    model: str,
    api_key: str,
) -> dict:
    await schema_manager.get_class_attributes(ocsf_class_uid)
    prompt = _build_prompt(sample_logs, connector_type, ocsf_class_uid)
    return await _run_mapping_prompt(prompt, ocsf_class_uid, provider, model, api_key)


async def generate_mapping_fix(
    failed_events: list[dict],
    errors: list[str],
    current_mapping: dict,
    connector_type: str,
    ocsf_class_uid: int,
    provider: str,
    model: str,
    api_key: str,
    reason: str = "failed",
) -> dict:
    """Propose a corrected, complete mapping for failed DLQ events (reason="failed") or analyst samples."""
    await schema_manager.get_class_attributes(ocsf_class_uid)
    prompt = _build_fix_prompt(failed_events, errors, current_mapping, connector_type, ocsf_class_uid, reason)
    return await _run_mapping_prompt(prompt, ocsf_class_uid, provider, model, api_key)


async def _run_mapping_prompt(prompt: str, ocsf_class_uid: int, provider: str, model: str, api_key: str) -> dict:
    raw_response = ""
    try:
        if provider == "claude":
            raw_response = await _call_claude(prompt, model, api_key)
        elif provider == "openai":
            raw_response = await _call_openai(prompt, model, api_key)
        elif provider == "gemini":
            raw_response = await _call_gemini(prompt, model, api_key)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        raw_response = raw_response.strip()
        if raw_response.startswith("```"):
            lines = raw_response.split("\n")
            raw_response = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        result = json.loads(raw_response)

        if "mapping" not in result:
            result["mapping"] = {}
        if "unknown_fields" not in result:
            result["unknown_fields"] = []
        if "explanation" not in result:
            result["explanation"] = ""
        result["ocsf_class_uid"] = ocsf_class_uid

        warnings = []
        for route in result["mapping"].get("_routes") or []:
            uid = route.get("class_uid")
            if isinstance(uid, int) and await schema_manager.get_class_attributes(uid):
                _, bad = validate_mapping_against_schema(route.get("mapping") or {}, uid)
                bad = [b for b in bad if b not in ("activity_id", "activity_name")]
                if bad:
                    warnings.append(f"route {route.get('name')}: not attributes of class {uid}: {', '.join(bad[:8])}")
        if warnings:
            result["explanation"] = (result["explanation"] + "\n\nSchema check: " + "; ".join(warnings)).strip()

        return result

    except json.JSONDecodeError as e:
        logger.error("AI response was not valid JSON: %s\nRaw: %s", e, raw_response[:500])
        raise ValueError(f"AI returned invalid JSON: {e}. Raw response: {raw_response[:200]}")
    except Exception as e:
        logger.error("AI mapping call failed (%s/%s): %s", provider, model, e)
        raise


def validate_mapping_against_schema(mapping: dict, ocsf_class_uid: int) -> tuple[list[str], list[str]]:
    valid_fields = set(schema_manager.get_ocsf_class_fields(ocsf_class_uid))
    if not valid_fields:
        return [], []

    mapped_fields = [k for k in mapping.keys() if not k.startswith(("$", "_"))]
    known = []
    unknown = []
    for field in mapped_fields:
        top_level = field.split(".")[0]
        if top_level in valid_fields or field in valid_fields:
            known.append(field)
        else:
            unknown.append(field)

    return known, unknown
