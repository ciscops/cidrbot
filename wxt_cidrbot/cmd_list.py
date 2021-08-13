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

        self.user_email = ""

    def message_handler(self, request):
        if "cidrbot" in request:
            text = request.replace('cidrbot', '')
        else:
            text = ' ' + request

        if text == '':
            return f"Type **@CIDRbot help** for a list of commands\n"
        if text == " help":
            return self.help_menu()
        if "list issues" in text:
            return self.issues(text)
        if text == " list repos":
            return self.repo_list()
        if "assign" in text:
            return (self.assign_issue(text))
        return "Sorry I don't understand your message"

    def assign_issue(self, text):
        text = text.replace("assign", '')

        try:
            repo_name = text.split(' ', 2)[1]
            issue = text.split(' ', 3)[2]
            assignee = text.split(' ', 4)[3]
        except IndexError:
            assignee = None

        if assignee is None:
            return self.git_handle.git_assign(repo_name, issue, "message sender")
        return self.git_handle.git_assign(repo_name, issue, assignee)
        #return 'Please use format: "assign (repo) (issue number) (user)"'

        # Pardon my dust, this next function looks like a demolition site (it works)
    def conversation_handler(self, text):
        if "cidrbot" in text:
            text = text.replace('cidrbot ', '')

        if "assign" in text:
            return (self.assign_issue(text))
        return self.message_handler(text)

    def new_user(self, json_string):
        user_name = json_string['data']['personDisplayName']
        user_id = json_string['data']['personId']
        name_format = f'<@personId:{user_id}|{user_name}>'
        return f"Welcome to Cidrbot testing room {name_format}, type **@CIDRbot help** for a list of commands\n"

    def user_email_payload(self, email):
        self.user_email = email.split("@cisco.com")

    def issues(self, text):
        text = text.replace('list issues', '')

        if text == ' ':
            return f"**All Issues:**\n" + self.git_handle.issues_list("List")
        if text == "  me":
            target_user = self.user_email[0]
        else:
            target_user = text.replace(' ', '')

        issue_dict = self.git_handle.issues_list("Dict")
        message = f"**Issues assigned to** **" + str(target_user) + "**\n"
        issues_found = 0
        for issue in issue_dict:
            repo_name = issue.split(', ', 1)[0]
            value = issue_dict.get(issue)
            issue_name = value.split(', ', 1)[0]
            status = value.split(', ', 2)[1]
            if status == "True":
                assignee = value.split(', ', 3)[2]
                if assignee == target_user:
                    url = value.split(', ', 4)[3]
                    issue_type = value.split(', ', 5)[4]
                    hyperlink_format = f'<a href="{url}">{issue_name}</a>'
                    text = f"- {issue_type} in {repo_name}: {hyperlink_format}"

                    message += text + "\n"
                    issues_found += 1

        if issues_found > 0:
            return message
        return "Specified username invalid, or no issues assigned to user"

    def help_menu(self):
        help_list = (
            f"Here is a list of current commands and features\n" +
            "- Display issues: - **@Cidrbot list issues (me, username, blank)**\n" +
            "- Assigning issues: - **@Cidrbot assign repo issue (me, username, blank)** - currently unavaliable\n" +
            "- Display current repo list: -**@Cidrbot list repos**\n" +
            "- To access these commands in direct messages, omit **@cidrbot**\n" +
            "\n-For further documentation and proper message syntax, see #Confluence page link"
        )

        return str(help_list)

    def repo_list(self):
        repos = self.git_handle.git_repos()
        message = "Here are the current repos cidrbot uses:\n"
        for repo in repos:
            repo_url = "https://github.com/" + str(repo)
            hyperlink = f'<a href="{repo_url}">{repo}</a>\n'
            message += "- " + hyperlink + " \n"
        return message
