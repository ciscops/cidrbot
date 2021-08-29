import logging
import os
import sys
import json
from webexteamssdk import WebexTeamsAPI, ApiError
from wxt_cidrbot import cmd_list
from wxt_cidrbot import git_api_handler
from wxt_cidrbot import dynamo_api_handler
from wxt_cidrbot import webex_edit_message


class cidrbot:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
        self.logging = logging.getLogger()

        # Initialize webex global variables
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

        if 'WEBEX_TEAMS_ACCESS_TOKEN' in os.environ:
            self.wxt_access_token = os.getenv("WEBEX_TEAMS_ACCESS_TOKEN")
        else:
            logging.error("Environment variable WEBEX_TEAMS_ACCESS_TOKEN must be set")
            sys.exit(1)

        # Initialize Api
        self.Api = WebexTeamsAPI()

        # Init sibling py files
        self.get_command = cmd_list.cmdlist()
        self.git_handle = git_api_handler.githandler()
        self.dynamo = dynamo_api_handler.dynamoapi()
        self.webex = webex_edit_message.webex_message()

    def send_wbx_msg(self, room, message, pt_id):
        self.Api.messages.create(room, markdown=message, parentId=pt_id)

    def send_directwbx_msg(self, person_id, message):
        self.Api.messages.create(toPersonId=person_id, markdown=message)

    # Send a daily message to the cidrbot users chatroom: Every day at 11am est: Cron expression 0 15 ? * * *
    def send_timed_msg(self):
        message = self.git_handle.scan_repos("List", 'All', self.dynamo.dynamo_db("repos", None, None, None))
        self.send_wbx_msg(self.cidrbot_room_id, message, None)

    # Send a message to all users with reminders enabled: Every monday at 12pm est: Cron expression 0 16 ? * 2 *
    def weekly_reminder_email(self):
        remind_users = dict(self.dynamo.dynamo_db('all_users', None, None, None))
        assigned_issues_dict = self.git_handle.scan_repos(
            "Dict", 'All', self.dynamo.dynamo_db("repos", None, None, None)
        )

        for i in remind_users['Items']:
            user_name = i['User']
            person_id = i['person_id']
            self.logging.debug(user_name + " " + person_id)

            message = self.get_command.get_user_issues(assigned_issues_dict, user_name)
            if message != "No issues":
                self.send_directwbx_msg(person_id, message)

    # Process webhook request from lambda_function
    def webhook_request(self, event):
        json_string = json.loads((event["body"]))
        webex_msg_sender = json_string['data']['personEmail']
        event_type = json_string['name']
        user_id = json_string['data']['personId']

        if event_type == "New user":
            user_name = self.Api.people.get(user_id).firstName
            text = self.get_command.new_user(json_string, webex_msg_sender, user_name)
            self.send_wbx_msg(self.cidrbot_room_id, text, None)
        elif event_type == "User left":
            self.logging.debug("User left")
            self.dynamo.dynamo_db('delete_user', webex_msg_sender, None, None)
        elif webex_msg_sender != "CIDRBot@webex.bot":
            self.message_event(json_string, event_type, webex_msg_sender)

    # Webex sdk does not support editing a message, so the rest api is directly called
    def edit_wbx_message(self, message_id, message, room_id):
        self.webex.edit_message(message_id, message, room_id)

    # When an issue is assigned, notify users who have reminders enabled
    def webex_notify_room_user(self, text, room_id):
        message = text[0]
        user_id = text[2]
        chatroom_message = text[3]
        chatroom_message_id = text[4]
        self.edit_wbx_message(chatroom_message_id, chatroom_message, room_id)
        self.send_directwbx_msg(user_id, message)

    # Resolve the message type and shuttle the data off to cmd_list to be processed
    def message_event(self, json_string, event_type, webex_msg_sender):
        webex_sender_id = json_string['data']['personId']
        room_id = json_string['data']['roomId']
        msg_id = json_string['data']['id']
        message = self.Api.messages.get(msg_id)
        text = message.text

        self.get_command.user_email_payload(
            webex_msg_sender, webex_sender_id, self.Api.memberships.list(roomId=self.cidrbot_room_id)
        )

        if event_type == "Message":
            try:
                pt_id = json_string['data']['parentId']
            except Exception:
                pt_id = None

            if pt_id is not None:
                text = self.get_command.message_handler(text, None, room_id, pt_id)
                if text[1] is not None and text[1] == "edit message":
                    message = text[2]
                    message_id = text[0]
                    self.edit_wbx_message(message_id, message, room_id)
                elif text[1] is not None and text[1] == 'notify user':
                    self.webex_notify_room_user(text, room_id)
                else:
                    self.send_wbx_msg(room_id, text, pt_id)
                    return
            else:
                text = self.get_command.message_handler(text, None, room_id, msg_id)
                if text[1] is not None and text[1] == "edit message":
                    message = text[2]
                    message_id = text[0]
                    self.edit_wbx_message(message_id, message, room_id)
                elif text[1] is not None and text[1] == 'notify user':
                    self.webex_notify_room_user(text, room_id)
                else:
                    self.send_wbx_msg(room_id, text, msg_id)

        elif event_type == "Direct Message":
            try:
                verify_membership = self.Api.memberships.list(roomId=self.cidrbot_room_id, personId=webex_sender_id)
            except ApiError:
                verify_membership = None

            if verify_membership is not None:
                for i in verify_membership:
                    i = i.to_dict()
                    if i['personId'] == webex_sender_id:
                        text = self.get_command.message_handler(text, event_type, room_id, None)
                        self.logging.debug("hello see this")
                        if text[1] is not None and text[1] == "edit message":
                            message = text[2]
                            message_id = text[0]
                            self.edit_wbx_message(message_id, message, room_id)
                        elif text[1] is not None and text[1] == 'notify user':
                            self.webex_notify_room_user(text, room_id)
                        else:
                            self.send_wbx_msg(room_id, text, None)
