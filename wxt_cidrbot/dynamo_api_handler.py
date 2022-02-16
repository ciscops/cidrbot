import logging
import os
import sys
import base64
import json
import datetime
import time
import jwt
import boto3
from boto3.dynamodb.conditions import Key, Attr
from botocore.exceptions import ClientError
import requests


class dynamoapi:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
        self.logging = logging.getLogger()

        if "DYNAMODB_ROOM_TABLE" in os.environ:
            self.db_room_name = os.getenv("DYNAMODB_ROOM_TABLE")
        else:
            logging.error("Environment variable DYNAMODB_ROOM_TABLE must be set")
            sys.exit(1)

        if "DYNAMODB_AUTH_TABLE" in os.environ:
            self.db_auth_name = os.getenv("DYNAMODB_AUTH_TABLE")
        else:
            logging.error("Environment variable DYNAMODB_AUTH_TABLE must be set")
            sys.exit(1)

        if "DYNAMODB_INSTALLATION_TABLE" in os.environ:
            self.db_install_name = os.getenv("DYNAMODB_INSTALLATION_TABLE")
        else:
            logging.error("Environment variable DYNAMODB_INSTALLATION_TABLE must be set")
            sys.exit(1)

        if "APP_ID" in os.environ:
            self.app_id = os.getenv("APP_ID")
        else:
            logging.error("Environment variable APP_ID must be set")
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

        self.dynamodb = ""
        self.table = ""

    def get_dynamo(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(self.db_room_name)

    def add_auth_request(self, state, state_value):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(self.db_auth_name)

        time_to_expire = datetime.datetime.today() + datetime.timedelta(minutes=10)
        expire_date = int(time.mktime(time_to_expire.timetuple()))

        self.table.put_item(
            Item={
                'state': state,
                'personId': state_value['personId'],
                'roomId': state_value['roomId'],
                'ptId': state_value['ptId'],
                'ttl': expire_date
            }
        )

    def create_room(self, room_id, members, id_list):
        self.get_dynamo()
        self.table.put_item(
            Item={
                'room_id': room_id,
                'users': {},
                'repos': {},
                'webhook_ids': id_list,
                'auth_requests': {}
            }
        )

        for member in members:
            email = member['user_email']
            first_name = member['first_name']
            dup_status = member['duplicate']
            person_id = member['person_id']

            self.logging.debug("Adding user %s, %s", email, first_name)
            try:
                self.table.update_item(
                    Key={'room_id': room_id},
                    UpdateExpression="set #user.#username= :name",
                    ExpressionAttributeNames={
                        '#user': 'users',
                        '#username': email
                    },
                    ExpressionAttributeValues={
                        ':name': {
                            'reminders_enabled': 'off',
                            'dup_status': dup_status,
                            'first_name': first_name,
                            'person_id': person_id
                        }
                    }
                )
            except Exception as e:
                self.logging.debug("Error: %s", e.message)
                continue

            self.logging.debug("added user")
            self.logging.debug(email)

    def delete_room(self, room_id):
        self.get_dynamo()
        self.table.delete_item(Key={'room_id': room_id})

        try:
            response = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))
            self.logging.debug("Room could not be deleted")
            self.logging.debug(response)
        except Exception:
            self.logging.debug("Room deleted")

    def add_triage_user(self, room_id, user_name):
        self.get_dynamo()

        try:
            response = self.table.query(
                KeyConditionExpression=Key('room_id').eq(room_id), FilterExpression=Attr('triage').exists()
            )
            user_exists = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))
            if 'triage' in user_exists['Items'][0]:
                if user_name in user_exists['Items'][0]['triage']:
                    return f"{user_name} is already in triage list"
            self.logging.debug(user_exists)

            if response['Count'] == 0:
                self.table.update_item(
                    Key={'room_id': room_id},
                    UpdateExpression='SET #triage= :value',
                    ExpressionAttributeNames={'#triage': 'triage'},
                    ExpressionAttributeValues={':value': {}}
                )
            self.table.update_item(
                Key={'room_id': room_id},
                UpdateExpression="SET #triage.#name= :value",
                ExpressionAttributeNames={
                    '#triage': 'triage',
                    '#name': user_name
                },
                ExpressionAttributeValues={':value': ''}
            )
            return f"Successfully added triage user {user_name}"
        except Exception:
            return f"Cannot add user {user_name}"

    def remove_triage_user(self, user, room_id):
        self.get_dynamo()

        try:
            self.table.update_item(
                Key={'room_id': room_id},
                UpdateExpression="REMOVE #triagelist.#username",
                ExpressionAttributeNames={
                    '#triagelist': 'triage',
                    '#username': user
                }
            )
            return f"Successfully removed {user} from triage list"
        except Exception:
            return f"Cannot remove {user} from triage list"

    def clean_username(self, name):
        name = str(name)
        if "@" in name:
            name = name.split("@", 1)[0]

        return name

    def get_all_ids(self):
        self.get_dynamo()
        all_room_ids = self.table.scan()

        ids = []
        for i in all_room_ids['Items']:
            ids.append(i['room_id'])

        self.logging.debug(ids)
        return ids

    def user_dict(self, room_id):
        self.get_dynamo()
        response = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))

        return response['Items'][0]['users']

    def get_webhooks(self, room_id):
        self.get_dynamo()

        response = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))

        return response['Items'][0]['webhook_ids']

    def get_repositories(self, room_id):
        self.get_dynamo()
        response = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))

        repo_dict = response['Items'][0]['repos']
        repo_list = []

        for i in repo_dict:
            repo_list.append(i)

        return repo_list

    def get_triage(self, room_id):
        self.get_dynamo()
        response = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))

        triage_dict = response['Items'][0]['triage']
        triage_list = []

        for i in triage_dict:
            triage_list.append(i)

        return triage_list

    def get_repo_keys(self, room_id, repo_name):
        self.get_dynamo()
        response = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))

        repo_list = response['Items'][0]['repos']
        token = repo_list[repo_name]

        self.table = self.dynamodb.Table(self.db_install_name)
        installation = self.table.scan(
            FilterExpression=Attr('room_id').contains(room_id) and Attr("access_token").contains(token)
        )

        if installation['Items'][0]['access_token'] == token:
            current_time = int(time.time())
            self.logging.debug(current_time)
            self.logging.debug(installation['Items'][0]['expire_date'])

            if current_time > int(installation['Items'][0]['expire_date']):
                room_id = installation['Items'][0]['room_id']
                token_to_remove = installation['Items'][0]['access_token']
                installation_id = installation['Items'][0]['installation_id']

                session = boto3.session.Session()
                client = session.client(service_name='secretsmanager', region_name=self.region_name)
                try:
                    get_secret_value_response = client.get_secret_value(SecretId=self.secret_name)
                except ClientError as e:
                    raise e
                else:
                    if 'SecretString' in get_secret_value_response:
                        secret = get_secret_value_response['SecretString']
                        private_key = secret
                    else:
                        decoded_binary_secret = base64.b64decode(get_secret_value_response['SecretBinary'])
                        private_key = json.loads(decoded_binary_secret)

                time_epoch = int(time.time())

                payload = {'iat': time_epoch, 'exp': time_epoch + (10 * 60), 'iss': self.app_id}

                encoded_key = jwt.encode(payload, private_key, algorithm="RS256")
                token_payload = self.git_refresh_token(installation_id, encoded_key)
                if token_payload is not None:
                    expire_date = int(time.time()) + 3600

                    payload_dict = json.loads(token_payload)
                    token = payload_dict['token']

                    self.update_access_token(installation_id, token, token_to_remove, expire_date, room_id)

        return token

    def update_access_token(self, install_id, new_token, old_token, time_to_expire, room_id):
        self.table.update_item(
            Key={'installation_id': install_id},
            UpdateExpression="set #token = :new_token, #expire = :tte",
            ExpressionAttributeNames={
                '#token': 'access_token',
                '#expire': 'expire_date'
            },
            ExpressionAttributeValues={
                ':new_token': new_token,
                ':tte': time_to_expire
            }
        )

        self.table = self.dynamodb.Table(self.db_room_name)
        response = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))

        repo_list = response['Items'][0]['repos']

        for repo in repo_list:
            if repo_list[repo] == old_token:
                self.table.update_item(
                    Key={'room_id': room_id},
                    UpdateExpression="set #repo.#reponame= :name",
                    ExpressionAttributeNames={
                        '#repo': 'repos',
                        '#reponame': repo
                    },
                    ExpressionAttributeValues={':name': new_token}
                )

    def git_refresh_token(self, installation_id, encoded_key):
        URL = f'https://api.github.com/app/installations/{installation_id}/access_tokens'
        headers = {"Authorization": "Bearer {}".format(encoded_key), 'Accept': 'application/vnd.github.v3+json'}
        post_data = {}

        response = requests.post(URL, json=post_data, headers=headers)
        if response.status_code == 201:
            self.logging.debug("Refreshed key")
            resp = str(response.text)
            return resp

        self.logging.debug(str(response.status_code))
        self.logging.debug(str(response.text))
        return None

    def update_repo_list(self, name, request, room_id):
        self.get_dynamo()

        response = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))

        db_repo_name = None
        if name in response['Items'][0]['repos']:
            db_repo_name = name

        if request == "add repo":
            if db_repo_name is None:
                self.table.update_item(
                    Key={'room_id': room_id},
                    UpdateExpression="set #repo.#reponame= :name",
                    ExpressionAttributeNames={
                        '#repo': 'repos',
                        '#reponame': name
                    },
                    ExpressionAttributeValues={':name': ''}
                )

                return f"Successfuly added repo: {name}"

            return f"Repo: {name} already exists"

        if db_repo_name is not None:
            self.table.update_item(
                Key={'room_id': room_id},
                UpdateExpression="REMOVE #repo.#reponame",
                ExpressionAttributeNames={
                    '#repo': 'repos',
                    '#reponame': name
                }
            )

            return f"Successfuly removed repo: {name}"
        return f"Cannot find repo: {name}"

    def get_notif_users(self):
        self.get_dynamo()
        all_rooms = self.table.scan()

        return all_rooms

    def get_user_info(self, name, room_id):
        self.get_dynamo()
        name = self.clean_username(name)

        response = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))

        return response['Items'][0]['users'][name]

    def create_user(self, name, person_id, full_name, room_id):
        self.get_dynamo()
        name = self.clean_username(name)

        first_name = full_name.split(" ")[0].lower()

        response = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))

        dup_status = False
        for user in response['Items'][0]['users']:
            if response['Items'][0]['users'][user]['first_name'] == first_name:
                dup_status = True
                self.table.update_item(
                    Key={'room_id': room_id},
                    UpdateExpression="set #user.#username.#dup= :name",
                    ExpressionAttributeNames={
                        '#user': 'users',
                        '#username': name,
                        '#dup': 'dup_status'
                    },
                    ExpressionAttributeValues={':name': dup_status}
                )

        self.table.update_item(
            Key={'room_id': room_id},
            UpdateExpression="set #user.#username= :name",
            ExpressionAttributeNames={
                '#user': 'users',
                '#username': name
            },
            ExpressionAttributeValues={
                ':name': {
                    'reminders_enabled': 'off',
                    'dup_status': dup_status,
                    'first_name': first_name,
                    'person_id': person_id
                }
            }
        )

    def update_user(self, name, status, person_id, room_id):
        self.get_dynamo()
        name = self.clean_username(name)

        for room in room_id:
            response = self.table.query(KeyConditionExpression=Key('room_id').eq(room))

            if name in response['Items'][0]['users']:
                if person_id in response['Items'][0]['users'][name]['person_id']:
                    self.table.update_item(
                        Key={'room_id': room},
                        UpdateExpression="set #user.#username.#reminders = :name",
                        ExpressionAttributeNames={
                            '#user': 'users',
                            '#username': name,
                            '#reminders': 'reminders_enabled'
                        },
                        ExpressionAttributeValues={':name': status}
                    )
                    self.logging.debug("updated")

        return f"Successfully turned {status} reminders for {name}"

    def delete_user(self, name, room_id):
        self.get_dynamo()
        name = self.clean_username(name)

        response = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))

        if len(response['Items'][0]['users'][name]['first_name']) > 0:

            self.table.update_item(
                Key={'room_id': room_id},
                UpdateExpression="REMOVE #user.#username",
                ExpressionAttributeNames={
                    '#user': 'users',
                    '#username': name
                }
            )

            response_check = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))

            dup_counter = 0

            user = ''
            for user in response_check['Items'][0]['users']:
                if response['Items'][0]['users'][name]['first_name'] == response_check['Items'][0]['users'][user][
                    'first_name']:
                    if name != user:
                        dup_counter += 1

            if len(user) > 0:
                if 0 < dup_counter < 2:
                    self.table.update_item(
                        Key={'room_id': room_id},
                        UpdateExpression="set #user.#username.#dup= :name",
                        ExpressionAttributeNames={
                            '#user': 'users',
                            '#username': user,
                            '#dup': 'dup_status'
                        },
                        ExpressionAttributeValues={':name': False}
                    )
