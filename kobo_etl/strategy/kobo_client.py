import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TOKEN = settings.TOKEN_KOBO
DEFAULT_BASE_URL = 'https://kf.kobotoolbox.org'
PARAMS = {
    'format': 'json'
}

# Per-form overrides: map form_id → {"token": "...", "base_url": "..."}
# Configure in Django settings as KOBO_FORM_OVERRIDES = { "form_id": { ... } }
FORM_OVERRIDES = getattr(settings, 'KOBO_FORM_OVERRIDES', {})


def get(kobo_asset_uid, **kwargs):
    """Fetch form data from KoBo API.

    Uses default TOKEN_KOBO and kf.kobotoolbox.org unless the form has
    an override in settings.KOBO_FORM_OVERRIDES:

        KOBO_FORM_OVERRIDES = {
            "atpoVbHXZCdLD9ETHTv6z4": {
                "token": "your_other_server_token",
                "base_url": "https://kobo.other-server.org",
            }
        }
    """
    override = FORM_OVERRIDES.get(kobo_asset_uid, {})
    token = override.get('token', TOKEN)
    base_url = override.get('base_url', DEFAULT_BASE_URL)
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