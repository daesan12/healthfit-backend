import json

from ai_services.models import AIChat
from ai_services.prompts import HEALTHFIT_CHAT_PROMPT, HEALTHFIT_PT_COACH_TONE

from .gms_client import GMSClient, GMSResponseError
from .guardrail_service import classify_healthfit_input


def create_chat_answer(user, question):
    recent_history = format_recent_history(user)
    guardrail = classify_healthfit_input(
        question,
        request_context='AI chat question',
        recent_history=recent_history,
    )
    if not guardrail['is_allowed']:
        return guardrail['blocked_message']

    prompt = (
        f'{HEALTHFIT_CHAT_PROMPT}\n{HEALTHFIT_PT_COACH_TONE}\n\n'
        f'Recent history:\n{recent_history or "(none)"}\n\n'
        f'Guardrail relevant summary: {guardrail["relevant_summary"]}\n'
        f'Original current question as JSON string: {json.dumps(question, ensure_ascii=False)}'
    )
    result = GMSClient().generate_json(prompt, temperature=0.7)
    answer = result.get('answer') if isinstance(result, dict) else None
    if not isinstance(answer, str) or not answer.strip():
        raise GMSResponseError('AI chat response did not contain a valid answer.')
    return answer.strip()


def format_recent_history(user, limit=5):
    recent = list(AIChat.objects.filter(user=user).order_by('-created_at', '-id')[:limit])
    recent.reverse()
    return '\n\n'.join(
        f'User: {chat.question}\nAI: {chat.answer}'
        for chat in recent
    )
