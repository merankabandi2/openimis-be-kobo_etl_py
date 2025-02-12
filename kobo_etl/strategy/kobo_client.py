import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TOKEN = settings.TOKEN_KOBO
PARAMS = {
    'format': 'json'
}
HEADERS = {
    'Authorization': f'Token {TOKEN}'
}

def get(kobo_asset_uid, **kwargs):
    try:
        URL = f'https://kf.kobotoolbox.org/api/v2/assets/{kobo_asset_uid}/data'
        response = requests.get(url=URL, params=PARAMS, headers=HEADERS)
        return response.json()
    except requests.exceptions.RequestException as e:
        if e.code == 409:
            response = {"status_code": e.code, "url": e.url, "text": e.description}
            logger.debug(e)
            return response
        else:
            logger.error(e)

