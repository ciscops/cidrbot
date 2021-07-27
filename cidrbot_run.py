import logging
import datetime
import json
#import socket
from wxt_cidrbot.cidrbot import cidrbot

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


def lambda_handler(event, handle):
    logger.debug('new event received: %s', str(event))
    logger.debug(str(event))
    logger.debug(str(handle))
    #logger.debug(socket.gethostbyname(''))
    start_time = datetime.datetime.now()
    cidr = cidrbot()
    cidr.msg_request(event)
    end_time = datetime.datetime.now()
    logger.debug('Script complete, total runtime {%s - %s}', end_time, start_time)
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps({"testkey ": "testval"})
    }
