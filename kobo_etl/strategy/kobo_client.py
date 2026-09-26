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
# (connect, read) seconds for the status probe, which runs while the admin page loads.
PROBE_TIMEOUT = (5, 10)


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


def is_configured(kobo_asset_uids):
    """True when every form resolves a non-empty token and base URL."""
    return all(all(_get_form_config(uid)) for uid in kobo_asset_uids)


def is_reachable(kobo_asset_uids):
    """True when KoBo answers a data request (limit 1) for one form of each distinct (base URL, token).

    The request carries the token, so a rejected token counts as unreachable.
    """
    if not is_configured(kobo_asset_uids):
        return False
    probes = {}
    for uid in kobo_asset_uids:
        probes.setdefault(_get_form_config(uid), uid)
    for (token, base_url), uid in probes.items():
        try:
            response = requests.get(
                url=f'{base_url}/api/v2/assets/{uid}/data',
                params={**PARAMS, 'limit': 1},
                headers={'Authorization': f'Token {token}'},
                timeout=PROBE_TIMEOUT,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logger.warning(f"KoBo connection check of {uid} on {base_url} failed: {e}")
            return False
    return True


class KoboFetchError(Exception):
    """Raised when a KoBo form cannot be fetched completely."""


def get(kobo_asset_uid, **kwargs):
    """Fetch ALL form data from KoBo API, handling pagination.

    Returns {"count": N, "results": [...all submissions...]}.
    Raises KoboFetchError when any page fails, so a partial result set is never returned.
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
    except requests.exceptions.RequestException as e:
        logger.error(
            f"Error fetching {kobo_asset_uid} from {base_url} after {len(all_results)} submissions: {e}"
        )
        raise KoboFetchError(
            f"KoBo fetch of {kobo_asset_uid} failed after {len(all_results)} submissions: {e}"
        ) from e

    return {"count": len(all_results), "results": all_results}
