import logging
import datetime
import json
import os
import sys
from wxt_cidrbot.cidrbot import cidrbot
from wxt_cidrbot.git_webhook_handler import gitwebhook

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


def lambda_handler(event, handle):
    logger.debug('new event received: %s', str(event))
    logger.debug(str(event))
    logger.debug(str(handle))
    start_time = datetime.datetime.now()

    if "GITHUB_WEBHOOK_PATH" in os.environ:
        webhook_path = os.getenv("GITHUB_WEBHOOK_PATH")
    else:
        logging.error("Environment variable GITHUB_WEBHOOK_PATH must be set")
        sys.exit(1)

    if "BASE_WEBHOOK_PATH" in os.environ:
        base_webhook_path = os.getenv("BASE_WEBHOOK_PATH")
    else:
        logging.error("Environment variable BASE_WEBHOOK_PATH must be set")
        sys.exit(1)

    cidr = cidrbot()
    git = gitwebhook()
    # Determine the type of event and execute the correct function

    if 'path' in event:
        if event['path'] == webhook_path:
            git.webhook_request(event)
        elif event['path'] == base_webhook_path:
            cidr.webhook_request(event)

    if event.get("Type") == "Timer":
        cidr.send_timed_msg()
    elif event.get("Type") == "Weekly Timer":
        cidr.weekly_reminder_email()

    end_time = datetime.datetime.now()
    logger.debug('Script complete, total runtime {%s - %s}', end_time, start_time)
    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps({"testkey ": "testval"})
    }
