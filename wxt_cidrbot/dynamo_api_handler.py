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
        self.repo_schema_name = '#repo'
        self.reponame_schema = '#reponame'

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
                'auth_requests': {},
                'triage': {}
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
                            'person_id': person_id,
                            'git_name': email  # the user's git name is set to their webex email by default
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

    def update_github_username(self, target_name, alias_name, room_id):
        self.get_dynamo()
        response = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))

        if target_name in response['Items'][0]['users']:
            self.table.update_item(
                Key={'room_id': room_id},
                UpdateExpression="set #user.#username.#gitname = :name",
                ExpressionAttributeNames={
                    '#user': 'users',
                    '#username': target_name,
                    '#gitname': 'git_name'
                },
                ExpressionAttributeValues={':name': alias_name}
            )
            self.logging.debug("updated")
            return f"Successfully updated git username reference for {target_name} to {alias_name}"

        return "Could not update reference, ensure target name is correct **@Cidrbot update name target alias**"

    def update_required_approvals(self, approval_number, repos, room_id):
        self.get_dynamo()

        failed_repo_updates = ""
        successful_repo_updates = ""

        for repo in repos:
            try:
                self.table.update_item(
                    Key={'room_id': room_id},
                    UpdateExpression="set #repo.#reponame.#approvals= :name",
                    ExpressionAttributeNames={
                        self.repo_schema_name: 'repos',
                        self.reponame_schema: repo,
                        '#approvals': 'required_approvals'
                    },
                    ExpressionAttributeValues={':name': approval_number}
                )
                successful_repo_updates += "\n- **" + repo + "**"
            except Exception:
                failed_repo_updates += "\n- **" + repo + "**"

        message = ""
        if failed_repo_updates != "":
            message = f"\n\nThe following repos were not successfully updated: {failed_repo_updates}"

        return f"The following repos were successfully updated: {successful_repo_updates}{message}"

    def get_required_approvals(self, repo_name, room_id):
        self.get_dynamo()

        response = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))

        return int(response['Items'][0]['repos'][repo_name]['required_approvals'])

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
        self.table = self.dynamodb.Table(self.db_install_name)

        repo_install_id = repo_list[repo_name]['installation_id']
        installation_response = self.table.query(KeyConditionExpression=Key('installation_id').eq(str(repo_install_id)))
        token = installation_response['Items'][0]['access_token']

        installation = self.table.scan(
            FilterExpression=Attr('room_id').contains(room_id) and Attr("access_token").contains(token)
        )

        if installation['Items'][0]['access_token'] == token:
            current_time = int(time.time())
            self.logging.debug(current_time)
            self.logging.debug(installation['Items'][0]['expire_date'])

            if current_time > int(installation['Items'][0]['expire_date']):
                room_id = installation['Items'][0]['room_id']
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

                    self.update_access_token(installation_id, token, expire_date)

        return token

    def update_access_token(self, install_id, new_token, time_to_expire):
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

    def edit_repo(self, room_id, repo, installation_id, request):
        self.get_dynamo()
        repo = repo.lower()
        if request == "add":
            response = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))

            db_repo_name = None
            if repo in response['Items'][0]['repos']:
                db_repo_name = repo

            if db_repo_name is None:
                self.table.update_item(
                    Key={'room_id': room_id},
                    UpdateExpression="set #repo.#reponame= :name",
                    ExpressionAttributeNames={
                        self.repo_schema_name: 'repos',
                        self.reponame_schema: repo
                    },
                    ExpressionAttributeValues={
                        ':name': {
                            'installation_id': str(installation_id),
                            'required_approvals': 1
                        }
                    }
                )
        else:
            self.table.update_item(
                Key={'room_id': room_id},
                UpdateExpression="REMOVE #repo.#reponame",
                ExpressionAttributeNames={
                    self.repo_schema_name: 'repos',
                    self.reponame_schema: repo
                }
            )

    def get_notif_users(self):
        self.get_dynamo()
        all_rooms = self.table.scan()

        return all_rooms

    def get_user_info(self, name, room_id):
        self.get_dynamo()
        name = self.clean_username(name)

        response = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))

        if name in response['Items'][0]['users']:
            return response['Items'][0]['users'][name]

        return None

    def create_user(self, name, person_id, full_name, room_id):
        self.get_dynamo()
        name = self.clean_username(name)

        first_name = full_name.split(" ")[0].lower()

        response = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))

        dup_status = False
        for user in response['Items'][0]['users']:
            dynamo_user = response['Items'][0]['users'][user]['first_name']
            if dynamo_user == first_name:
                dup_status = True
                self.table.update_item(
                    Key={'room_id': room_id},
                    UpdateExpression="set #user.#username.#dup= :name",
                    ExpressionAttributeNames={
                        '#user': 'users',
                        '#username': user,
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
                    'person_id': person_id,
                    'git_name': name
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

        if name in response['Items'][0]['users']:
            self.table.update_item(
                Key={'room_id': room_id},
                UpdateExpression="REMOVE #user.#username",
                ExpressionAttributeNames={
                    '#user': 'users',
                    '#username': name
                }
            )

            post_delete_user_query = self.table.query(KeyConditionExpression=Key('room_id').eq(room_id))
            duplicate_named_users = []

            user = ''
            for user in post_delete_user_query['Items'][0]['users']:
                if response['Items'][0]['users'][name]['first_name'] == post_delete_user_query['Items'][0]['users'][
                    user]['first_name']:
                    if name != user:
                        self.logging.debug("User found with duplicate first name: %s", user)
                        self.logging.debug(name)
                        duplicate_named_users.append(user)

            # We only change the status of a duplicate user if they are the only user in a room with that first name
            # Meaning we don't need to change their dup status is more than 1 dup user exists.
            # Only Set dup status to false if duplicate_named_users is 1
            if len(duplicate_named_users) == 1:
                for user in duplicate_named_users:
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
