import logging
import datetime
import json
from wxt_cidrbot.cidrbot import cidrbot

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


def lambda_handler(event, handle):
    logger.debug('new event received: %s', str(event))
    logger.debug(str(event))
    logger.debug(str(handle))
    start_time = datetime.datetime.now()
    cidr = cidrbot()
    # Determine the type of event and execute the correct function
    if event.get("Type") == "Timer":
        cidr.send_timed_msg()
    elif event.get("Type") == "Weekly Timer":
        cidr.weekly_reminder_email()
    else:
        cidr.webhook_request(event)
    end_time = datetime.datetime.now()
    logger.debug('Script complete, total runtime {%s - %s}', end_time, start_time)
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps({"testkey ": "testval"})
    }
