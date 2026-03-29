import logging
import os
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TOKEN = os.environ.get('TOKEN_KOBO', getattr(settings, 'TOKEN_KOBO', ''))
DEFAULT_BASE_URL = os.environ.get('KOBO_BASE_URL', 'https://kf.kobotoolbox.org')
PARAMS = {
    'format': 'json'
}


def _get_form_config(kobo_asset_uid):
    """Resolve token and base_url for a form.

    Per-form overrides via env vars:
        KOBO_TOKEN_<form_id>=<token>
        KOBO_URL_<form_id>=<base_url>

    Example in .env:
        KOBO_TOKEN_atpoVbHXZCdLD9ETHTv6z4=abc123def456
        KOBO_URL_atpoVbHXZCdLD9ETHTv6z4=https://kobo.other-server.org

    Falls back to TOKEN_KOBO + KOBO_BASE_URL if no override.
    """
    token = os.environ.get(f'KOBO_TOKEN_{kobo_asset_uid}', TOKEN)
    base_url = os.environ.get(f'KOBO_URL_{kobo_asset_uid}', DEFAULT_BASE_URL)
    return token, base_url


def get(kobo_asset_uid, **kwargs):
    """Fetch form data from KoBo API."""
    token, base_url = _get_form_config(kobo_asset_uid)
    headers = {'Authorization': f'Token {token}'}

    try:
        url = f'{base_url}/api/v2/assets/{kobo_asset_uid}/data'
        response = requests.get(url=url, params=PARAMS, headers=headers)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 409:
            response = {"status_code": e.code, "url": e.url, "text": e.description}
            logger.debug(e)
            return response
        logger.error(f"HTTP error fetching {kobo_asset_uid} from {base_url}: {e}")
        return {"results": []}
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching {kobo_asset_uid} from {base_url}: {e}")
        return {"results": []}