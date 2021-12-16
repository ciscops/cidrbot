import logging
import datetime
import json
from git_cidrbot.gitauth import gitauth

logger = logging.getLogger()
logger.setLevel(logging.DEBUG)


def lambda_handler(event, handle):
    logger.debug('new event received: %s', str(event))
    logger.debug(str(event))
    logger.debug(str(handle))
    start_time = datetime.datetime.now()
    git = gitauth()
    webhook_payload = git.webhook_request(event)

    end_time = datetime.datetime.now()
    logger.debug('Script complete, total runtime {%s - %s}', end_time, start_time)

    if webhook_payload is not None:
        return webhook_payload
    return {
        "statusCode": 302,
        "headers": {
            "Location": 'https://github.com/apps/cidrbot',
            "Content-Type": "application/json"
        },
        "body": json.dumps({"Redirect ": "successful"})
    }
