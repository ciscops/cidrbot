import logging
import os
from difflib import SequenceMatcher
from wxt_cidrbot import git_api_handler


class cmdlist:
    def __init__(self):
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
        self.logging = logging.getLogger()

        self.git_handle = git_api_handler.githandler()
        self.user_email = ""
        self.room_email_list = []
        self.username_email_dict = {}

    def similar(self, a, b):
        return SequenceMatcher(None, a, b).ratio()

    def message_handler(self, request):
        if "CIDRBot" in request:
            text = request.replace('CIDRBot', '')
            text = text.lower()
        else:
            text = ' ' + request
            text = text.lower()

        text_split = text.split(" ")
        name_list = self.room_email_list
        words = self.message_similarity(text_split, ['list', 'issues', 'me', 'my', 'all', 'repos', 'help'], 0.8)
        names = self.message_similarity(text_split, name_list, 0.9)
        sim_text = ""

        for i in words:
            sim_text += i + " "

        if len(names) > 0:

            if names[0] in self.username_email_dict:
                if self.username_email_dict[names[0]]['duplicate']:
                    return self.dup_user(names[0])
                search_name = self.username_email_dict[names[0]]['login']
                sim_text += search_name
                self.logging.debug(sim_text)
            else:
                search_name = str(names[0])
                sim_text += search_name
                self.logging.debug(sim_text)

            if self.similar(sim_text, "list issues " + search_name) > 0.85:
                return self.issues(search_name)

        if self.similar(sim_text, "list all issues") or self.similar(sim_text, "list issues") > 0.9:
            return f"**All Issues:**\n" + self.git_handle.issues_list("List")
        if self.similar(sim_text, "list my issues") > 0.8:
            return self.issues(self.user_email)
        if self.similar(sim_text, "list repos") > 0.8:
            return self.repo_list()
        if self.similar(sim_text, "help") > 0.8:
            return self.help_menu()
        if ' assign ' in text:
            return self.assign_issue(text_split, "assign", search_name)
        if ' unassign ' in text:
            return self.assign_issue(text_split, "unassign", search_name)
        return f"Type **@CIDRbot help** for a list of commands\n"

    # Prevent cidrbot from choosing the wrong name when invoked with webex user's "first name"
    def dup_user(self, name):
        login_list = ""
        email_dict = self.username_email_dict
        name = name[0].upper() + name[1:]
        for i in email_dict:
            if email_dict[i]['duplicate']:
                login_list += "(" + email_dict[i]['login'][0].upper() + email_dict[i]['login'][1:] + ")"

        return "Multiple users exist with the name " + name + "; please use one of the following names instead: " + login_list

    def message_similarity(self, text_split, word_list, msg_threshold):
        likely_words = []
        for word in text_split:
            for key_word in word_list:
                if self.similar(word, key_word) > msg_threshold:
                    if key_word not in likely_words:
                        likely_words.append(key_word)
        return likely_words

    def assign_issue(self, text, assign_status, search_name):
        git_dict = self.git_handle.issues_list('Dict')
        name_list = self.room_email_list
        name_list.append("me")

        repos = []
        issues = []

        for i in git_dict:
            repo_name = i.split(',', 1)[0]
            issue_name = i.split(', ', 2)[1]
            if repo_name not in repos:
                repos.append(repo_name)
            if issue_name not in issues:
                issues.append(issue_name)

        try:
            repo_sim = self.message_similarity(text, repos, 0.8)[0]
            issue_sim = self.message_similarity(text, issues, 0.8)[0]
            name_sim = self.message_similarity(text, name_list, 0.8)[0]
        except Exception:
            return "Cannot locate issue, verify issue exists and you are spelling the repo, issue, and username correctly"

        #if name_sim == "me":
        #    name_sim = self.user_email

        for i in git_dict:
            if i == repo_sim + ", " + issue_sim:
                url = git_dict[i]['url']
                #issue_type = git_dict[i]['type']
                issue_title = git_dict[i]['name']
                return self.git_handle.git_assign(repo_sim, search_name, url, issue_title, assign_status, name_sim)
        return "Cannot locate issue, verify issue exists and you are spelling the repo, issue, and username correctly"

    def conversation_handler(self, request, text):
        if "CIDRBot" in text:
            text = text.replace('CIDRBot ', '')
        text = text.lower()
        self.logging.debug("below me")
        self.logging.debug(request)

        #ignore if the parent message was from the bot (think more about this)
        # this function might just be used to reply to users
        return self.message_handler(text)

    def new_user(self, json_string):
        user_name = json_string['data']['personDisplayName']
        user_id = json_string['data']['personId']
        name_format = f'<@personId:{user_id}|{user_name}>'
        return f"Welcome to Cidrbot testing room {name_format}, type **@CIDRbot help** for a list of commands\n"

    def user_email_payload(self, email, email_list):
        self.user_email = email.split("@cisco.com")[0]
        for x in email_list:
            x = x.to_dict()
            if str(x['personEmail']) != "CIDRBot@webex.bot":
                git_wbx_login = x['personEmail'].split("@cisco.com")[0]
                git_wbx_username = x['personDisplayName'].split(" ")[0].lower()
                self.logging.debug(git_wbx_login)
                self.room_email_list.append(git_wbx_login)
                self.room_email_list.append(git_wbx_username)

                if git_wbx_username in self.username_email_dict:
                    dup_status = True
                    login = self.username_email_dict[git_wbx_username]['login']
                    self.username_email_dict.update({git_wbx_username: {'login': login, 'duplicate': True}})
                    git_wbx_username += x['personDisplayName'].split(" ")[1][0].lower()
                else:
                    dup_status = False

                self.username_email_dict.update({git_wbx_username: {'login': git_wbx_login, 'duplicate': dup_status}})

    def issues(self, target_user):
        issue_dict = self.git_handle.issues_list("Dict")
        message = f"**Issues assigned to** **" + str(target_user) + "**\n"
        issues_found = 0
        for issue in issue_dict:
            repo_name = issue.split(', ', 1)[0]
            #value = issue_dict.get(issue)
            issue_name = issue_dict[issue]['name']
            status = issue_dict[issue]['assigned_status']
            if status:
                assignee = issue_dict[issue]['assigned']
                if assignee == target_user:
                    url = issue_dict[issue]['url']
                    issue_type = issue_dict[issue]['type']
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
            "- Display issues: - **@Cidrbot list (my, all) issues (username)**\n" +
            "- Assigning issues: - **@Cidrbot assign repo issue (me, username, blank)** - currently unavaliable\n" +
            "- Display current repo list: -**@Cidrbot list repos**\n" +
            "- To access these commands in direct messages, omit **@cidrbot**\n" +
            "\n-For further documentation and proper message syntax, see #Confluence page link"
        )

        #"Display all issues assigned to you - **@cidrbot list issues me**\n"
        #"- Cidrbot uses webex email to assign issues in git, if your webex/git emails do not match, specify your git name after the issue number\n" +
        return str(help_list)

    def repo_list(self):
        repos = self.git_handle.git_repos()
        message = "Here are the current repos cidrbot uses:\n"
        for repo in repos:
            repo_url = "https://github.com/" + str(repo)
            hyperlink = f'<a href="{repo_url}">{repo}</a>\n'
            message += "- " + hyperlink + " \n"
        return message

        #repo_url = "https://github.com/" + repo.full_name
        #issues += "\n Repo: " + f'<a href="{repo_url}">{repo.full_name}</a>\n'
