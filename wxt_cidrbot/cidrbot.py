from github import Github
from webexteamssdk import WebexTeamsAPI
import logging
import json
import os
import sys
import base64

# fill in imports that are necessary for webex api


class cidrbot:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
        self.logging = logging.getLogger()

        # Obtain room id via env var
        if "ROOM_ID" in os.environ:
            room_id = os.getenv("ROOM_ID")
        else:
            logging.error("Environment variable ROOM_ID must be set")
            sys.exit(1)

        if "GITHUB_ACCESS_TOKEN" in os.environ:
            git_token = os.getenv("GITHUB_ACCESS_TOKEN")
        else:
            logging.error(
                "Environment variable GITHUB_ACCESS_TOKEN must be set")
            sys.exit(1)

        # using an access token
        self.git_init = Github(git_token)

        # Initialize Api
        self.Api = WebexTeamsAPI()

        # Format room_id, this starts as an env var. The env var is the room id you can obtain from the drop down in webex under group settings
        room_uri = "ciscospark://us/ROOM/{}".format(room_id)
        room_uri = room_uri.encode()
        encoded_roomid = base64.b64encode(room_uri)
        encoded_roomid = encoded_roomid.decode("utf-8")

    def compile_notif(self, repo, open_type, identifier):
        if identifier == "issue":
            for issue in open_type:  # Iterate through the given issues
                open_name = issue.title
                issue_num = issue.number
                url = issue.html_url
                git_reviewer= issue.user.login
                try:
                    git_assigned_user = issue.assignee.login
                except:
                    pass
                    print("no assignee assigned")

                self.send_message(git_reviewer, identifier, url, open_name)

        elif identifier == "pr":
            for PullRequest in open_type:  # Iterate through the given issues
                open_name = PullRequest.title
                issue_num = PullRequest.number
                url = PullRequest.html_url
                git_reviewer= PullRequest.user.login
                #try:
                git_assigned_user = PullRequest.assignee.login
                #except:
                #    pass

                # figure this out tomorrow, I can't figure out who is the reviewer here
                # the try except is there bc it will error if it isn't assigned, make something more permenant for this eventually
                # figure out the deal with "reviewers" versus "assignees"

                self.send_message(git_reviewer, identifier, url, open_name)

    def send_message(self, reviewer, identifier, url, open_name):
        git_email = "{}@cisco.com".format(reviewer)
        for i in self.Api.people.list(git_email):
            i = i.to_dict()
            user_name = i["firstName"]
            user_email = i["emails"]
            user_id = i["id"]

        if identifier == "issue":
            message = f"Hey <@personId:{user_id}|{user_name}>, you currently have an open issue which needs reviewing \n\n {open_name}: {url}"
            print(message)
            # sender = Api.messages.create(encoded_roomid, markdown=message) # Send message to room

        elif identifier == "pr":
            message = f"Hey <@personId:{user_id}|{user_name}>, you currently have an open pull request which needs reviewing \n\n {open_name}: {url}"
            print(message)
            # sender = Api.messages.create(encoded_roomid, markdown=message) # Send message to room

    def scan_repos(self):
        envvar_for_repos = {"ciscops/cidrbot"} # Decide what to do with the env var for storing multiple repos
        for repository in envvar_for_repos:
            repo = self.git_init.get_repo(repository)
            open_issues = repo.get_issues(state='open')
            open_prs = repo.get_pulls(state='open')
            if repo.open_issues > 0:
                self.compile_notif(repo, open_issues, "issue")
            if len(list(open_prs)) > 0:
                self.compile_notif(repo, open_prs, "pr")

    def run_script(self):
        self.scan_repos()
