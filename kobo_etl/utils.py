import datetime
import hashlib

# import the logging library
import logging
import re


# Get an instance of a logger
logger = logging.getLogger(__name__)


def toDatetimeStr(dateIn):
    if dateIn is None:
        return None
    elif isinstance(dateIn, datetime.datetime):
        return (dateIn.isoformat() + ".000")[:23]
    elif isinstance(dateIn, datetime.date):
        return (dateIn.isoformat() + "T00:00:00.000")[:23]
    elif isinstance(dateIn, str):
        regex = re.compile("^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3,6})?$")
        if regex.match(dateIn):
            return (dateIn + ".000")[:23]
        regex = re.compile("^\d{4}-\d{2}-\d{2}$")
        if regex.match(dateIn):
            return (dateIn + "T00:00:00.000")[:23]
        else:
            return None
    else:
        return None


def toDateStr(dateIn):
    if dateIn is None:
        return None
    elif isinstance(dateIn, datetime.datetime) or isinstance(dateIn, datetime.date):
        return dateIn.isoformat()[:10]
    elif isinstance(dateIn, str):
        regex = re.compile("^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(\.\d{3,6})?)?$")
        if regex.match(dateIn):
            return dateIn[:10]
        else:
            return None
    else:
        return None