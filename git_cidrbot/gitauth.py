import logging
import os
import sys
import json
import boto3
from boto3.dynamodb.conditions import Key
from webexteamssdk import WebexTeamsAPI
import requests


class gitauth:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
        self.logging = logging.getLogger()

        if "CLIENTID" in os.environ:
            self.client_id = os.getenv("CLIENTID")
        else:
            logging.error("Environment variable CLIENTID must be set")
            sys.exit(1)

        if "CLIENTSECRET" in os.environ:
            self.client_secret = os.getenv("CLIENTSECRET")
        else:
            logging.error("Environment variable CLIENTSECRET must be set")
            sys.exit(1)

        if "CALLBACKURL" in os.environ:
            self.callback_url = os.getenv("CALLBACKURL")
        else:
            logging.error("Environment variable CALLBACKURL must be set")
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

        self.dynamodb = ""
        self.table = ''
        self.Api = WebexTeamsAPI()

    def webhook_request(self, event):
        json_string = event

        if json_string['headers']['referer'] == 'https://github.com/':
            code = json_string['queryStringParameters']['code']
            install_id = json_string['queryStringParameters']['installation_id']

            if json_string['queryStringParameters']['setup_action'] == 'install':
                if 'state' in json_string['queryStringParameters']:
                    state = json_string['queryStringParameters']['state']
                else:
                    self.logging.debug("This is probably a user using the public auth link, abort")
                    return {
                        "statusCode":
                        302,
                        "headers": {
                            "Content-Type": "application/json",
                            "Refresh": "15; url=https://github.com/apps/cidrbot"
                        },
                        "body":
                        json.dumps({
                            f"User authenticated app without using webex auth flow":
                            "Please uninstall app (Uninstall cidrbot) then follow this process: " +
                            f" 1) Invite the bot to a secure webex teams room " + f" 2) Type @CIDRbot add repo " +
                            f" 3) Complete the auth process by clicking the link the bot messages you " +
                            f" 4) You will receive a message in both the room and direct messages that the bot authed successfully. REDIRECTING IN 15 SECONDS"
                        })
                    }

                payload = self.check_payload(code, state)
                if payload is not None:
                    state_status = self.check_state(state)
                    if state_status is not False:
                        self.logging.debug("Success the state matches and the payload was true")
                        #self.logging.debug(str(payload) + " " + str(state) + " " + str(state_status))

                        person_id = state_status['personId']
                        room_id = state_status['roomId']
                        pt_id = state_status['ptId']

                        room = self.Api.rooms.get(room_id)
                        room_name = room.title

                        start = payload.find("access_token=") + len("access_token=")
                        end = payload.find("&expires_in")
                        token = payload[start:end]

                        repo_info = self.git_user_info(
                            token, f'https://api.github.com/user/installations/{install_id}/repositories'
                        )
                        user_info = self.git_user_info(token, f'https://api.github.com/user')

                        repo_info_dict = json.loads(repo_info)
                        user_info_dict = json.loads(user_info)

                        user_id = user_info_dict['id']
                        count = repo_info_dict['total_count']
                        repo_list = ''
                        i = 0
                        while i < count:
                            repo_full_name = repo_info_dict['repositories'][i]['full_name']

                            Repo_hypr_lnk = f'<a href="{"https://github.com/" + repo_full_name}">{repo_full_name}</a>'
                            repo_list += Repo_hypr_lnk + ", "
                            i += 1

                        text_direct = f"Authentication successful, added {repo_list} to {room_name}"
                        text = f"{repo_list} added, you can now interact with github in the following format: **@CIDRbot list issues in repoPath/repoName**"

                        post_direct_message = {'toPersonId': person_id, 'markdown': text_direct}

                        post_message = {'roomId': room_id, 'parentId': pt_id, 'markdown': text}

                        self.add_installation(str(user_id), install_id, person_id, room_id, token)
                        self.send_webex_message(post_direct_message)
                        self.send_webex_message(post_message)

                        self.logging.debug("Auth cycle completed, redirecting user")
                        return None

                    self.logging.debug("Bad state, no open requests")
                    return None

                self.logging.debug("Bad payload can't contact github")
                return None

            self.logging.debug("Bad setup action")
            return None

        self.logging.debug(json_string['headers']['referer'])
        self.logging.debug("Unknown referer")
        return None

    def git_user_info(self, token, URL):
        headers = {'Authorization': 'token ' + token, 'Accept': 'application/vnd.github.v3+json'}
        session = requests.Session()
        response = session.get(URL, headers=headers)
        if response.status_code == 200:
            self.logging.debug("Git user info retrieved")
            resp = response.text
            return resp

        self.logging.debug(str(response.status_code))
        self.logging.debug(str(response.text))
        return None

    def send_webex_message(self, post_data):
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

    def add_installation(self, user_id, install_id, person_id, room_id, token):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table('active_github_installations')

        self.table.put_item(
            Item={
                'user_id': user_id,
                'installation_id': install_id,
                'person_id': person_id,
                'room_id': room_id,
                'access_token': token
            }
        )

    def check_state(self, state):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table('cidrbot-users-repos')

        all_room_ids = self.table.scan()

        state_condition = False
        for i in all_room_ids['Items']:
            response = self.table.query(KeyConditionExpression=Key('room_id').eq(i['room_id']))
            if state in response['Items'][0]['auth_requests']:
                state_condition = response['Items'][0]['auth_requests'][state]

                self.table.update_item(
                    Key={'room_id': i['room_id']},
                    UpdateExpression="REMOVE #auth.#userauth",
                    ExpressionAttributeNames={
                        '#auth': 'auth_requests',
                        '#userauth': state
                    }
                )

                break

        return state_condition

    def check_payload(self, code, state):
        URL = f'https://github.com/login/oauth/access_token'
        headers = {"Access-Control-Allow-Origin": "*"}
        post_data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': code,
            'redirect_uri': self.callback_url,
            'state': state
        }

        response = requests.post(URL, json=post_data, headers=headers)
        if response.status_code == 200:
            self.logging.debug("Access key granted")
            resp = str(response.text)
            return resp

        self.logging.debug(str(response.status_code))
        self.logging.debug(str(response.text))
        return None
