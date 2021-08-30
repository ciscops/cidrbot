import logging
import os
import sys
import base64
import json
import boto3
import requests
from github import Github
from botocore.exceptions import ClientError
from wxt_cidrbot import dynamo_api_handler
from wxt_cidrbot import webex_edit_message


class githandler:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
        self.logging = logging.getLogger()

        # Initialize Aws secrets information
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

        # Init sibling py files and used global vars
        self.dynamo = dynamo_api_handler.dynamoapi()
        self.webex = webex_edit_message.webex_message()
        self.user_search_name = ""
        self.room_id = ""
        self.msg_edit_id = ""
        self.git_api = ""
        self.token = ""
        self.repos = []

    # Connect to aws secrets, and retrieve the github access token
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
                json_string = json.loads(secret)
                token = json_string['cidrbot_access_token']
                self.git_api = Github(token)
                self.token = token
            else:
                decoded_binary_secret = base64.b64decode(get_secret_value_response['SecretBinary'])
                json_string = json.loads(decoded_binary_secret)
                token = json_string['cidrbot_access_token']
                self.git_api = Github(token)
                self.token = token

    # Determine the reviewer, requested reviewer, or the assignee (if its an issue). The reviewer is currently a disabled feature
    def get_issue_info(self, issue, issue_type):
        if issue_type == "Pr":
            if len(issue['requested_reviewers']) > 0:
                reviewer = ''
                if issue['requested_reviewers'][0]['login'] is not None:
                    for i in issue['requested_reviewers']:
                        reviewer += i['login'] + ', '
                    reviewer = reviewer[:-2]

                if len(reviewer) < 1:
                    reviewer = None

            # Currently disabled method for retrieving the reviewer of a pull request (a requested reviewer who sumbitted a review)
            # Direct http requests to git's rest api won't return 'review_comments' in the json

            #elif issue['review_comments'] > 0:
            #   https://api.github.com/repos/CiscoDevNet/python-viptela/pulls/78/comments
            #   reviewer = None
            #   for i in get_rev:
            #       rev_as_dict = i.raw_data
            #       if rev_as_dict['state'] == 'CHANGES_REQUESTED' or rev_as_dict['state'] == "COMMENTED":
            #          reviewer = i.user.login
            #          break

            else:
                reviewer = None
            return {'issue_type': issue_type, 'user': reviewer}

        self.logging.debug(issue)
        if issue['assignees'] is not None:
            assigned = ""
            for i in issue['assignees']:
                assigned += i['login'] + ', '
            assigned = assigned[:-2]

            if len(assigned) < 1:
                assigned = None
        else:
            assigned = None
        return {'issue_type': issue_type, 'user': assigned}

    # Determine the assigned status of an issue or pr
    def get_assigned_status(self, assigned_user, issue_type, request):
        text = ""
        self.logging.debug(issue_type)
        if assigned_user is not None:
            text += f" | **Assigned**: " + str(assigned_user) + "\n"
            assigned_status = [True, str(assigned_user)]
        else:
            text += "\n"
            assigned_status = [False, None]
        if request == "List":
            return text
        return assigned_status

    # Function that works with scan_repos to format issue and pr text, which will be displayed to the user
    def process_issue(self, issue, request, issue_type, issue_num, assign_type):
        message = ""

        title = issue['title']
        first_four_title = ''
        title_words = title.split(" ")[:5]
        if len(title_words) > 4:
            for index in range(0, 5):
                first_four_title += title_words[index] + " "
            title = first_four_title[:-1] + '...'

        url = issue['html_url']
        hyperlink_format = f'<a href="{url}">{title}</a>'

        text = f"- {issue_type} #{issue_num}: {hyperlink_format}"
        issue_info = self.get_issue_info(issue, issue_type)
        issue_type = issue_info.get('issue_type')
        assigned_user = issue_info.get('user')
        status = self.get_assigned_status(assigned_user, issue_type, request)

        if assign_type != "All":
            if status != "\n":
                return "unassigned"
        message += text + status
        return message

    # Update a local dictionary of all the issues and their relevant information. This is used to get the issues for a specific user
    def update_dict(self, issue_dict, issue, repo_full_name, issue_name, issue_url, issue_type, request):
        issue_info = self.get_issue_info(issue, issue_type)
        assigned_user = issue_info.get('user')
        status = self.get_assigned_status(assigned_user, issue_type, request)
        number = issue['number']
        assigned_status = status[0]
        assigned = status[1]

        issue_dict.update({
            repo_full_name: {
                'name': issue_name,
                'assigned_status': assigned_status,
                'assigned': assigned,
                'url': issue_url,
                'type': issue_type,
                'number': number
            }
        })
        return issue_dict

    # Iterate through a list of repos, and parse the relevant information from two dictionaries
    def scan_repos(self, request, assign_type, repo_name):
        self.get_git_key()
        full_text = f"**{assign_type} Issues:**\n"

        message = f"Retrieving a list of {assign_type} issues, one moment..."
        msg_edit_num = 1
        issue_dict = {}
        session = requests.Session()
        headers = {'Authorization': 'token ' + self.token}
        for repository in repo_name:
            if request == "List":
                if msg_edit_num < 10:
                    message_repo = repository.upper()
                    message += f"\n - Finding issues in repo: {message_repo}..."
                    self.webex.edit_message(self.msg_edit_id, message, self.room_id)
                    msg_edit_num += 1

            repo_url = "https://github.com/" + repository
            repo_text = "\n Repo: " + f'<a href="{repo_url}">{repository}</a>\n'
            all_issues_text = ""
            issue_num = 0

            all_issues = session.get(
                'https://api.github.com/repos/' + repository + '/issues?state=open', headers=headers
            )
            all_prs = session.get('https://api.github.com/repos/' + repository + '/pulls?state=open', headers=headers)

            for pr in all_prs.json():
                number = pr['number']
                if request == "List":
                    text = self.process_issue(pr, request, 'Pr', number, assign_type)
                    if text != 'unassigned':
                        all_issues_text += text
                        issue_num += 1
                else:
                    repo_full_name = repository + ", " + str(issue_num)
                    issue_dict = self.update_dict(
                        issue_dict, pr, repo_full_name, pr['title'], pr['html_url'], 'Pr', request
                    )
                    issue_num += 1

            for issue in all_issues.json():
                number = issue['number']
                if request == "List":
                    if 'pull_request' not in issue:
                        text = self.process_issue(issue, request, 'Issue', number, assign_type)
                        if text != 'unassigned':
                            all_issues_text += text
                            issue_num += 1
                else:
                    if 'pull_request' not in issue:
                        repo_full_name = repository + ", " + str(issue_num)
                        issue_dict = self.update_dict(
                            issue_dict, issue, repo_full_name, issue['title'], issue['html_url'], 'Issue', request
                        )
                        issue_num += 1

            if issue_num > 0:
                full_text += repo_text + all_issues_text
            else:
                full_text += "\n"

        if request == "List":
            full_text += f"\n \n Type **@Cidrbot help** for assigning options"
            return full_text
        return issue_dict

    def user_name(self, search_name):
        self.user_search_name = search_name

    def room_and_edit_id(self, room_id, msg_edit_id):
        self.room_id = room_id
        self.msg_edit_id = msg_edit_id

    # Ensure an issue/pr was assigned. If the username was invalid, this function returns false and the webex user is notified of an invalid username error
    def check_assigned_status(self, search_name, issue_type, repo, issue_number):
        issue = self.git_api.get_repo(repo).get_issue(int(issue_number))
        issue_json = issue.raw_data
        assignee = self.get_issue_info(issue_json, issue_type)
        if assignee.get('user') is not None:
            if search_name in assignee.get('user'):
                return True
        return False

    # Assign the issue to the user, additionally, if their notifications are enabled, send them a message
    def git_assign(self, repo, issue_number, search_name, assign_status, name_sim):
        self.get_git_key()
        notify_user_status = False
        try:
            user = self.dynamo.dynamo_db('user_info', search_name, None, None)
            user_id = user['Items'][0]['person_id']

            if search_name != self.user_search_name:
                if user['Items'][0]['reminders_enabled'] == "on":
                    notify_user_status = True
        except Exception:
            pass

        issue = self.git_api.get_repo(repo).get_issue(int(issue_number))
        issue_json = issue.raw_data
        hyperlink_format = f'<a href="{issue.html_url}">{issue.title}</a>'

        if 'pull_request' not in issue_json:
            if assign_status == "assign":
                issue.add_to_assignees(search_name)
                message = f"{hyperlink_format} successfully assigned to " + name_sim
                if notify_user_status:
                    direct_message = (
                        f"Hello {name_sim}, the following issue was just assigned to you: {hyperlink_format}," +
                        " please take a minute to review it when possible!\n" +
                        "\n -To disable notifications, type: **disable reminders**"
                    )
                    return [direct_message, 'notify user', user_id, message]
                if self.check_assigned_status(search_name, 'issue', repo, issue_number) is False:
                    return f"Could not assign issue to user {search_name}, Error: invalid user"
                return message
            issue.remove_from_assignees(search_name)
            return f"{hyperlink_format} successfully unassigned from " + name_sim

        issue = issue.as_pull_request()
        if assign_status == "assign":
            message = f"{hyperlink_format} successfully assigned to " + name_sim
            issue.create_review_request(reviewers=[search_name])
            if notify_user_status:
                direct_message = (
                    f"Hello {name_sim}, the following pull request was just assigned to you: {hyperlink_format}," +
                    " please take a minute to review it when possible!\n" +
                    "\n -To disable notifications, type: **disable reminders**"
                )
                return [direct_message, 'notify user', user_id, message]
            if self.check_assigned_status(search_name, 'Pr', repo, issue_number) is False:
                return f"Could not assign issue to user {search_name}, Error: invalid user"
            return message

        #  issue.delete_review_request(reviewers=[search_name])
        #  return f"Pull request: {hyperlink_format} successfully unassigned from " + name_sim
        #  Commented out because cidr-automation github account needs admin permissions to unassign pull requests
        return f"Could not unassign pull request, Error: Currently disabled feature"
