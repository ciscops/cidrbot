import logging
import os
import sys
import json
from webexteamssdk import WebexTeamsAPI
from wxt_cidrbot import command_list


class cidrbot:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
        self.logging = logging.getLogger()

        # Webex room id
        #if "ROOM_ID" in os.environ:
        #    room_id = os.getenv("ROOM_ID")
        #else:
        #    logging.error("Environment variable ROOM_ID must be set")
        #    sys.exit(1)

        if "WEBEX_BOT_ID" in os.environ:
            self.webex_bot_id = os.getenv("WEBEX_BOT_ID")
        else:
            logging.error("Environment variable WEBEX_BOT_ID must be set")
            sys.exit(1)

        # Initialize Api
        self.Api = WebexTeamsAPI()

        # self.git_handle = Git_handler.githandler(git_token)
        self.get_command = Command_list.cmdlist()

        # Send messages returned by different parts of the code
    def send_wbx_msg(self, room, message, pt_id):
        self.Api.messages.create(room, markdown=message, parentId=pt_id)

        # Handle user invite messages, general commands, and conversations
    def msg_request(self, event):
        json_string = json.loads((event["body"]))
        event_type = json_string['name']
        room_id = json_string['data']['roomId']

        if event_type == "New user":
            text = self.get_command.new_user(json_string)
            self.send_wbx_msg(room_id, text, None)

        elif event_type == "Message":
            webex_msg_sender = json_string['data']['personEmail']
            #webex_sender_id = json_string['data']['personId']
            msg_id = json_string['data']['id']
            message = self.Api.messages.get(msg_id)
            text = message.text

            if webex_msg_sender != "CIDRBot@webex.bot":
                try:
                    pt_id = json_string['data']['parentId']
                except Exception:
                    pt_id = None

                if pt_id is not None:
                    message = self.Api.messages.list(room_id, parentId=pt_id)
                    for i in message:
                        if i.personId == self.webex_bot_id:
                            text = self.get_command.conversation_handler(i.text, text)
                            self.send_wbx_msg(room_id, text, pt_id)
                            return
                else:
                    text = self.get_command.message_handler(text)
                    self.send_wbx_msg(room_id, text, msg_id)
