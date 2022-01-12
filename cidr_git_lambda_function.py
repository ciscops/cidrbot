import logging
import datetime
import json
import os
import sys
from git_cidrbot.gitauth import gitauth

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


def lambda_handler(event, handle):
    logger.debug('new event received: %s', str(event))
    logger.debug(str(event))
    logger.debug(str(handle))
    start_time = datetime.datetime.now()

    if 'GITHUB_BOT_NAME' in os.environ:
        git_bot_name = os.getenv("GITHUB_BOT_NAME")
    else:
        logging.error("Environment variable GITHUB_BOT_NAME must be set")
        sys.exit(1)

    git = gitauth()
    webhook_payload = git.webhook_request(event)

    end_time = datetime.datetime.now()
    logger.debug('Script complete, total runtime {%s - %s}', end_time, start_time)

    if webhook_payload is not None:
        return webhook_payload
    return {
        "statusCode": 302,
        "headers": {
            "Location": 'https://github.com/apps/' + git_bot_name,
            "Content-Type": "application/json"
        },
        "body": json.dumps({"Redirect ": "successful"})
    }
