import logging
import os
import sys
from webexteamssdk import WebexTeamsAPI
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

        self.Api = WebexTeamsAPI()
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

                    #string = f'{'user_email': user_email, 'first_name': name, 'duplicate': dup, 'person_id': person_id, 'reminders_enabled': 'off'}'

                    member_info.append({'user_email': user_email, 'first_name': name, 'duplicate': dup, 'person_id': person_id, 'reminders_enabled': 'off'})



            #self.logging.debug(str(member_info) + " " + str(member_list))

            self.Api.messages.create(room_id, markdown=f"Hello, thank you for adding cidrbot to your room \n - Setting up webhooks...")
            self.dynamo.dynamo_db('create_room', member_info, None, None, None, room_id)
        else:
            self.logging.debug("something went wrong")
