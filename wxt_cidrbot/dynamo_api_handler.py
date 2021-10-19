import logging
import os
import sys
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
        self.table = self.dynamodb.Table('cidrbot_user_message_preferences')

    # Start connection to dynamo. This is done as a function and not in the init because dynamo isn't necessarily called each time the lambda function is run
    def dynamo_db(self, request, name, status, person_id, full_name, room_id):
        self.get_dynamo()
        name = self.clean_username(name)


        if request == "create_room":
            return self.create_room(room_id, name)
        if request == "delete_room":
            return self.delete_room(room_id)
        if request == "all_ids":
            return self.get_all_ids()
        if request == "repos":
            return self.get_repositories(room_id)
        if request == "all_users":
            return self.user_dict(room_id)
        if request ==  "notif_users":
            return self.get_notif_users()
        if request == "user_info":
            return self.get_user_info(name, room_id)
        if request == "create_user":
            return self.create_user(name, status, person_id, full_name)
        if request ==  "update_user":
            return self.update_user(name, status, person_id, room_id)
        if request == "delete_user":
            return self.delete_user(name)
        if request == "add repo":
            return self.update_repo_list(name, request, room_id)
        if request == "remove repo":
            return self.update_repo_list(name, request, room_id)
        return "No request type found"

    def create_room(self, room_id, name):
        self.table = self.dynamodb.Table('cidrbot-users-repos')
        self.table.put_item(Item={'room_id':room_id})

        self.logging.debug(name)
        self.logging.debug(len(name))

        sys.exit(1)


        #self.table.update_item(
        #    Key={'room_id': room_id},
        #    UpdateExpression="set #user.#username= :name",
        #    ExpressionAttributeNames={
        #        '#user': 'users',
        #        '#username' : name
        #    },
        #    ExpressionAttributeValues = {
        #        ':name': {"M" : { "reminders_enabled" : { "S" : "off" },
        #                        "dup_status" : { "BOOL" : dup_status },
        #                        "first_name" : { "S" : first_name },
        #                        "person_id" : { "S" : person_id }}}
        #        })





    def delete_room(self, room_id):
        self.table = self.dynamodb.Table('cidrbot-users-repos')
        self.table.delete_item(Key={'room_id': room_id})

        try:
            response = self.table.query(
                KeyConditionExpression=Key('room_id').eq(room_id))
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
        self.table = self.dynamodb.Table('cidrbot-users-repos')
        all_room_ids = self.table.scan()

        ids = []
        for i in all_room_ids['Items']:
            ids.append(i['room_id'])

        self.logging.debug(ids)
        return ids

    def user_dict(self, room_id):
        self.table = self.dynamodb.Table('cidrbot-users-repos')
        response = self.table.query(
            KeyConditionExpression=Key('room_id').eq(room_id))

        return response['Items'][0]['users']

    def get_repositories(self, room_id):
        self.table = self.dynamodb.Table('cidrbot-users-repos')
        response = self.table.query(
            KeyConditionExpression=Key('room_id').eq(room_id))

        repo_dict = response['Items'][0]['repos']
        repo_list = []

        for i in repo_dict:
            repo_list.append(i)

        return repo_list

    def update_repo_list(self, name, request, room_id):
        # If no repos exist, create the map first
        self.table = self.dynamodb.Table('cidrbot-users-repos')

        response = self.table.query(
            KeyConditionExpression=Key('room_id').eq(room_id))

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
                            '#reponame' : name
                        },
                        ExpressionAttributeValues = {
                            ':name': ''
                            })

                return f"Successfuly added repo: {name}"

            return f"Repo: {name} already exists"

        if db_repo_name is not None:
            self.table.update_item(
                        Key={'room_id': room_id},
                        UpdateExpression="REMOVE #repo.#reponame",
                        ExpressionAttributeNames={
                            '#repo': 'repos',
                            '#reponame' : name
                        })

            return f"Successfuly removed repo: {name}"
        return f"Cannot find repo: {name}"

    def get_notif_users(self):
        self.table = self.dynamodb.Table('cidrbot-users-repos')
        all_rooms = self.table.scan()

        return all_rooms

    # rework this, used for assigning issues
    def get_user_info(self, name, room_id):
        self.table = self.dynamodb.Table('cidrbot-users-repos')
        response = self.table.query(
            KeyConditionExpression=Key('room_id').eq(room_id))

        return response['Items'][0]['users'][name]

    #Needed for the new user webhook
    def create_user(self, name, status, person_id, full_name):
        # needs to check if attribute for map exists or not, if not create it

        #Key={'room_id': room_id},
            #            UpdateExpression="set #user.#username = :name",
            ##            ExpressionAttributeNames={
              #              '#user': 'users',
              #              '#username' : name
              #          },
              #          ExpressionAttributeValues = {
              #              ':name': { 'reminders_enabled' : 'on' , 'dup_status' : 'false'} (make sure dup status is a boolean)
              #              })



        first_name = full_name.split(" ")[0].lower()

        response = self.table.scan()

        dup_status = False
        for user in response['Items']:
            if first_name == user['first_name']:
                dup_status = True
                self.table.update_item(

                Key={'User': user['User']},
                    UpdateExpression='SET dup_status = :dup',
                    ExpressionAttributeValues={
                            ':dup': True
                        }
                )


        self.table.put_item(
            Item={
                'User': name,
                'person_id': person_id,
                'reminders_enabled': status,
                'first_name': first_name,
                'dup_status': dup_status
            }
        )

    #This block "should" always run and be successful so the return at the end is okay for now, but linting might not like it
    def update_user(self, name, status, person_id, room_id):
        self.table = self.dynamodb.Table('cidrbot-users-repos')

        for room in room_id:
            response = self.table.query(
            KeyConditionExpression=Key('room_id').eq(room))

            if name in response['Items'][0]['users']:
                if person_id in response['Items'][0]['users'][name]['person_id']:
                    self.table.update_item(
                        Key={'room_id': room},
                        UpdateExpression="set #user.#username.#reminders = :name",
                        ExpressionAttributeNames={
                            '#user': 'users',
                            '#username' : name,
                            '#reminders' : 'reminders_enabled'
                        },
                        ExpressionAttributeValues = {
                            ':name': status
                            })
                    self.logging.debug("updated")

        return f"Successfully turned {status} reminders for {name}"


    #Needs to be done for the webhook
    def delete_user(self, name):
        # Remove dup status if only 1 person remains with it
        response = self.table.query(
            KeyConditionExpression=Key('User').eq(name))

        if len(response['Items']) > 0:
            self.table.delete_item(
                Key={
                    'User': name
                }
            )

        all_users = self.table.scan()
        dup_counter = 0

        user = ''
        for user in all_users['Items']:
            if response['Items'][0]['first_name'] == user['first_name']:
                if response['Items'][0]['User'] != user['User']:
                    dup_counter += 1

        # Change dup status to False if 1 user remains
        if len(user) > 0:
            if 0 < dup_counter < 2:
                self.table.update_item(
                    Key={'User': user['User']},
                        UpdateExpression='SET dup_status = :dup',
                        ExpressionAttributeValues={
                                ':dup': False
                            }
                    )
