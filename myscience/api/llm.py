import json
import logging
from typing import Any, Dict

import requests
from django.conf import settings


logger = logging.getLogger(__name__)


class LLMServiceError(Exception):
    pass


def _build_messages(criteria_text: str, article_context: Dict[str, Any]) -> list[dict[str, str]]:
    article_json = json.dumps(article_context, ensure_ascii=False)
    system_prompt = (
        "You are an assistant for systematic literature review screening.\n"
        "Use the PRISMA inclusion criteria and article metadata/abstract to recommend one of: include, exclude, uncertain.\n"
        "Return ONLY valid JSON with keys: recommendation, rationale.\n"
        "recommendation must be exactly one of: include, exclude, uncertain."
    )
    user_prompt = (
        f"Project inclusion criteria (PRISMA 2020):\n{criteria_text}\n\n"
        f"Article data:\n{article_json}\n\n"
        "Provide recommendation and concise rationale in JSON."
    )
    return [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt},
    ]


def _build_project_inclusion_messages(title: str, description: str = '') -> list[dict[str, str]]:
    system_prompt = (
        "You are a senior systematic review methodologist.\n"
        "Your task is to draft a high-quality proposal for Inclusion Criteria aligned with PRISMA 2020.\n"
        "Infer a reasonable review scope from the project title and optional description, but do not invent narrow facts.\n"
        "Write in Spanish.\n"
        "Return plain text only, with no code fences.\n"
        "Structure the answer as:\n"
        "Inclusion Criteria (PRISMA 2020):\n"
        "- Review focus\n"
        "- Population/Problem\n"
        "- Intervention/Exposure or phenomenon of interest\n"
        "- Comparator/Context when applicable\n"
        "- Outcomes\n"
        "- Study designs\n"
        "- Setting and language\n"
        "- Publication date range\n"
        "- Publication type / peer review\n"
        "- Data/reporting requirements\n"
        "Keep each bullet specific, useful, and editable by a researcher."
    )
    description_block = f"\nDescripción opcional del proyecto:\n{description.strip()}" if description.strip() else ''
    user_prompt = (
        f"Título del proyecto:\n{title.strip()}{description_block}\n\n"
        "Redacta una propuesta inicial de criterios de inclusión basada en PRISMA 2020. "
        "Debe ser práctica, clara y suficientemente estructurada para revisar y editar después."
    )
    return [
        {'role': 'system', 'content': system_prompt},
        {'role': 'user', 'content': user_prompt},
    ]


def _normalize_recommendation(value: str) -> str:
    val = (value or '').strip().lower()
    if val in {'include', 'incluir'}:
        return 'include'
    if val in {'exclude', 'excluir'}:
        return 'exclude'
    return 'uncertain'


def _extract_json(text: str) -> Dict[str, Any]:
    if not text:
        return {}
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        return {}
    chunk = text[start:end + 1]
    try:
        return json.loads(chunk)
    except Exception:
        return {}


def _parse_llm_result(raw_text: str) -> Dict[str, str]:
    parsed = _extract_json(raw_text)
    recommendation = _normalize_recommendation(parsed.get('recommendation', ''))
    rationale = (parsed.get('rationale') or '').strip()
    if not rationale:
        rationale = raw_text.strip()[:1200]
    return {
        'recommendation': recommendation,
        'rationale': rationale,
    }


def _clean_text_response(text: str) -> str:
    value = (text or '').strip()
    if value.startswith('```'):
        lines = value.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == '```':
            value = '\n'.join(lines[1:-1]).strip()
    return value


def _request_openai_text_completion(
    messages: list[dict[str, str]],
    temperature: float = 0.1,
) -> Dict[str, Any]:
    api_key = getattr(settings, 'OPENAI_API_KEY', '').strip()
    if not api_key:
        raise LLMServiceError('Missing OpenAI API key')

    base_url = getattr(settings, 'OPENAI_API_BASE_URL', 'https://api.openai.com/v1').rstrip('/')
    model = getattr(settings, 'OPENAI_MODEL', 'gpt-4o-mini')
    timeout = int(getattr(settings, 'LLM_API_TIMEOUT', 60))
    endpoint = f'{base_url}/chat/completions'

    payload = {
        'model': model,
        'messages': messages,
        'temperature': temperature,
    }
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    response = requests.post(endpoint, json=payload, headers=headers, timeout=timeout)
    if response.status_code >= 400:
        raise LLMServiceError(f'OpenAI request failed ({response.status_code}): {response.text[:300]}')

    data = response.json()
    content = (
        data.get('choices', [{}])[0]
        .get('message', {})
        .get('content', '')
    )
    return {
        'raw_text': content,
        'payload': data,
        'prompt': messages[-1]['content'],
        'model': model,
        'llm_provider': 'openai',
    }


def request_article_suggestion(criteria_text: str, article_context: Dict[str, Any]) -> Dict[str, Any]:
    messages = _build_messages(criteria_text, article_context)
    response = _request_openai_text_completion(messages=messages, temperature=0.1)
    response['parsed'] = _parse_llm_result(response.get('raw_text', ''))
    return response


def generate_project_inclusion_criteria(title: str, description: str = '') -> Dict[str, Any]:
    if not (title or '').strip():
        raise LLMServiceError('Project title is required to generate inclusion criteria')

    messages = _build_project_inclusion_messages(title=title, description=description)
    response = _request_openai_text_completion(messages=messages, temperature=0.3)
    text = _clean_text_response(response.get('raw_text', ''))
    if not text:
        raise LLMServiceError('OpenAI returned an empty inclusion criteria proposal')

    response['text'] = text
    return response
