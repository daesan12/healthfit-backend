import json
import os

import requests


DEFAULT_GMS_ENDPOINT = (
    'https://gms.ssafy.io/gmsapi/'
    'generativelanguage.googleapis.com/v1beta'
)
DEFAULT_GMS_MODEL = 'gemini-2.5-flash-lite'
DEFAULT_TIMEOUT_SECONDS = 30
DEFAULT_MAX_ATTEMPTS = 2


class GMSConfigurationError(Exception):
    pass


class GMSAPIError(Exception):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class GMSResponseError(Exception):
    pass


class GMSClient:
    def __init__(self, timeout=DEFAULT_TIMEOUT_SECONDS):
        self.api_key = os.getenv('GMS_KEY', '').strip()
        self.timeout = timeout

    def generate_json(self, prompt):
        if not self.api_key:
            raise GMSConfigurationError('GMS_KEY is missing.')

        url = f'{DEFAULT_GMS_ENDPOINT}/models/{DEFAULT_GMS_MODEL}:generateContent'
        payload = {
            'contents': [{'parts': [{'text': prompt}]}],
            'generationConfig': {'responseMimeType': 'application/json'},
        }
        for attempt in range(DEFAULT_MAX_ATTEMPTS):
            try:
                response_data = self._request_json(url, payload)
                response_text = self._extract_response_text(response_data)
                return self._parse_json_object(response_text)
            except GMSResponseError:
                if attempt == DEFAULT_MAX_ATTEMPTS - 1:
                    raise

    def _request_json(self, url, payload):
        try:
            response = requests.post(
                url,
                headers={
                    'Content-Type': 'application/json',
                    'x-goog-api-key': self.api_key,
                },
                json=payload,
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            raise GMSAPIError('GMS API request failed or timed out.') from exc

        if response.status_code >= 400:
            raise GMSAPIError(
                'GMS API returned an error response.',
                status_code=response.status_code,
            )

        if not response.content.strip():
            raise GMSResponseError('GMS returned an empty response envelope.')
        try:
            return response.json()
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GMSResponseError('GMS returned an invalid response envelope.') from exc

    def _extract_response_text(self, response_data):
        try:
            parts = response_data['candidates'][0]['content']['parts']
            response_text = ''.join(
                part.get('text', '')
                for part in parts
                if isinstance(part, dict)
            ).strip()
        except (KeyError, IndexError, TypeError) as exc:
            raise GMSResponseError('GMS response did not contain candidate text.') from exc

        if not response_text:
            raise GMSResponseError('GMS response candidate text was empty.')
        return response_text

    def _parse_json_object(self, response_text):
        cleaned = response_text.strip().lstrip('\ufeff')
        candidates = [cleaned]

        if cleaned.startswith('```'):
            lines = cleaned.splitlines()
            if lines and lines[0].startswith('```'):
                lines = lines[1:]
            if lines and lines[-1].strip() == '```':
                lines = lines[:-1]
            candidates.append('\n'.join(lines).strip())

        first_brace = cleaned.find('{')
        last_brace = cleaned.rfind('}')
        if first_brace >= 0 and last_brace > first_brace:
            candidates.append(cleaned[first_brace:last_brace + 1])

        parsed_non_object = False
        for candidate in candidates:
            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed
            parsed_non_object = True

        if parsed_non_object:
            raise GMSResponseError('GMS JSON content must be an object.')
        raise GMSResponseError('GMS response text could not be parsed as JSON.')
