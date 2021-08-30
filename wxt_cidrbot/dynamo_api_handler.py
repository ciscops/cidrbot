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
    def dynamo_db(self, request, name, status, person_id):
        self.get_dynamo()
        name = self.clean_username(name)

        if request == "repos":
            return self.get_repositories()
        if request ==  "all_users":
            return self.get_all_users()
        if request == "user_info":
            return self.get_user_info(name)
        if request == "create_user":
            return self.create_user(name, status, person_id)
        if request ==  "update_user":
            return self.update_user(name, status, person_id)
        if request == "delete_user":
            return self.delete_user(name)
        return "No request type found"

    # Remove the @ cisco tag from the username. If users join a cidrbot room who don't belong to cisco/don't have the @ tag, this can be changed to clean that
    def clean_username(self, name):
        name = str(name)
        if "@cisco.com" in name:
            name = name.split("@cisco.com")[0]
        return name

    def get_repositories(self):
        self.table = self.dynamodb.Table('cidrbot_repos')
        response = self.table.query(
            KeyConditionExpression=Key('Repositories').eq('Repo_list'))

        repos = response['Items'][0]["Repos"].split(',')
        return repos

    def get_all_users(self):
        response = self.table.scan(
            FilterExpression=Attr('reminders_enabled').eq('on')
        )

        return response

    def get_user_info(self, name):
        response = self.table.query(
            KeyConditionExpression=Key('User').eq(name))

        return response

    def create_user(self, name, status, person_id):
        self.table.put_item(
            Item={
                'User': name,
                'person_id': person_id,
                'reminders_enabled': status
            }
        )

    def update_user(self, name, status, person_id):
        response = self.get_user_info(name)
        self.logging.debug(status)
        if len(response['Items']) == 0:
            self.create_user(name, status, person_id)
        else:
            self.table.update_item(
            Key={'User': name},
            UpdateExpression='SET reminders_enabled = :status',
            ExpressionAttributeValues={
                ':status': status
            }
            )

            if response['Items'][0]['person_id'] is not person_id:
                self.table.update_item(
                Key={'User': name},
                UpdateExpression='SET person_id = :id',
                ExpressionAttributeValues={
                    ':id': person_id
                }
                )

        if status == "on":
            return f"Reminders enabled for user: {name}"
        return f"Reminders disabled for user: {name}"


    def delete_user(self, name):
        self.table.delete_item(
            Key={
                'User': name
            }
        )
