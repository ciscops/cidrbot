import logging
import os
import boto3
from boto3.dynamodb.conditions import Key
import requests
import sys
import json
from wxt_cidrbot import dynamo_api_handler
from webexteamssdk import WebexTeamsAPI

class gitwebhook:
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

        self.dynamo = dynamo_api_handler.dynamoapi()
        self.Api = WebexTeamsAPI()
        self.dynamodb = ""
        self.table = ''
        self.room_id = ''

    def webhook_request(self, event):
        json_string = json.loads((event["body"]))
        installation_id = json_string['installation']['id']
        event_action = json_string['action']
        github_login_id = json_string['installation']['account']['id']

        if event_action == 'added' or event_action == 'removed':
            event_info = self.check_installation(installation_id, github_login_id)

            room_id = event_info[0]['room_id']
            token = event_info[0]['access_token']
            name = event_info[0]['user_name']
            message_add_repo = ""
            message_remove_repo = ""

            self.dynamodb = boto3.resource('dynamodb')
            self.table = self.dynamodb.Table('cidrbot-users-repos')
            user_reminders = self.dynamo.get_user_info(name, room_id)

            for repo_added in json_string['repositories_added']:
                if len(repo_added) > 0:
                    repo = repo_added['full_name']
                    message_add_repo += f" - " + repo + "\n"
                    self.edit_repo(room_id, repo, token, "add")

            for repo_removed in json_string['repositories_removed']:
                if len(repo_removed) > 0:
                    repo = repo_removed['full_name']
                    message_remove_repo += f" - " + repo + "\n"
                    self.edit_repo(room_id, repo, token, "remove")

            if user_reminders['reminders_enabled'] == 'on':
                person_id = user_reminders['person_id']
                room = self.Api.rooms.get(room_id)
                room_name = room.title

                message = f"Repos updated for room: {room_name} \n"

                if len(message_add_repo) > 0:
                    message += f"**Added:**\n" + message_add_repo
                if len(message_remove_repo) > 0:
                    message += f"**Removed:**\n"+ message_remove_repo

                self.Api.messages.create(toPersonId=person_id, markdown=message)

        elif event_action == 'deleted':
            removed_repos = self.delete_installation(installation_id, github_login_id)
            message_uninstall = "A Cidr installation was just removed from this room. \n The following repos are no longer avaliable \n"

            if len(removed_repos) > 0:
                for repo in removed_repos:
                    message_uninstall += f" - " + repo + "\n"

                self.Api.messages.create(self.room_id, markdown=message_uninstall)    

    def edit_repo(self, room_id, repo, token, request):

        if request == "add":
            response = self.table.query(
                KeyConditionExpression=Key('room_id').eq(room_id))

            db_repo_name = None
            if repo in response['Items'][0]['repos']:
                db_repo_name = repo

            if db_repo_name is None:
                self.table.update_item(
                        Key={'room_id': room_id},
                        UpdateExpression="set #repo.#reponame= :name",
                        ExpressionAttributeNames={
                            '#repo': 'repos',
                            '#reponame' : repo
                        },
                        ExpressionAttributeValues = {
                            ':name': token
                            })
        else:
            self.table.update_item(
                    Key={'room_id': room_id},
                    UpdateExpression="REMOVE #repo.#reponame",
                    ExpressionAttributeNames={
                        '#repo': 'repos',
                        '#reponame' : repo
                    })

    def delete_installation(self, installation_id, github_login_id):
        event_info = self.check_installation(installation_id, github_login_id)

        self.room_id = event_info[0]['room_id']
        token = event_info[0]['access_token']

        self.table.delete_item(Key={'installation_id': str(installation_id)})
        self.table = self.dynamodb.Table('cidrbot-users-repos')

        response = self.table.query(
            KeyConditionExpression=Key('room_id').eq(self.room_id))

        removed_repo_list = []

        for repo in response['Items'][0]['repos']:
            self.logging.debug("checking repo")
            if response['Items'][0]['repos'][repo] == token:
                removed_repo_list.append(repo)

                self.table.update_item(
                    Key={'room_id': self.room_id},
                    UpdateExpression="REMOVE #repo.#reponame",
                    ExpressionAttributeNames={
                        '#repo': 'repos',
                        '#reponame' : repo
                    })

        return removed_repo_list


    def check_installation(self, installation_id, github_id):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table('active_github_installations')

        try:
            response = self.table.query(
            KeyConditionExpression=Key('installation_id').eq(str(installation_id)))
        except Exception:
            self.logging.debug('Cannot find record, quitting...')
            sys.exit(1)


        if response['Items'][0]['user_id'] == str(github_id):
            return response['Items']

        self.logging.debug("Github user id doesn't match, quitting...")
        sys.exit(1)
