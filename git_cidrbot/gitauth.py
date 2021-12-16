import logging
import os
import sys
import base64
import json
import time
import cryptography
import jwt
import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from webexteamssdk import WebexTeamsAPI
import requests


class gitauth:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
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

        if "DYNAMODB_ROOM_TABLE" in os.environ:
            self.db_room_name = os.getenv("DYNAMODB_ROOM_TABLE")
        else:
            logging.error("Environment variable DYNAMODB_ROOM_TABLE must be set")
            sys.exit(1)

        if "DYNAMODB_INSTALLATION_TABLE" in os.environ:
            self.db_installation_name = os.getenv("DYNAMODB_INSTALLATION_TABLE")
        else:
            logging.error("Environment variable DYNAMODB_INSTALLATION_TABLE must be set")
            sys.exit(1)

        if "DYNAMODB_AUTH_TABLE" in os.environ:
            self.db_auth_name = os.getenv("DYNAMODB_AUTH_TABLE")
        else:
            logging.error("Environment variable DYNAMODB_AUTH_TABLE must be set")
            sys.exit(1)

        if "SECRET_NAME" in os.environ:
            self.secret_name = os.getenv("SECRET_NAME")
        else:
            logging.error("Environment variable SECRET_NAME must be set")
            sys.exit(1)

        if "REGION_NAME" in os.environ:
            self.region_name = os.getenv("REGION_NAME")
        else:
            logging.error("Environment variable REGION_NAME must be set")
            sys.exit(1)

        if "APP_ID" in os.environ:
            self.app_id = os.getenv("APP_ID")
        else:
            logging.error("Environment variable APP_ID must be set")
            sys.exit(1)

        self.dynamodb = ""
        self.table = ''
        self.Api = WebexTeamsAPI()
        self.private_key = ''

    def get_git_key(self):
        session = boto3.session.Session()
        client = session.client(service_name='secretsmanager', region_name=self.region_name)

        try:
            get_secret_value_response = client.get_secret_value(SecretId=self.secret_name)

        except ClientError as e:
            if e.response['Error']['Code'] == 'DecryptionFailureException':
                raise e
            elif e.response['Error']['Code'] == 'InternalServiceErrorException':
                raise e
            elif e.response['Error']['Code'] == 'InvalidParameterException':
                raise e
            elif e.response['Error']['Code'] == 'InvalidRequestException':
                raise e
            elif e.response['Error']['Code'] == 'ResourceNotFoundException':
                raise e
        else:
            if 'SecretString' in get_secret_value_response:
                secret = get_secret_value_response['SecretString']
                self.private_key = secret
            else:
                decoded_binary_secret = base64.b64decode(get_secret_value_response['SecretBinary'])
                self.private_key = json.loads(decoded_binary_secret)

    def webhook_request(self, event):
        json_string = event

        if json_string['headers']['referer'] == 'https://github.com/':
            #code = json_string['queryStringParameters']['code']
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

                state_status = self.check_state(state)
                if state_status is not False:
                    time_epoch = int(time.time())

                    payload = {'iat': time_epoch, 'exp': time_epoch + (10 * 60), 'iss': self.app_id}

                    self.get_git_key()
                    encoded_key = jwt.encode(payload, self.private_key, algorithm="RS256")

                    token_payload = self.create_token(install_id, encoded_key)
                    if token_payload is not None:
                        self.logging.debug("Success the state matches and the payload was true")
                        #self.logging.debug(str(token_payload) + " " + str(state) + " " + str(state_status))

                        person_id = state_status[0]['personId']
                        room_id = state_status[0]['roomId']
                        pt_id = state_status[0]['ptId']

                        room = self.Api.rooms.get(room_id)
                        room_name = room.title

                        payload_dict = json.loads(token_payload)
                        token = payload_dict['token']

                        expire_date = int(time.time()) + 3600

                        repo_info = self.git_repo_info(token, f'https://api.github.com/installation/repositories')
                        user_info = self.git_user_info(
                            encoded_key, f'https://api.github.com/app/installations/{install_id}'
                        )

                        repo_info_dict = json.loads(repo_info)
                        user_info_dict = json.loads(user_info)

                        self.logging.debug(user_info_dict)
                        self.logging.debug(repo_info_dict)

                        user_id = user_info_dict['account']['id']
                        user_name = user_info_dict['account']['login']
                        count = repo_info_dict['total_count']
                        repo_path_list = []

                        repo_list = ''
                        i = 0
                        while i < count:
                            repo_full_name = repo_info_dict['repositories'][i]['full_name']
                            repo_path_list.append(repo_full_name.lower())
                            Repo_hypr_lnk = f'<a href="{"https://github.com/" + repo_full_name}">{repo_full_name}</a>'
                            repo_list += " - " + Repo_hypr_lnk + " \n "
                            i += 1

                        text_direct = f"Authentication successful, the following repos are added to room: {room_name} \n" + repo_list
                        text = (
                            f"Authentication successful, type @CIDRbot help to begin. To add repos, please" +
                            ''' visit <a href="https://github.com/settings/installations/">Github applications</a> and click "configure" for the cidrbot app '''
                        )

                        post_direct_message = {'toPersonId': person_id, 'markdown': text_direct}

                        post_message = {'roomId': room_id, 'parentId': pt_id, 'markdown': text}

                        #self.add_installation(str(user_id), install_id, person_id, user_name, room_id, token, repo_path_list, expire_date, refresh_token)
                        self.add_installation(
                            str(user_id), install_id, person_id, user_name, room_id, token, repo_path_list, expire_date
                        )
                        self.send_webex_message(post_direct_message)
                        self.send_webex_message(post_message)

                        self.logging.debug("Auth cycle completed, redirecting user")
                        return None

                    self.logging.debug("Token payload is none")
                    return {
                        "statusCode":
                        302,
                        "headers": {
                            "Content-Type": "application/json",
                            "Refresh": "15; url=https://github.com/apps/cidrbot"
                        },
                        "body":
                        json.dumps({
                            f"Expired link was used":
                            "Please uninstall cidrbot app and follow the process " +
                            "described by the page you will be redirected to. REDIRECTING IN 15 SECONDS"
                        })
                    }

                self.logging.debug("State status is false")
                return None

            self.logging.debug("Bad setup action")
            return None

        self.logging.debug(json_string['headers']['referer'])
        self.logging.debug("Unknown referer")
        return None

    def git_repo_info(self, token, URL):
        headers = {'Authorization': 'token ' + token, 'Accept': 'application/vnd.github.v3+json'}
        session = requests.Session()
        response = session.get(URL, headers=headers)
        if response.status_code == 200:
            self.logging.debug("Repo info granted")
            resp = response.text
            return resp

        self.logging.debug(str(response.status_code))
        self.logging.debug(str(response.text))
        return None

    def git_user_info(self, encoded_key, URL):
        headers = {"Authorization": "Bearer {}".format(encoded_key), 'Accept': 'application/vnd.github.v3+json'}
        post_data = {}

        response = requests.get(URL, json=post_data, headers=headers)
        if response.status_code == 200:
            self.logging.debug("User info granted")
            resp = str(response.text)
            return resp

        self.logging.debug(str(response.status_code))
        self.logging.debug(str(response.text))
        return None

    def send_webex_message(self, post_data):
        URL = f'https://webexapis.com/v1/messages'
        headers = {'Authorization': 'Bearer ' + self.wxt_access_token, 'Content-type': 'application/json;charset=utf-8'}

        requests.post(URL, json=post_data, headers=headers)

    def add_installation(self, user_id, install_id, person_id, user_name, room_id, token, repo_path_list, expire_date):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(self.db_installation_name)

        self.table.put_item(
            Item={
                'installation_id': install_id,
                'user_id': user_id,
                'user_name': user_name,
                'person_id': person_id,
                'room_id': room_id,
                'access_token': token,
                'expire_date': expire_date,
            }
        )

        self.table = self.dynamodb.Table(self.db_room_name)

        response = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))

        current_repos = response['Items'][0]['repos']

        for repo in repo_path_list:
            db_repo_name = None

            if repo in current_repos:
                db_repo_name = repo

            if db_repo_name is None:
                self.table.update_item(
                    Key={'room_id': room_id},
                    UpdateExpression="set #repo.#reponame= :name",
                    ExpressionAttributeNames={
                        '#repo': 'repos',
                        '#reponame': repo
                    },
                    ExpressionAttributeValues={':name': token}
                )

    def check_state(self, state):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(self.db_auth_name)
        state_condition = False

        current_time = int(time.time())

        try:
            response = self.table.query(KeyConditionExpression=Key('state').eq(state))

            self.logging.debug(current_time)
            self.logging.debug(response['Items'][0]['ttl'])
            if current_time < int(response['Items'][0]['ttl']):
                state_condition = response['Items']
        except Exception:
            pass

        self.table.delete_item(Key={'state': state})

        return state_condition

    def create_token(self, installation_id, encoded_key):
        URL = f'https://api.github.com/app/installations/{installation_id}/access_tokens'
        headers = {"Authorization": "Bearer {}".format(encoded_key), 'Accept': 'application/vnd.github.v3+json'}
        post_data = {}

        response = requests.post(URL, json=post_data, headers=headers)
        if response.status_code == 201:
            self.logging.debug("Access key granted")
            resp = str(response.text)
            return resp

        self.logging.debug(str(response.status_code))
        self.logging.debug(str(response.text))
        return None
