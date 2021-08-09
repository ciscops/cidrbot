import logging
import os
from webexteamssdk import WebexTeamsAPI
from wxt_cidrbot import git_api_handler


class cmdlist:
    def __init__(self):
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
        self.logging = logging.getLogger()

        self.Api = WebexTeamsAPI()
        self.git_handle = git_api_handler.githandler()

    def message_handler(self, request):
        # do a bunch of elif's here to handle all
        # messages and return based on each one
        # add another function for comparing
        # add another function for resending y/n

        if "CIDRBot" in request:
            text = request.replace('CIDRBot', '')
        else:
            text = request

        if text == " ":
            return f"Type **@CIDRbot help** for a list of commands\n"
        if text == " help":
            return "Here is a basic help menu"
        if text == " list issues":
            return self.git_handle.issues_list("List")
        if text == " commands":
            return self.help_menu()
        if text == " reply test":
            return "reply test"
        if "assign" in text:
            return(self.assign_issue(text))
        return "Sorry I don't understand your message"

    def assign_issue(self, text):
        text = text.replace("assign ", '')

        try:
            repo_name = text.split(' ', 2)[1]
            issue = text.split(' ', 3)[2]
            assignee = text.split(' ', 4)[3]
        except IndexError:
            assignee = None
            #return 'Please use format: "assign (repo) (issue number) (user)"'

        if assignee is None:
            return self.git_handle.git_assign(repo_name, issue, "message sender")
        return self.git_handle.git_assign(repo_name, issue, assignee)
        #return 'Please use format: "assign (repo) (issue number) (user)"'

        # Pardon my dust, this next function looks like a demolition site (it works)
    def conversation_handler(self, text):
        if "CIDRBot" in text:
            text = text.replace('CIDRBot', '')

        if "assign" in text:
            return(self.assign_issue(text))
        return self.message_handler(text)


    def new_user(self, json_string):
        user_name = json_string['data']['personDisplayName']
        user_id = json_string['data']['personId']
        name_format = f'<@personId:{user_id}|{user_name}>'
        return f"Welcome to Cidrbot testing room {name_format}, type **@CIDRbot help** for a list of commands\n"

    def help_menu(self):
        help_list = "My current commands are: help, list issues, commands"
        return help_list
