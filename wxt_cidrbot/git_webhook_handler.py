import logging
import os
import sys
import json
import boto3
from boto3.dynamodb.conditions import Key
from webexteamssdk import WebexTeamsAPI
import requests
from wxt_cidrbot import git_api_handler
from wxt_cidrbot import dynamo_api_handler


class gitwebhook:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
        self.logging = logging.getLogger()

        if 'WEBEX_TEAMS_ACCESS_TOKEN' in os.environ:
            self.wxt_access_token = os.getenv("WEBEX_TEAMS_ACCESS_TOKEN")
        else:
            logging.error("Environment variable WEBEX_TEAMS_ACCESS_TOKEN must be set")
            sys.exit(1)

        if "WEBEX_BOT_ID" in os.environ:
            self.webex_bot_id = os.getenv("WEBEX_BOT_ID")
        else:
            logging.error("Environment variable WEBEX_BOT_ID must be set")
            sys.exit(1)

        if "DYNAMODB_INSTALLATION_TABLE" in os.environ:
            self.db_installation_name = os.getenv("DYNAMODB_INSTALLATION_TABLE")
        else:
            logging.error("Environment variable DYNAMODB_INSTALLATION_TABLE must be set")
            sys.exit(1)

        if "DYNAMODB_ROOM_TABLE" in os.environ:
            self.db_room_name = os.getenv("DYNAMODB_ROOM_TABLE")
        else:
            logging.error("Environment variable DYNAMODB_ROOM_TABLE must be set")
            sys.exit(1)

        self.git_handle = git_api_handler.githandler()
        self.dynamo = dynamo_api_handler.dynamoapi()
        self.Api = WebexTeamsAPI()
        self.dynamodb = ""
        self.table = ''
        self.room_id = ''

    def webhook_request(self, event):
        json_string = json.loads((event["body"]))
        installation_id = json_string['installation']['id']
        event_action = json_string['action']
        x_event_type = event['headers']['x-github-event']

        if event_action in ('added', 'removed'):
            event_info = self.check_installation(installation_id)

            room_id = event_info[0]['room_id']
            token = event_info[0]['access_token']
            person_id = event_info[0]['person_id']
            message_add_repo = ""
            message_remove_repo = ""

            self.dynamodb = boto3.resource('dynamodb')
            self.table = self.dynamodb.Table(self.db_room_name)

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

            room = self.Api.rooms.get(room_id)
            room_name = room.title

            message = f"Repos updated for room: {room_name} \n"

            if len(message_add_repo) > 0:
                message += f"**Added:**\n" + message_add_repo
            if len(message_remove_repo) > 0:
                message += f"**Removed:**\n" + message_remove_repo

            self.Api.messages.create(toPersonId=person_id, markdown=message)

        elif event_action == 'deleted':
            removed_repos = self.delete_installation(installation_id)
            message_uninstall = "A Cidr installation was just removed from this room. \n The following repos are no longer avaliable \n"

            if len(removed_repos) > 0:
                for repo in removed_repos:
                    message_uninstall += f" - " + repo + "\n"

                self.Api.messages.create(self.room_id, markdown=message_uninstall)

        elif x_event_type in ('issues', 'pull_request'):
            if event_action == 'opened':
                self.triage_issue(installation_id, json_string, x_event_type)

    # Assign a new github issue/pr on webhook
    def triage_issue(self, installation_id, json_string, x_event_type):
        event_info = self.check_installation(installation_id)
        issue_type = "Pull request"
        query_key = "pull_request"

        # Issues and prs have different dict structures
        if x_event_type == 'issues':
            issue_type = "Issue"
            query_key = "issue"
            issue_num = json_string['issue']['number']
        else:
            issue_num = json_string['number']

        room_id = event_info[0]['room_id']

        try:
            triage_list = self.dynamo.get_triage(room_id)
            repos = self.dynamo.get_repositories(room_id)
        except Exception:
            self.logging.debug("Error retrieving triage users and/or repos")
            sys.exit(1)

        issue_title = json_string[query_key]['title']
        issue_url = json_string[query_key]['url']
        issue_user = json_string[query_key]['user']['login']
        repo_name = json_string['repository']['full_name']
        repo_url = json_string['repository']['html_url']

        hyperlink_format = f'<a href="{issue_url}">{issue_title}</a>'
        hyperlink_format_repo = f'<a href="{repo_url}">{repo_name}</a>'
        message = f"{issue_type} {hyperlink_format} created in {hyperlink_format_repo}. Performing automated triage:"

        if len(triage_list) < 1:
            self.logging.debug("No triage users, quitting triage")
            sys.exit(1)

        URL = f'https://webexapis.com/v1/messages'
        headers = {'Authorization': 'Bearer ' + self.wxt_access_token, 'Content-type': 'application/json;charset=utf-8'}
        post_message = {'roomId': room_id, 'markdown': message}
        response = requests.post(URL, json=post_message, headers=headers)
        if response.status_code == 200:
            self.logging.debug("Message created successfully")
            msg_edit_id = json.loads(str(response.text))["id"]
        else:
            self.logging.debug("Status code %s | text %s", str(response.status_code), str(response.text))

        session = requests.Session()
        self.logging.debug("Starting triage")
        author_list = []
        user_issue_count = []

        for triage_list_user in triage_list:
            author_list.append(triage_list_user)
            self.logging.debug("Adding %s", triage_list_user)

        query_repo = ""
        for repo in repos:
            self.logging.debug("repo: %s", repo)
            query_repo += f" repo:{repo} "

        for author in author_list:
            self.logging.debug("Checking issue count for Author: %s", author)
            issue_query = f"state:open type:issue assignee:{author}" + query_repo
            full_issue_url = f"https://api.github.com/search/issues?q=" + issue_query

            pr_query = f"state:open type:pr review-requested:{author}" + query_repo
            full_pr_url = f"https://api.github.com/search/issues?q=" + pr_query

            issue_search = session.get(full_issue_url, headers={})
            issue_count = issue_search.json()['total_count']

            pr_search = session.get(full_pr_url, headers={})
            pr_count = pr_search.json()['total_count']

            issue_count_dict = {'issues': issue_count + pr_count, 'username': author}
            user_issue_count.append(issue_count_dict)

        issue_count_sorted = sorted(user_issue_count, key=lambda i: i['issues'])
        self.logging.debug(issue_count_sorted)

        user_to_assign = None
        self.git_handle.room_and_edit_id(room_id, None)

        for user in issue_count_sorted:
            if issue_user != user['username']:
                user_to_assign = user['username']
                self.logging.debug("Picking user with least issues: %s", user_to_assign)

                git_user_info = requests.get('https://api.github.com/users/' + user_to_assign)
                full_name = git_user_info.json()['name']

                reply_message = self.git_handle.git_assign(repo_name, issue_num, user_to_assign, 'assign', full_name)
                self.logging.debug("assigning result %s", reply_message)
                if 'Error: **invalid user**' in reply_message:
                    self.logging.debug("Invalid user, cannot assign %s: removing from triage list", user_to_assign)
                    self.dynamo.remove_triage_user(user_to_assign, room_id)
                    remove_triage_message = f"{user_to_assign} cannot be assigned because they do not have access to the repo/org, removing user from triage list"
                    self.Api.messages.create(room_id, markdown=remove_triage_message, parentId=msg_edit_id)
                    continue
                break
        self.Api.messages.create(room_id, markdown=reply_message, parentId=msg_edit_id)

    def edit_repo(self, room_id, repo, token, request):
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
                        '#repo': 'repos',
                        '#reponame': repo
                    },
                    ExpressionAttributeValues={':name': token}
                )
        else:
            self.table.update_item(
                Key={'room_id': room_id},
                UpdateExpression="REMOVE #repo.#reponame",
                ExpressionAttributeNames={
                    '#repo': 'repos',
                    '#reponame': repo
                }
            )

    def delete_installation(self, installation_id):
        event_info = self.check_installation(installation_id)

        self.room_id = event_info[0]['room_id']
        token = event_info[0]['access_token']

        self.table.delete_item(Key={'installation_id': str(installation_id)})
        self.table = self.dynamodb.Table(self.db_room_name)

        response = self.table.query(KeyConditionExpression=Key('room_id').eq(self.room_id))

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
                        '#reponame': repo
                    }
                )

        return removed_repo_list

    def check_installation(self, installation_id):
        self.dynamodb = boto3.resource('dynamodb')
        self.table = self.dynamodb.Table(self.db_installation_name)

        try:
            response = self.table.query(KeyConditionExpression=Key('installation_id').eq(str(installation_id)))
        except Exception:
            self.logging.debug('Cannot find record, quitting...')
            sys.exit(1)

        return response['Items']
