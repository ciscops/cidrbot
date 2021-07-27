import logging
import os
import sys
import base64
from github import Github
from webexteamssdk import WebexTeamsAPI

# fill in imports that are necessary for webex api


class cidrbot:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
        self.logging = logging.getLogger()

        # Webex room id
        if "ROOM_ID" in os.environ:
            room_id = os.getenv("ROOM_ID")
        else:
            logging.error("Environment variable ROOM_ID must be set")
            sys.exit(1)

        # List of git repos to pull from
        if "GIT_REPO_LIST" in os.environ:
            self.repos = os.getenv("GIT_REPO_LIST")
        else:
            logging.error("Environment variable GIT_REPO_LIST must be set")
            sys.exit(1)

        if "GITHUB_ACCESS_TOKEN" in os.environ:
            git_token = os.getenv("GITHUB_ACCESS_TOKEN")
        else:
            logging.error("Environment variable GITHUB_ACCESS_TOKEN must be set")
            sys.exit(1)

        self.message = ""
        self.direct_message_unassigned_list = ""
        self.direct_message_assigned_list = ""

        # using an access token
        self.git_init = Github(git_token)

        # Initialize Api
        self.Api = WebexTeamsAPI()

        # Format room_id, this starts as an env var. The env var is the room id you can obtain from the drop down in webex under group settings
        room_uri = "ciscospark://us/ROOM/{}".format(room_id)
        room_uri = room_uri.encode()
        encoded_roomid = base64.b64encode(room_uri)
        self.encoded_roomid = encoded_roomid.decode("utf-8")

    def compile_notif(self, repo, open_issues):
        for issue in open_issues:
            issue_name = issue.title
            url = issue.html_url
            issue_type = ""
            if issue.pull_request is None:
                issue_type = "Issue"
                self.find_reviewer(repo, issue_type, issue, url, issue_name)
            else:
                issue_type = "Pr"
                self.find_reviewer(repo, issue_type, issue, url, issue_name)

    def find_reviewer(self, repo, issue_type, issue, url, issue_name):
        if issue_type == "Issue":
            if issue.assignee is None:
                self.issue_to_list(repo, url, issue_name, issue_type)
            else:
                git_assigned_user = issue.assignee.login
                if issue.assignee.email is not None:
                    git_assigned_user = issue.assignee.email
                self.create_message(repo, git_assigned_user, url, issue_name, issue_type)

        elif issue_type == "Pr":
            pr = issue.as_pull_request()
            reviewer = "None"
            for i in pr.get_review_requests():
                for reviewers in i:
                    reviewer = reviewers.login
                    reviewer_email = reviewers.email

            if reviewer == "None":
                self.issue_to_list(repo, url, issue_name, issue_type)
            else:
                if reviewer_email is not None:
                    reviewer = reviewer_email
                self.create_message(repo, reviewer, url, issue_name, issue_type)

    def create_message(self, repo, reviewer, url, issue_name, issue_type):
        name_format = f'{reviewer}'

        for i in self.Api.people.list(reviewer):
            i = i.to_dict()
            user_name = i["firstName"]
            user_id = i["id"]
            name_format = f'<@personId:{user_id}|{user_name}>'

        hyperlink_format = f'<a href="{url}">{issue_name}</a>'
        self.direct_message_assigned_list += f"{name_format}: {issue_type} in {repo.full_name}: {hyperlink_format}\n"

    def issue_to_list(self, repo, url, issue_name, issue_type):
        hyperlink_format = f'<a href="{url}">{issue_name}</a>'
        self.direct_message_unassigned_list += f"Unassigned {issue_type} in {repo.full_name}: {hyperlink_format} \n"

    def send_list_message(self):
        list_message = f"**ASSIGNED ISSUES** \n" + self.direct_message_assigned_list + "**UNASSIGNED ISSUES** \n" + self.direct_message_unassigned_list
        self.Api.messages.create(self.encoded_roomid, markdown=list_message)

    def scan_repos(self):
        self.repos = self.repos.split(",")
        for repository in self.repos:
            repo = self.git_init.get_repo(repository)
            print(repo)
            open_issues = repo.get_issues(state='open')
            if repo.open_issues > 0:
                self.compile_notif(repo, open_issues)

        self.send_list_message()


    def msg_request(self, event):
        print(event)
