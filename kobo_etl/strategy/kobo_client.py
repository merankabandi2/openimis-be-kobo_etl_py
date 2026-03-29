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
    """Fetch ALL form data from KoBo API, handling pagination.

    Returns {"count": N, "results": [...all submissions...]}.
    """
    token, base_url = _get_form_config(kobo_asset_uid)
    headers = {'Authorization': f'Token {token}'}
    all_results = []
    url = f'{base_url}/api/v2/assets/{kobo_asset_uid}/data'
    params = {**PARAMS}

    try:
        while url:
            response = requests.get(url=url, params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
            results = data.get('results', [])
            all_results.extend(results)
            url = data.get('next')
            params = {}  # next URL already includes params
            if results:
                logger.info(f"Fetched {len(all_results)}/{data.get('count', '?')} from {kobo_asset_uid}")

        return {"count": len(all_results), "results": all_results}
    except requests.exceptions.HTTPError as e:
        if e.response is not None and e.response.status_code == 409:
            return {"status_code": e.code, "url": e.url, "text": e.description}
        logger.error(f"HTTP error fetching {kobo_asset_uid} from {base_url}: {e}")
        return {"count": len(all_results), "results": all_results}
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching {kobo_asset_uid} from {base_url}: {e}")
        return {"count": len(all_results), "results": all_results}