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
            logging.error("Environment variable GITHUB_ACCESS_TOKEN must be set")
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

    # End of what needs to go into the init def (use self when the main key functions are working fine)

    def get_repo_issues(self):
        repo = self.git_init.get_repo("ciscops/cidrbot") # Cycle through the different repos, make this work through an env var
        open_issues = repo.get_issues(state='open') # Check if there are any open issues

        self.msg_sender(open_issues, repo)

    # This if block should be a function
    def msg_sender(self, open_issues, repo):
        if repo.open_issues > 0: # Easy way to differetiate between issues and no issues
            for issue in open_issues: # Iterate through the given issues
                issue_name = issue.title
                issue_num = issue.number
                url = issue.html_url
                git_assigned_user = issue.user.login
                git_reviewer = issue.assignee.login
                print(git_reviewer)
                print(git_assigned_user)
                #print(issue.state) # Determine wether or the not the issue is open or closed
                #print(issue.updated_at) # Use this for the time threshold to remind users in combination with aws cloudwatch timer


                git_email = "{}@cisco.com".format(git_reviewer) # Format the git user name into an email to search webex for a user id

                # All the code below should be it's own function

                for i in self.Api.people.list(git_email): # Easiest way to do this, its a generator container so this will always look ugly
                    i = i.to_dict()
                    user_name = i["firstName"]
                    user_email = i["emails"]
                    user_id = i["id"]

                message = f"Hey <@personId:{user_id}|{user_name}>, you currently have an open issue which needs reviewing \n\n {issue_name}: {url}" # Make message
                print(message)
                #sender = Api.messages.create(encoded_roomid, markdown=message) # Send message to room

    def run_script(self):
        self.get_repo_issues()


    #write something about there being a case where the email doesnt exists
    #if so tag a mod or someone in the space to contact the git user listed
