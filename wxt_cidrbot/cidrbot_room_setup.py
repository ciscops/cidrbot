import logging
import os
import sys
import json
import requests
from webexteamssdk import WebexTeamsAPI
from wxt_cidrbot import cmd_list
from wxt_cidrbot import dynamo_api_handler
from wxt_cidrbot import webex_edit_message


class room_setup:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
        self.logging = logging.getLogger()

        if "WEBEX_BOT_ID" in os.environ:
            self.webex_bot_id = os.getenv("WEBEX_BOT_ID")
        else:
            logging.error("Environment variable WEBEX_BOT_ID must be set")
            sys.exit(1)

        if 'WEBEX_TEAMS_ACCESS_TOKEN' in os.environ:
            self.wxt_access_token = os.getenv("WEBEX_TEAMS_ACCESS_TOKEN")
        else:
            logging.error("Environment variable WEBEX_TEAMS_ACCESS_TOKEN must be set")
            sys.exit(1)

        if 'TARGET_URL' in os.environ:
            self.targetURL = os.getenv("TARGET_URL")
        else:
            logging.error("Environment variable TARGET_URL must be set")
            sys.exit(1)

        self.Api = WebexTeamsAPI()
        self.get_command = cmd_list.cmdlist()
        self.dynamo = dynamo_api_handler.dynamoapi()
        self.webex = webex_edit_message.webex_message()

    def invited(self, json_string):
        user_id = json_string['data']['personId']

        if self.webex_bot_id == user_id:
            room_id = json_string['data']['roomId']

            members = self.Api.memberships.list(roomId=room_id)
            member_count = 0
            member_info = []
            member_list = []

            for i in members:
                i = i.to_dict()
                if i['personEmail'] != "CIDRBot@webex.bot":
                    member_count += 1
                    name = str(i['personDisplayName']).split(" ", 1)[0]
                    user_email = str(i['personEmail']).split("@", 1)[0]
                    person_id = i['personId']
                    if name not in member_list:
                        member_list.append(name)
                        dup = False
                    else:
                        member_list.append(user_email)
                        dup = True

                    member_info.append({
                        'user_email': user_email,
                        'first_name': name,
                        'duplicate': dup,
                        'person_id': person_id
                    })

            text = f"Hello, thank you for adding cidrbot to your room, one moment while I set things up: \n - Setting up webhooks..."
            post_message = {'roomId': room_id, 'markdown': text}

            message_id = self.post_message(post_message)

            text += f"\n - Webhook setup complete"
            self.webex.edit_message(message_id, text, room_id)

            id_list = self.webex_webhook_setup(room_id)
            self.dynamo.create_room(room_id, member_info, id_list)

            text += f"\n - Room setup complete \n\n To begin using cidrbot's github features, type **@CIDRbot add repo** \n For a list of commands type **@CIDRbot help**"
            self.webex.edit_message(message_id, text, room_id)

    def webex_webhook_setup(self, room_id):
        room_filter = "roomId=" + room_id
        id_list = []

        post_data_message = {
            'name': "Message",
            'targetUrl': self.targetURL,
            'resource': "messages",
            'event': "created",
            'filter': room_filter
        }

        post_data_new = {
            'name': "New user",
            'targetUrl': self.targetURL,
            'resource': "memberships",
            'event': "created",
            'filter': room_filter
        }

        post_data_left = {
            'name': "User left",
            'targetUrl': self.targetURL,
            'resource': "memberships",
            'event': "deleted",
            'filter': room_filter
        }

        id_message = self.post_webhook(post_data_message)
        id_new_user = self.post_webhook(post_data_new)
        id_user_left = self.post_webhook(post_data_left)

        id_list.extend([id_message, id_new_user, id_user_left])
        self.logging.debug(id_list)

        return id_list

    def post_webhook(self, post_data):
        URL = f'https://webexapis.com/v1/webhooks'
        headers = {'Authorization': 'Bearer ' + self.wxt_access_token, 'Content-type': 'application/json;charset=utf-8'}

        response = requests.post(URL, json=post_data, headers=headers)
        if response.status_code == 200:
            self.logging.debug("Webhook created successfully")
            self.logging.debug(str(response.text))
            resp = json.loads(str(response.text))
            return resp["id"]

        self.logging.debug(str(response.status_code))
        self.logging.debug(str(response.text))
        return "no id"

    def post_message(self, post_data):
        URL = f'https://webexapis.com/v1/messages'
        headers = {'Authorization': 'Bearer ' + self.wxt_access_token, 'Content-type': 'application/json;charset=utf-8'}

        response = requests.post(URL, json=post_data, headers=headers)
        if response.status_code == 200:
            self.logging.debug("Message created successfully")
            self.logging.debug(str(response.text))
            resp = json.loads(str(response.text))
            return resp["id"]

        self.logging.debug(str(response.status_code))
        self.logging.debug(str(response.text))
        return "no id"
