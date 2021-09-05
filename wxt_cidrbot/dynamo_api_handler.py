import logging
import os
import boto3
from boto3.dynamodb.conditions import Key, Attr


class dynamoapi:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
        self.logging = logging.getLogger()

        # Init global vars, which immediately get converted to objects in exactly 4 lines of code. This is pylinting's fault! Not my choice :((
        self.dynamodb = ""
        self.table = ""

    def get_dynamo(self):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table('cidrbot_user_message_preferences')

    # Start connection to dynamo. This is done as a function and not in the init because dynamo isn't necessarily called each time the lambda function is run
    def dynamo_db(self, request, name, status, person_id, full_name):
        self.get_dynamo()
        name = self.clean_username(name)

        if request == "repos":
            return self.get_repositories()
        if request == "all_users":
            return self.user_dict()
        if request == "notif_users":
            return self.get_notif_users()
        if request == "user_info":
            return self.get_user_info(name)
        if request == "create_user":
            return self.create_user(name, status, person_id, full_name)
        if request == "update_user":
            return self.update_user(name, status, person_id, full_name)
        if request == "delete_user":
            return self.delete_user(name)
        if request == "add repo":
            return self.update_repo_list(name, request)
        if request == "remove repo":
            return self.update_repo_list(name, request)
        return "No request type found"

    # Remove the @ cisco tag from the username. If users join a cidrbot room who don't belong to cisco/don't have the @ tag, this can be changed to clean that
    def clean_username(self, name):
        name = str(name)
        if "@cisco.com" in name:
            name = name.split("@cisco.com")[0]
        return name

    def user_dict(self):
        all_users = self.table.scan()

        return all_users

    def get_repositories(self):
        self.table = self.dynamodb.Table('cidrbot_repos')
        response = self.table.scan()
        repo_list = ""
        for repo in response['Items']:
            repo_list += repo['Repositories'] + ","
        repo_list = repo_list[:-1]
        return repo_list.split(',')

    def update_repo_list(self, name, request):
        self.table = self.dynamodb.Table('cidrbot_repos')
        db_repo_name = None
        response = self.table.query(KeyConditionExpression=Key('Repositories').eq(name))

        if len(response['Items']) > 0:
            db_repo_name = response['Items'][0]['Repositories']

        if request == "remove repo":
            if db_repo_name is not None and db_repo_name == name:
                self.table.delete_item(Key={'Repositories': name})
                return f"Successfuly removed repo: {name}"
            return f"Cannot find repo: {name}"

        if db_repo_name == name:
            return f"Repo: {name} already exists"

        self.table.put_item(Item={'Repositories': name})
        return f"Successfuly added repo: {name}"

    def get_notif_users(self):
        response = self.table.scan(FilterExpression=Attr('reminders_enabled').eq('on'))

        return response

    def get_user_info(self, name):
        response = self.table.query(KeyConditionExpression=Key('User').eq(name))

        return response

    def create_user(self, name, status, person_id, full_name):
        first_name = full_name.split(" ")[0].lower()

        response = self.table.scan()

        dup_status = False
        for user in response['Items']:
            if first_name == user['first_name']:
                dup_status = True
                self.table.update_item(
                    Key={'User': user['User']},
                    UpdateExpression='SET dup_status = :dup',
                    ExpressionAttributeValues={':dup': True}
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

    def update_user(self, name, status, person_id, full_name):
        response = self.get_user_info(name)
        self.logging.debug(status)
        if len(response['Items']) == 0:
            self.create_user(name, status, person_id, full_name)
        else:
            self.table.update_item(
                Key={'User': name},
                UpdateExpression='SET reminders_enabled = :status',
                ExpressionAttributeValues={':status': status}
            )

            if response['Items'][0]['person_id'] is not person_id:
                self.table.update_item(
                    Key={'User': name},
                    UpdateExpression='SET person_id = :id',
                    ExpressionAttributeValues={':id': person_id}
                )

        if status == "on":
            return f"Reminders enabled for user: {name}"
        return f"Reminders disabled for user: {name}"

    def delete_user(self, name):
        # Remove dup status if only 1 person remains with it
        response = self.table.query(KeyConditionExpression=Key('User').eq(name))

        if len(response['Items']) > 0:
            self.table.delete_item(Key={'User': name})

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
                    ExpressionAttributeValues={':dup': False}
                )
