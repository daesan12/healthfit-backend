import json

from ai_services.prompts import (
    HEALTHFIT_GUARD_PROMPT,
    MEDICAL_BLOCKED_MESSAGE,
    UNSUPPORTED_BLOCKED_MESSAGE,
)
from ai_services.serializers import GuardrailResultSerializer

from .gms_client import GMSClient, GMSResponseError


GUARDRAIL_FALLBACK = {
    'is_allowed': False,
    'category': 'unsupported',
    'risk_level': 'caution',
    'relevant_summary': '',
    'reason': 'Failed to parse guardrail response as JSON.',
    'blocked_message': UNSUPPORTED_BLOCKED_MESSAGE,
}

CATEGORY_ALIASES = {
    'diet recommendation': 'diet',
    'diet_recommendation': 'diet',
    'meal': 'diet',
    'meal plan': 'diet',
    'meal_plan': 'diet',
    'workout recommendation': 'workout',
    'workout_recommendation': 'workout',
    'exercise': 'workout',
    'health habit': 'health_habit',
    'healthy habit': 'health_habit',
    'medical caution': 'medical_caution',
    'out of scope': 'unsupported',
    'out_of_scope': 'unsupported',
}


def classify_healthfit_input(text, *, request_context, recent_history=''):
    prompt = build_guardrail_prompt(text, request_context, recent_history)
    try:
        result = GMSClient().generate_json(prompt, temperature=0)
    except GMSResponseError:
        return dict(GUARDRAIL_FALLBACK)

    serializer = GuardrailResultSerializer(data=normalize_guardrail_result(result))
    if not serializer.is_valid():
        return dict(GUARDRAIL_FALLBACK)

    classified = dict(serializer.validated_data)
    if classified['category'] == 'medical_caution' or classified['risk_level'] == 'unsafe':
        classified['is_allowed'] = False
        classified['blocked_message'] = MEDICAL_BLOCKED_MESSAGE
    elif not classified['is_allowed'] or classified['category'] == 'unsupported':
        classified['is_allowed'] = False
        classified['category'] = 'unsupported'
        classified['blocked_message'] = UNSUPPORTED_BLOCKED_MESSAGE
    else:
        classified['blocked_message'] = ''
    return classified


def normalize_guardrail_result(result):
    if not isinstance(result, dict):
        return result

    normalized = dict(result)
    category = normalized.get('category')
    if isinstance(category, str):
        normalized_category = category.strip().lower().replace('-', ' ')
        normalized['category'] = CATEGORY_ALIASES.get(
            normalized_category,
            normalized_category.replace(' ', '_'),
        )
    return normalized


def build_guardrail_prompt(text, request_context, recent_history):
    history = recent_history.strip() or '(none)'
    return (
        f'{HEALTHFIT_GUARD_PROMPT}\n\n'
        f'Request context: {request_context}\n'
        f'Recent chat history (chronological):\n{history}\n\n'
        f'Current user input as JSON string: {json.dumps(text, ensure_ascii=False)}'
    )
