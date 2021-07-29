import logging
import os
import sys
import base64
import json
#from Git_handler import githandler
#from Command_list import cmdlist
#from github import Github
from webexteamssdk import WebexTeamsAPI

# fill in imports that are necessary for webex api


class cidrbot:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
        self.logging = logging.getLogger()

        # Webex room id
        if "ROOM_ID" in os.environ:
            room_id = os.getenv("ROOM_ID")
        else:
            logging.error("Environment variable ROOM_ID must be set")
            sys.exit(1)

        # Initialize Api
        self.Api = WebexTeamsAPI()

        # Format room_id
        # This needs to be moved, since this is needed only after the webhook arrives
        room_uri = "ciscospark://us/ROOM/{}".format(room_id)
        room_uri = room_uri.encode()
        encoded_roomid = base64.b64encode(room_uri)
        self.encoded_roomid = encoded_roomid.decode("utf-8")
        print(self.encoded_roomid)

    def send_wbx_msg(self, room, message):
        self.Api.messages.create(room, markdown=message)

    def msg_request(self, event):
        json_string = json.loads((event["body"]))
        webex_msg_sender = json_string['data']['personEmail']
        room_id = json_string['data']['roomId']
        event_type = json_string['name']
        user_name = json_string['data']['personDisplayName']
        user_id = json_string['data']['personId']

        name_format = f'<@personId:{user_id}|{user_name}>'

        if event_type == "Message":
            if webex_msg_sender != "CIDRBot@webex.bot":
                message = self.Api.messages.get(id)
                text = message.text

                if "CIDRBot" in text:
                    text = text.strip("CIDRBot ")

                if text == "help":
                    self.send_wbx_msg(room_id, "Here is a basic help menu")
                elif text == "list issues":
                    self.send_wbx_msg(room_id, "Pretend this is a list of current git issues")
                elif text == "commands":
                    self.send_wbx_msg(room_id, "My current commands are: help, list issues, commands")
                else:
                    self.send_wbx_msg(room_id, "Sorry I don't understand your message")

        elif event_type == "New user":
            self.send_wbx_msg(room_id, "Welcome to Cidrbot testing room " + name_format)
