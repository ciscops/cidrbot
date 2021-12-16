import logging
import os
import sys
import re
import secrets
import string
from datetime import datetime
from webexteamssdk import WebexTeamsAPI
import requests
from github import Github
from wxt_cidrbot import dynamo_api_handler
from wxt_cidrbot import webex_edit_message


class githandler:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
        self.logging = logging.getLogger()

        if "REGION_NAME" in os.environ:
            self.region_name = os.getenv("REGION_NAME")
        else:
            logging.error("Environment variable REGION_NAME must be set")
            sys.exit(1)

        if 'WEBEX_TEAMS_ACCESS_TOKEN' in os.environ:
            self.wxt_access_token = os.getenv("WEBEX_TEAMS_ACCESS_TOKEN")
        else:
            logging.error("Environment variable WEBEX_TEAMS_ACCESS_TOKEN must be set")
            sys.exit(1)

        # Init sibling py files and used global vars
        self.Api = WebexTeamsAPI()
        self.dynamo = dynamo_api_handler.dynamoapi()
        self.webex = webex_edit_message.webex_message()
        self.user_search_name = ""
        self.room_id = ""
        self.msg_edit_id = ""
        self.git_api = ""
        self.token = ""
        self.repos = []
        self.headers = {}
        self.session = ""

    # Determine the reviewer, requested reviewer, or the assignee (if its an issue). The reviewer is currently a disabled feature
    def get_issue_info(self, issue, issue_type):
        if issue_type == "Pr":
            reviewer = ""
            if len(issue['requested_reviewers']) > 0:
                if issue['requested_reviewers'][0]['login'] is not None:
                    for i in issue['requested_reviewers']:
                        reviewer += i['login'] + ', '

            if 'review_comments_url' in issue:
                review_url = issue['url'] + "/reviews"
                self.logging.debug(issue)
                review = self.session.get(review_url, headers=self.headers)
                self.logging.debug(review.json())
                review_json = review.json()

                for user_review in review_json:
                    if len(review_json) > 0:
                        if user_review['state'] == 'CHANGES_REQUESTED' or user_review['state'] == "COMMENTED":
                            reviewer += user_review['user']['login'] + ', '
                            self.logging.debug(user_review['user']['login'])
                            break

            if len(reviewer) < 1:
                reviewer = None
            else:
                reviewer = reviewer[:-2]

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
    def scan_repos(self, request, assign_type, repo_names, edit_status):
        self.session = requests.Session()

        full_text = f"**{assign_type} Issues:**\n"

        message = f"Retrieving a list of {assign_type} issues, one moment..."
        msg_edit_num = 1
        issue_dict = {}

        for repository in repo_names:
            repo_token = self.dynamo.get_repo_keys(self.room_id, repository)
            self.headers = {'Authorization': 'token ' + repo_token}
            if edit_status and msg_edit_num < 10:
                message_repo = repository.upper()
                message += f"\n - Finding issues in repo: {message_repo}..."
                self.webex.edit_message(self.msg_edit_id, message, self.room_id)
                msg_edit_num += 1

            repo_url = "https://github.com/" + repository
            repo_text = "\n Repo: " + f'<a href="{repo_url}">{repository}</a>\n'
            all_issues_text = ""
            issue_num = 0

            all_issues = self.session.get(
                'https://api.github.com/repos/' + repository + '/issues?state=open', headers=self.headers
            )
            all_prs = self.session.get(
                'https://api.github.com/repos/' + repository + '/pulls?state=open', headers=self.headers
            )

            if all_prs.status_code != 200 or all_issues.status_code != 200:
                break

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

    def check_github_user(self, name):
        self.session = requests.Session()

        user = self.session.get('https://api.github.com/users/' + name)

        json_str = user.json()

        if "login" in json_str:
            if json_str['login'] == name:
                return True
        return False

    def check_github_repo(self, repo_name):
        if re.match(r'^[a-zA-Z-0-9._]+/[a-zA-Z-0-9._]+$', repo_name):
            repo_token = self.dynamo.get_repo_keys(self.room_id, repo_name)

            self.session = requests.Session()
            self.headers = {'Authorization': 'token ' + repo_token}

            repo = self.session.get('https://api.github.com/repos/' + repo_name, headers=self.headers)

            json_str = repo.json()

            if "full_name" in json_str:
                if json_str['full_name'] == repo_name:
                    return True
            return False
        return False

    def send_auth_link(self, person_id, room_id, pt_id):
        link = "https://github.com/apps/cidrbot/installations/new?state="
        state_value = {"personId": person_id, "roomId": room_id, "ptId": pt_id}

        alphabet = string.ascii_letters + string.digits
        state = ''.join(secrets.choice(alphabet) for i in range(26))

        message = f'<a href="{link + state}">Click here</a>'
        room = self.Api.rooms.get(room_id)
        room_name = room.title

        message += f" to authenticate a repo to Room: {room_name}. \n -Remember that this grants all members in the room access to your repo via bot commands"

        self.dynamo.add_auth_request(state, state_value)
        self.Api.messages.create(toPersonId=person_id, markdown=message)

    def issue_details(self, text):

        try:
            issue_number = text[2]
            repo = text[1]
        except Exception:
            return f"Use Syntax: **@cidrbot (repo) (issue#) info**"

        token = self.dynamo.get_repo_keys(self.room_id, repo)

        self.git_api = Github(token)
        self.session = requests.Session()
        self.headers = {'Authorization': 'token ' + token}

        if re.match(r'^[a-zA-Z-0-9._]+/[a-zA-Z-0-9._]+$', repo):
            if re.match(r'^[0-9]+$', issue_number):

                try:
                    issue = self.git_api.get_repo(repo).get_issue(int(issue_number))
                except Exception:
                    return f"Could not locate issue, Error: **invalid repo/issue combination**"

                issue_json = issue.raw_data
                if 'pull_request' not in issue_json:
                    issue_type = 'issue'
                    assignee_text = "Assignee:"
                    issue_json = issue.raw_data
                    commits = "0"
                    hyperlink_commits = f'<a href="{issue.html_url}">{"Commits:"}</a>'
                else:
                    issue_type = 'Pr'
                    assignee_text = "Reviewer:"
                    issue = issue.as_pull_request()
                    issue_json = issue.raw_data
                    self.logging.debug(issue_json)
                    commits = issue_json['commits']
                    url_commit = f"https://github.com/{repo}/pull/{issue_number}/commits"
                    hyperlink_commits = f'<a href="{url_commit}">{"Commits:"}</a>'

                assignee = self.get_issue_info(issue_json, issue_type)
                assigned_user = assignee.get('user')

                if assigned_user is not None:
                    user_url = f"https://github.com/{assigned_user}"
                    assigned_user = f'<a href="{user_url}">{assigned_user}</a>'

                updated_time = issue_json['updated_at']
                created_time = issue_json['created_at']
                date = datetime.strptime(updated_time, "%Y-%m-%dT%H:%M:%SZ")
                date_created = datetime.strptime(created_time, "%Y-%m-%dT%H:%M:%SZ")

                timespan = datetime.today() - date
                timespan_created = datetime.today() - date_created
                timespan = str(timespan).split(", ")[0]
                timespan_created = str(timespan_created).split(", ")[0]
                last_seen = f"Last seen: {timespan}"
                created = f"Created: {timespan_created} ago"

                hyperlink_format = f'<a href="{issue.html_url}">{issue.title}</a>'
                name_hyperlink = f'<a href="{issue.user.html_url}">{issue.user.login}</a>'

                Repo_url = f'<a href="{"https://github.com/" + repo}">{repo}</a>'
                Comments = f'<a href="{issue.html_url}">{"Comments:"}</a>'

                spacer = f"**|**"

                line1 = f"Owner: {name_hyperlink}   {spacer}  {Repo_url}"
                line2 = f"{assignee_text} {assigned_user}   {spacer}   {Comments} {issue.comments}   {spacer}   {hyperlink_commits} {commits}"
                line3 = f"{created}   {spacer}   {last_seen}   {spacer}   State: {issue.state} "

                return (
                    f"{issue_type} #{issue.number}: {hyperlink_format} \n" + f"- {line1}  \n" + f"- {line2}  \n" +
                    f"- {line3}  \n"
                )

            return f"Issue number invalid"
        return f"Repo name invalid"

    # Ensure an issue/pr was assigned. If the username was invalid, this function returns false and the webex user is notified of an invalid username error
    def check_assigned_status(self, search_name, issue_type, repo, issue_number):
        issue = self.git_api.get_repo(repo).get_issue(int(issue_number))
        if issue_type == "issue":
            issue_json = issue.raw_data
        else:
            issue = issue.as_pull_request()
            issue_json = issue.raw_data

        assignee = self.get_issue_info(issue_json, issue_type)
        if assignee.get('user') is not None:
            if search_name in assignee.get('user'):
                return True
        return False

    # Assign the issue to the user, additionally, if their notifications are enabled, send them a message
    def git_assign(self, repo, issue_number, search_name, assign_status, name_sim):
        token = self.dynamo.get_repo_keys(self.room_id, repo)

        self.git_api = Github(token)
        self.session = requests.Session()
        self.headers = {'Authorization': 'token ' + token}

        if self.check_github_user(search_name) is False:
            return f"Invalid username: {search_name}"

        notify_user_status = False
        try:
            user = self.dynamo.get_user_info(search_name, self.room_id)
            user_id = user['person_id']

            if search_name != self.user_search_name:
                if user['reminders_enabled'] == "on":
                    notify_user_status = True
        except Exception:
            pass

        try:
            issue = self.git_api.get_repo(repo).get_issue(int(issue_number))
        except Exception:
            return f"Could not assign issue to user {search_name}, Error: **invalid repo/issue combination**"

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
                    return f"Could not assign issue to user {search_name}, Error: **invalid user**"
                return message
            issue.remove_from_assignees(search_name)
            return f"{hyperlink_format} successfully unassigned from " + name_sim

        issue = issue.as_pull_request()
        if assign_status == "assign":
            message = f"{hyperlink_format} successfully assigned to " + name_sim

            try:
                issue.create_review_request(reviewers=[search_name])
            except Exception as e:
                if e.data['message'] == 'Review cannot be requested from pull request author.':
                    return "You created this pull request, why exactly are you trying to assign it to yourself?"
                return f"An error has occured: {e.data['message']}"

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

        issue.delete_review_request(reviewers=[search_name])
        return f"Pull request: {hyperlink_format} successfully unassigned from " + name_sim
