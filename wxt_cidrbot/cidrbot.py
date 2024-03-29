import logging
import os
import sys
import json
from webexteamssdk import WebexTeamsAPI, ApiError
from wxt_cidrbot import cidrbot_room_setup
#Change room_setup to be in a seperate folder to make this cleaner
from wxt_cidrbot import cmd_list
from wxt_cidrbot import git_api_handler
from wxt_cidrbot import dynamo_api_handler
from wxt_cidrbot import webex_edit_message


class cidrbot:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
        self.logging = logging.getLogger()

        if 'WEBEX_TEAMS_ACCESS_TOKEN' in os.environ:
            self.wxt_access_token = os.getenv("WEBEX_TEAMS_ACCESS_TOKEN")
        else:
            logging.error("Environment variable WEBEX_TEAMS_ACCESS_TOKEN must be set")
            sys.exit(1)

        if "WEBEX_BOT_ID" in os.environ:
            self.webex_bot_id = os.getenv("WEBEX_BOT_ID")
        else:
            logging.error("Environment variable WEBEX_BOT_ID must be set")
            sys.exit(1)

        if 'ORGANIZATION_ID' in os.environ:
            self.orgID = os.getenv("ORGANIZATION_ID")
        else:
            logging.error("Environment variable ORGANIZATION_ID must be set")
            sys.exit(1)

        if 'WEBEX_BOT_NAME' in os.environ:
            self.bot_name = os.getenv("WEBEX_BOT_NAME")
        else:
            logging.error("Environment variable WEBEX_BOT_NAME must be set")
            sys.exit(1)

        # Initialize Api
        self.Api = WebexTeamsAPI()

        # Init sibling py files
        self.get_command = cmd_list.cmdlist()
        self.git_handle = git_api_handler.githandler()
        self.dynamo = dynamo_api_handler.dynamoapi()
        self.webex = webex_edit_message.webex_message()
        self.room_handle = cidrbot_room_setup.room_setup()
        self.roomID = ""
        self.WEBEX_MESSAGE_CHAR_LIMIT = 4700

    def send_wbx_msg(self, room, message, pt_id):
        self.Api.messages.create(room, markdown=message, parentId=pt_id)

    def send_wbx_messages(self, msgs_to_be_sent, room_id, message_id, pt_id, request_type):
        """
        sends all messages in a list and can either sent the message(s) as an edit or new reply

        :param msgs_to_be_sent: list, the messages to be sent
        :param room_id: string, the id for the webex room
        :param message_id: string, id for the webex message bot will edit
        :param pt_id: string, id of webex parent message bot responds to
        :param request_type: string, whether request is daily update or to edit a message

        return: bool, True if messages sent
        """

        if request_type == 'daily_message':
            self.send_wbx_msg(room_id, msgs_to_be_sent.pop(0), pt_id)
        elif request_type == 'edit_message':
            self.webex.edit_message(message_id, msgs_to_be_sent.pop(0), room_id)
        for msg in msgs_to_be_sent:
            self.send_wbx_msg(room_id, msg, pt_id)

        return True

    def send_directwbx_msg(self, person_id, message):
        self.Api.messages.create(toPersonId=person_id, markdown=message)

    # Send a daily message to the cidrbot users chatroom: Every day at 11am est: Cron expression 0 15 * * ? *
    def send_timed_msg(self):
        id_list = self.dynamo.get_all_ids()

        for room_id in id_list:
            self.git_handle.room_and_edit_id(room_id, None)

            message = self.git_handle.scan_repos("List", 'All', self.dynamo.get_repositories(room_id), False)

            if '#' in message:
                self.logging.debug("sending message to " + room_id + "message " + message)
                message_overflow = self.check_message_overflow(message, room_id, None, None, 'daily_message')

                if message_overflow is False:
                    self.send_wbx_msg(room_id, message, None)

    # Send a message to all users with reminders enabled: Every monday at 12pm est: Cron expression 0 16 ? * 2 *
    # Change this to weekly_reminder_message
    def weekly_reminder_email(self):
        remind_users = self.dynamo.get_notif_users()
        self.logging.debug(remind_users)
        messaged_users = []

        for room in remind_users['Items']:
            self.git_handle.room_and_edit_id(room['room_id'], None)

            assigned_issues_dict = self.git_handle.scan_repos(
                "Dict", 'All', self.dynamo.get_repositories(room['room_id']), False
            )

            room_info = self.Api.rooms.get(room['room_id'])
            room_name = room_info.title

            for user in room['users']:
                if room['users'][user]['reminders_enabled'] == "on":
                    self.logging.debug(str(assigned_issues_dict))
                    self.logging.debug(room['users'][user]['git_name'])
                    self.logging.debug(room['room_id'])
                    self.logging.debug(user)
                    git_username = room['users'][user]['git_name']
                    text = self.get_command.get_user_issues(assigned_issues_dict, git_username)

                    #Side note, maybe add | at the start of each message to make it look nice
                    if text != "No issues":
                        if user in messaged_users:
                            message = f"Room: {room_name} \n"
                            message += text + '\n'
                        else:
                            message = (
                                "**Weekly reminder to review your issues**, " +
                                f" -To disable these messages, type: **disable reminders** \n \n Room: {room_name} \n"
                            )
                            message += text + '\n'

                        self.send_directwbx_msg(room['users'][user]['person_id'], message)
                        messaged_users.append(user)

    # Process webhook request from lambda_function
    def webhook_request(self, event):
        json_string = json.loads((event["body"]))
        webex_msg_sender = json_string['data']['personEmail']
        event_type = json_string['name']
        user_id = json_string['data']['personId']
        org_id = json_string['orgId']
        self.roomID = json_string['data']['roomId']

        if event_type == "New user":
            user_name = self.Api.people.get(user_id).firstName
            text = self.get_command.new_user(json_string, webex_msg_sender, user_name, self.roomID)
            self.send_wbx_msg(self.roomID, text, None)
        elif event_type == "Bot add to room" and json_string['data']['roomType'] != 'direct':
            self.logging.debug("bot added to room")
            self.room_handle.invited(json_string)
        elif event_type == "User left":
            if user_id == self.webex_bot_id:
                self.logging.debug("Bot was removed from room")
                webhook_list = self.dynamo.get_webhooks(self.roomID)

                for webhook in webhook_list:
                    self.Api.webhooks.delete(webhookId=webhook)

                self.dynamo.delete_room(self.roomID)
                return

            self.logging.debug("Checking memberships")
            members = self.Api.memberships.list(roomId=self.roomID)
            member_count = 0
            member_id = ''

            for i in members:
                member_count += 1
                i = i.to_dict()
                if i['personId'] == self.webex_bot_id:
                    member_id = i['id']

            if member_count == 1:
                webhook_list = self.dynamo.get_webhooks(self.roomID)

                for webhook in webhook_list:
                    self.Api.webhooks.delete(webhookId=webhook)

                self.dynamo.delete_room(self.roomID)
                self.Api.memberships.delete(member_id)
                self.logging.debug("no members left, leave room and delete row")
            else:
                self.logging.debug("User left")
                self.dynamo.delete_user(webex_msg_sender, self.roomID)

        elif webex_msg_sender != self.bot_name + "@webex.bot":
            if org_id == self.orgID:
                self.message_event(json_string, event_type, webex_msg_sender)

    def check_message_overflow(self, message, room_id, message_id, pt_id, request_type):
        """
        If message is over webex char limit, it separates the message into chunks that fit the limit

        :param message: string, the message to be evaluated
        :param room_id: string, the id for the webex room
        :param message_id: string, id for the webex message bot will edit
        :param pt_id: string, id of webex parent message bot responds to
        :param request_type: string, whether request is daily update or to edit a message

        return: bool, if message under limit - False; if over limit - True
        """
        split_keyword = 'Repo:'
        #If message overflow with an entire repo, how many lines should be able to be appended to last message before just making new message
        num_needed_repo_lines = 3

        if len(message) < self.WEBEX_MESSAGE_CHAR_LIMIT:
            return False

        split_message = message.split(split_keyword)
        message_first_part = ""
        msgs_to_be_sent = []

        issue_title = split_message.pop(0)
        message_first_part += issue_title

        for repo in split_message:
            self.logging.debug("Repo: %s", str(repo))
            self.logging.debug("Length of repo %s", len(repo))

            if len(message_first_part) + len(repo) < self.WEBEX_MESSAGE_CHAR_LIMIT:
                message_first_part += split_keyword
                message_first_part += repo
                continue

            split_repo = repo.split("\n")
            repo_name = split_repo.pop(0)

            #check to see if cannot append at least n lines to last message
            is_not_able_to_append = len(message_first_part) + len(
                "".join(split_repo[:num_needed_repo_lines])
            ) >= self.WEBEX_MESSAGE_CHAR_LIMIT

            #check see if entire repo fit in one message so don't waste memory and time splitting and repiecing
            if is_not_able_to_append and len(repo) < self.WEBEX_MESSAGE_CHAR_LIMIT:
                msgs_to_be_sent.append(message_first_part)
                message_first_part = split_keyword + repo
                continue
            if is_not_able_to_append:
                msgs_to_be_sent.append(message_first_part)
                message_first_part = ""

            # means is able to append
            message_first_part += split_keyword + repo_name
            for repo_part in split_repo:
                if len(message_first_part) + len(repo_part) < self.WEBEX_MESSAGE_CHAR_LIMIT:
                    message_first_part += "\n" + repo_part
                    continue
                msgs_to_be_sent.append(message_first_part)
                #if end message, don't do split_keyword part
                message_first_part = split_keyword + repo_name + " (continued)" + "\n" + repo_part
        msgs_to_be_sent.append(message_first_part)

        return self.send_wbx_messages(msgs_to_be_sent, room_id, message_id, pt_id, request_type)

    # Webex sdk does not support editing a message, so the rest api is directly called
    def edit_wbx_message(self, message_id, message, room_id, pt_id):
        message_overflow = self.check_message_overflow(message, room_id, message_id, pt_id, 'edit_message')

        if message_overflow is False:
            self.webex.edit_message(message_id, message, room_id)

    # When an issue is assigned, notify users who have reminders enabled
    def webex_notify_room_user(self, text, room_id):
        message = text[0]
        user_id = text[2]
        chatroom_message = text[3]
        chatroom_message_id = text[4]
        self.edit_wbx_message(chatroom_message_id, chatroom_message, room_id, None)
        self.send_directwbx_msg(user_id, message)

    # Resolve the message type and shuttle the data off to cmd_list to be processed
    def message_event(self, json_string, event_type, webex_msg_sender):
        webex_sender_id = json_string['data']['personId']
        msg_id = json_string['data']['id']
        message = self.Api.messages.get(msg_id)
        text = message.text

        self.get_command.user_email_payload(
            webex_msg_sender, webex_sender_id, self.Api.memberships.list(roomId=self.roomID, personId=webex_sender_id)
        )

        if event_type == "Message":
            try:
                pt_id = json_string['data']['parentId']
            except Exception:
                pt_id = msg_id

            text = self.get_command.message_handler(text, event_type, self.roomID, pt_id)
            if text[1] is not None and text[1] == "edit message":
                message = text[2]
                message_id = text[0]
                self.edit_wbx_message(message_id, message, self.roomID, pt_id)
            elif text[1] is not None and text[1] == 'notify user':
                self.webex_notify_room_user(text, self.roomID)
            else:
                self.send_wbx_msg(self.roomID, text, pt_id)

        elif event_type == "Direct Message":
            bot_memberships = self.Api.memberships.list(personId=self.webex_bot_id)

            room_id_list = []

            for i in bot_memberships:
                i = i.to_dict()
                if i['roomType'] == "group":
                    try:
                        verify_membership = self.Api.memberships.list(roomId=i['roomId'], personId=webex_sender_id)
                        for membership in verify_membership:
                            self.logging.debug(membership)
                            room_id_list.append(i['roomId'])
                    except ApiError:
                        verify_membership = None

            self.logging.debug(room_id_list)
            if verify_membership is not None:
                text = self.get_command.message_handler(text, event_type, room_id_list, None)
                self.send_wbx_msg(self.roomID, text, None)
