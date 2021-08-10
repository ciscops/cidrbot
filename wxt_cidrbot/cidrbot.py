import logging
import os
import sys
import json
from webexteamssdk import WebexTeamsAPI, ApiError
from wxt_cidrbot import cmd_list
from wxt_cidrbot import git_api_handler


class cidrbot:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
        self.logging = logging.getLogger()

        # Webex room id
        if "ROOM_ID" in os.environ:
            self.cidrbot_room_id = os.getenv("ROOM_ID")
        else:
            logging.error("Environment variable ROOM_ID must be set")
            sys.exit(1)

        if "WEBEX_BOT_ID" in os.environ:
            self.webex_bot_id = os.getenv("WEBEX_BOT_ID")
        else:
            logging.error("Environment variable WEBEX_BOT_ID must be set")
            sys.exit(1)

        # Initialize Api
        self.Api = WebexTeamsAPI()

        # self.git_handle = Git_handler.githandler(git_token)
        self.get_command = cmd_list.cmdlist()
        self.git_handle = git_api_handler.githandler()

        # Send messages returned by different parts of the code
    def send_wbx_msg(self, room, message, pt_id):
        self.Api.messages.create(room, markdown=message, parentId=pt_id)

    def send_timed_msg(self):
        message = self.git_handle.issues_list("List")
        self.send_wbx_msg(self.cidrbot_room_id, message, None)

        # Handle user invite messages, general commands, and conversations
    def webhook_request(self, event):
        json_string = json.loads((event["body"]))
        event_type = json_string['name']

        if event_type == "New user":
            text = self.get_command.new_user(json_string)
            self.send_wbx_msg(self.cidrbot_room_id, text, None)

        else:
            self.message_event(json_string, event_type)

    def message_event(self, json_string, event_type):
        webex_msg_sender = json_string['data']['personEmail']
        webex_sender_id = json_string['data']['personId']
        room_id = json_string['data']['roomId']
        msg_id = json_string['data']['id']
        message = self.Api.messages.get(msg_id)
        text = message.text

        if webex_msg_sender != "CIDRBot@webex.bot":
            if event_type == "Message":
                try:
                    pt_id = json_string['data']['parentId']
                except Exception:
                    pt_id = None

                if pt_id is not None:
                    message = self.Api.messages.list(room_id, parentId=pt_id)
                    for i in message:
                        if i.personId == self.webex_bot_id:
                            text = self.get_command.conversation_handler(text)
                            self.send_wbx_msg(room_id, text, pt_id)
                            return
                else:
                    text = self.get_command.message_handler(text)
                    self.send_wbx_msg(room_id, text, msg_id)

            elif event_type == "Direct Message":
                try:
                    verify_membership = self.Api.memberships.list(
                        roomId=self.cidrbot_room_id, personId=webex_sender_id)
                except ApiError:
                    verify_membership = None

                if verify_membership is not None:
                    for i in verify_membership:
                        i = i.to_dict()
                        if i['personId'] == webex_sender_id:
                            self.send_wbx_msg(
                                room_id, "You sent me a direct message, and you are part of cidrbot testing room", None)
