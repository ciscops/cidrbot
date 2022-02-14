import logging
import os
import sys
import json
import boto3
from boto3.dynamodb.conditions import Key
from webexteamssdk import WebexTeamsAPI
import requests
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

        elif x_event_type == 'issues' or x_event_type == 'pull_request':
            if event_action == 'opened':
                self.logging.debug("Triaging issue")
                self.triage_issue(installation_id, json_string, x_event_type)

    def triage_issue(self, installation_id, json_string, x_event_type):
        event_info = self.check_installation(installation_id)
        Issue_type = "Pull request"
        query_key = "pull_request"

        self.logging.debug("Checking issue type")
        if x_event_type == 'issues':
            issue_type = "Issue"
            query_key = "issue"

        room_id = event_info[0]['room_id']
        issue_title = json_string[query_key]['title']
        issue_url = json_string[query_key]['url']
        user = json_string[query_key]['user']['login']
        repo_name = json_string['repository']['full_name']
        repo_url = json_string[query_key]['repository_url']
        self.logging.debug("Creating room message")

        hyperlink_format = f'<a href="{issue_url}">{issue_title}</a>'
        hyperlink_format_repo = f'<a href="{repo_url}">{repo_name}</a>'
        message = f"{issue_type} {hyperlink_format} created in {hyperlink_format_repo}. Performing automated triage:"

        try:
            triage = self.dynamo.get_triage(room_id)
            repos = self.dynamo.get_repositories(room_id)
        except Exception:
            self.logging.debug("Error retrieving triage users and/or repos")
            sys.exit(1)

        if len(triage) < 1:
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

        for user in triage:
            author_list.append(user)
            self.logging.debug("Adding %s", user)

        query_repo = ""
        for repo in repos:
            self.logging.debug("repo: %s", repo)
            query_repo += f" repo:{repo} "

        for author in author_list:
            self.logging.debug("Checking issue count for Author: %s", author)
            issue_query = f"state:open author:{author}" + query_repo
            full_issue_url = f"https://api.github.com/search/issues?q=" + issue_query
            issue_search = session.get(full_issue_url, headers={})
            issue_count = issue_search.json()['total_count']
            self.logging.debug(issue_search.json())
            self.logging.debug(issue_search.json()['total_count'])
            issue_count_dict = {'issues': issue_count, 'username': author}
            user_issue_count.append(issue_count_dict)

        issue_count_sorted = sorted(user_issue_count, key = lambda i: i['issues'])
        self.logging.debug(issue_count_sorted)
        self.logging.debug("Picking user with least issues: %s", issue_count_sorted[0]['username'])
        triage_user = issue_count_sorted[0]['username']
        git_user_info = requests.get('https://api.github.com/users/' + triage_user)
        full_name = git_user_info.json()['name']
        reply_message = f"{full_name} has been assigned to issue {hyperlink_format}"
        self.Api.messages.create(room_id, markdown=reply_message, parentId=msg_edit_id)


        #query_author_issue = f"is:issue state:open author:{author}"
        #query_author_pr = f"is:pr state:open author:{author}"

        #full_query_issue = query_author_issue + query_repo
        #full_query_pr = query_author_pr + query_repo
        #url_issue = f"https://api.github.com/search/issues?q=" + full_query_issue
        #url_pr = f"https://api.github.com/search/issues?q=" + full_query_pr
        #issue_search = session.get(url_issue, headers={})
        #pr_search = session.get(url_pr, headers={})
        #self.logging.debug(issue_search.json())
        #self.logging.debug(pr_search.json())





        #self.Api.messages.create(

    #        room_id, markdown=message, parentId=msg_edit_id)

    #Do private repos need keys?
    #Does a new issue do triage based on a persons issues, prs, or both?
    #Do any and all repos authed to a room get triage instantly?

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
