import logging
import os
import boto3
from boto3.dynamodb.conditions import Key


class dynamoapi:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
        self.logging = logging.getLogger()

        self.dynamodb = ""
        self.table = ""

    def get_dynamo(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table('cidrbot-users-repos')

    def create_room(self, room_id, members, id_list):
        self.get_dynamo()
        self.table.put_item(Item={'room_id': room_id, 'users': {}, 'repos': {}, 'webhook_ids': id_list})

        for member in members:
            email = member['user_email']
            first_name = member['first_name']
            dup_status = member['duplicate']
            person_id = member['person_id']

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
