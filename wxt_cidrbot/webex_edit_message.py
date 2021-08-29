import logging
import os
import sys
import requests
from webexteamssdk import WebexTeamsAPI

class webex_message:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
        self.logging = logging.getLogger()

        if 'WEBEX_TEAMS_ACCESS_TOKEN' in os.environ:
            self.wxt_access_token = os.getenv("WEBEX_TEAMS_ACCESS_TOKEN")
        else:
            logging.error("Environment variable WEBEX_TEAMS_ACCESS_TOKEN must be set")
            sys.exit(1)

        # Initialize Api
        self.Api = WebexTeamsAPI()

    # Make a post request to webex's rest api since the sdk doesn't support editing messages...why...?
    def edit_message(self, message_id, message, room_id):
        URL = f'https://webexapis.com/v1/messages/{message_id}'

        headers = {'Authorization': 'Bearer ' + self.wxt_access_token,
                   'Content-type': 'application/json;charset=utf-8'}
        post_data = {'roomId': room_id,
                     'markdown': message}
        response = requests.put(URL, json=post_data, headers=headers)
        if response.status_code == 200:
            self.logging.debug("Message updated successfully")
        else:
            self.logging.debug(response.status_code, response.text)
