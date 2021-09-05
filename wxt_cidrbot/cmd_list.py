import logging
import os
import sys
from difflib import SequenceMatcher
from webexteamssdk import WebexTeamsAPI
from wxt_cidrbot import git_api_handler
from wxt_cidrbot import dynamo_api_handler
from wxt_cidrbot import webex_edit_message


class cmdlist:
    def __init__(self):
        # Initialize logging
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
        self.logging = logging.getLogger()

        # Initialize Bot Id as a global variable
        if "WEBEX_BOT_ID" in os.environ:
            self.webex_bot_id = os.getenv("WEBEX_BOT_ID")
        else:
            logging.error("Environment variable WEBEX_BOT_ID must be set")
            sys.exit(1)

        # Init sibling py files and used global vars
        self.git_handle = git_api_handler.githandler()
        self.dynamo = dynamo_api_handler.dynamoapi()
        self.webex = webex_edit_message.webex_message()
        self.webex_mod_status = ""
        self.msg_id = ""
        self.room_of_msg = ""
        self.user_email = ""
        self.user_person_id = ""
        self.username_email_dict = {}

    def similar(self, a, b):
        return SequenceMatcher(None, a, b).ratio()

    # Clean the message and detemine what the user typed, then execute the appropiate commands
    def message_handler(self, request, event_type, room_id, pt_id):
        if "CIDRBot" in request:
            text = request.replace("CIDRBot", "")
            text = text.lstrip()
            text = text.lower()
            text_split = text.split(" ")
            text_split.insert(0, '')
        else:
            text = ' ' + request
            text = text.lower()
            text_split = text.split(' ')

        words_list = ['list', 'issues', 'me', 'my', 'all', 'help', 'repos', 'enable', 'disable', 'reminders', 'in']
        help_words_list = ['assigning', 'issues', 'repos', 'reminders', 'syntax']

        repo_names = self.dynamo.dynamo_db("repos", None, None, None, None)
        repo_names = sorted(repo_names, key=str.lower)
        repo_search = []

        for i in repo_names:
            repo_search.append(i.lower())

        user_dict = self.dynamo.dynamo_db("all_users", None, None, None, None)

        name_list = []
        for user in user_dict['Items']:
            name_list.append(user['User'])

            if user['dup_status'] is False:
                name_list.append(user['first_name'])
                first_name = user['first_name']
            else:
                name_list.append(user['first_name'] + str(user['User'])[1].lower())
                name_list.append(user['first_name'])
                first_name = user['first_name'] + str(user['User'])[1].lower()
                self.username_email_dict.update({
                    user['first_name']: {
                        'login': user['User'],
                        'duplicate': user['dup_status']
                    }
                })

            self.username_email_dict.update({first_name: {'login': user['User'], 'duplicate': user['dup_status']}})
        name_list.append('me')

        repos = self.message_similarity(text_split, repo_search, 0.9)
        words = self.message_similarity(text_split, words_list + help_words_list, 0.8)
        names = self.message_similarity(text_split, name_list, 0.9)
        sim_text = ""

        for i in words:
            sim_text += i + " "

        search_name = ''
        if len(repos) < 1:
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

                if self.similar(sim_text, "list issues " + search_name) > 0.93:
                    return self.send_update_msg(room_id, "user", search_name, None, pt_id)

            elif "list issues" in text and len(text_split) > 3:
                sim_text += text_split[3]
                search_name = text_split[3]

                if self.similar(sim_text, "list issues " + search_name) > 0.93:
                    return self.send_update_msg(room_id, "user", search_name, None, pt_id)

        else:
            sim_text += repos[0]
            if self.similar(sim_text, "list all issues in" + repos[0]) > 0.95:
                return self.send_update_msg(room_id, "repo all", repos, None, pt_id)
            if self.similar(sim_text, "list issues in" + repos[0]) > 0.95:
                return self.send_update_msg(room_id, "repo unassigned", repos, None, pt_id)

        if " in " in text:
            return f"Could not locate repo, type **@CIDRBot list repos** for a list of currently searchable repos"

        if self.similar(sim_text, "list all issues") > 0.9:
            return self.send_update_msg(room_id, "all", repo_names, None, pt_id)
        if self.similar(sim_text, "list issues") > 0.9:
            return self.send_update_msg(room_id, "issues-unassigned", repo_names, None, pt_id)
        if self.similar(sim_text, "list my issues") > 0.9:
            return self.send_update_msg(room_id, "user", self.user_email, None, pt_id)
        if self.similar(sim_text, "list repos") > 0.8:
            return self.repo_list()
        if 'assign ' in text:
            return self.send_update_msg(room_id, 'assign', None, text_split, pt_id)
        if 'unassign ' in text:
            return self.send_update_msg(room_id, 'unassign', None, text_split, pt_id)
        if event_type == "Direct Message":
            for user in self.webex_mod_status:
                user = user.to_dict()
                full_name = user['personDisplayName']
            if self.similar(sim_text, "enable reminders") > 0.9:
                return self.dynamo.dynamo_db('update_user', self.user_email, "on", self.user_person_id, full_name)
            if self.similar(sim_text, "disable reminders") > 0.9:
                return self.dynamo.dynamo_db('update_user', self.user_email, "off", self.user_person_id, full_name)
        for help_word in help_words_list:
            if self.similar(sim_text, "help" + help_word) > 0.8:
                return self.help_menu(help_word)
        if self.similar(sim_text, "help") > 0.8:
            return self.help_menu("all")
        if "add repo" in text or "remove repo" in text:
            if event_type == "Message":
                for user in self.webex_mod_status:
                    if user.isModerator:
                        request = text_split[1] + " " + text_split[2]
                        name = text_split[3]
                        return self.dynamo.dynamo_db(request, name, None, None, None)
                    return "That command is only available to space moderators"
            else:
                return "That command is only available for moderators in the chatroom"
        help_text = (
            f"Type **@CIDRbot help** for a list of commands: Add any of the following strings for specific help \n" +
            "- **@CIDRbot help** + (assigning, issues, repos, reminders, syntax) \n"
        )
        return help_text

    # Send a status message to the user to let them know the bot is trying to find all the issues, then continue
    def send_update_msg(self, room_id, cmd_type, name, text_split, pt_id):
        Api = WebexTeamsAPI()
        if cmd_type == 'assign':
            text = "Assigning issue, one moment..."
        elif cmd_type == 'unassign':
            text = "Unassigning issue, one moment..."
        elif cmd_type == "all":
            text = "Retrieving a list of all issues, one moment..."
        elif cmd_type == "issues-unassigned":
            text = "Retrieving a list of unassigned issues, one moment..."
        elif cmd_type == "user":
            text = f"Retrieving issues, one moment..."
        else:
            display_name = name[0].split("/", 1)[1]
            text = f"Retrieving a list of issues in repo: {display_name}, one moment..."

        Api.messages.create(room_id, markdown=text, parentId=pt_id)
        msg_edit_id = self.get_message_id(Api, room_id, text, pt_id)
        self.git_handle.room_and_edit_id(room_id, msg_edit_id)
        self.msg_id = msg_edit_id
        self.room_of_msg = room_id
        message_info_list = [msg_edit_id, 'edit message']
        if cmd_type == "all":
            message = self.git_handle.scan_repos("List", 'All', name, True)
            message_info_list.append(message)
            return message_info_list
        if cmd_type == 'issues-unassigned':
            message = self.git_handle.scan_repos("List", 'Unassigned', name, True)
            message_info_list.append(message)
            return message_info_list
        if cmd_type == 'repo all':
            message = self.git_handle.scan_repos("List", 'All', name, True)
            message_info_list.append(message)
            return message_info_list
        if cmd_type == "repo unassigned":
            message = self.git_handle.scan_repos("List", 'Unassigned', name, True)
            message_info_list.append(message)
            return message_info_list
        if cmd_type == 'user':
            message = self.issues(name)
            message_info_list.append(message)
            return message_info_list
        if cmd_type == 'assign':
            message = self.assign_issue(text_split, cmd_type)
            if message[1] == 'notify user':
                message.append(msg_edit_id)
                return message
            message_info_list.append(message)
            return message_info_list
        if cmd_type == 'unassign':
            message = self.assign_issue(text_split, cmd_type)
            if message[1] == 'notify user':
                message.append(msg_edit_id)
                return message
            message_info_list.append(message)
            return message_info_list
        return "Interal error"

    # Find the message id of the last message the bot sent, so it knows what message to update
    def get_message_id(self, Api, room_id, text, pt_id):
        for message in Api.messages.list(room_id, parentId=pt_id):
            if message.personId == self.webex_bot_id:
                if message.text == text:
                    return message.id
        return "No id"

    # Prevent cidrbot from choosing the wrong name when invoked with webex user's "first name"
    # Since cidrbot allows for referencing users in the cidrbot-users room by their webex first name, users with duplicate first names may exist
    def dup_user(self, name):
        login_list = ""
        email_dict = self.username_email_dict
        name = name[0].upper() + name[1:]
        for i in email_dict:
            if email_dict[i]['duplicate']:
                full_user_name = email_dict[i]['login'][0].lower() + email_dict[i]['login'][1:]
                if full_user_name not in login_list:
                    login_list += "(" + full_user_name + ")"

        return f"Multiple users exist with the name **" + name + "**; please use one of the following names instead: **" + login_list + "**"

    def message_similarity(self, text_split, word_list, msg_threshold):
        likely_words = []
        for word in text_split:
            for key_word in word_list:
                if self.similar(word, key_word) > msg_threshold:
                    if key_word not in likely_words:
                        likely_words.append(key_word)
        return likely_words

    # Determine what repo/issue combination the user entered, and call git_api_handler to assign that issue
    # Names need to be percise, 1 letter off will prevent the issue from being assigned
    def assign_issue(self, text, assign_status):
        error_message_user = "User cannot be found, ensure you typed the username correctly "
        error_message_repo_issues = "The issue or repo you listed cannot be found, ensure you typed the repo, issue number, and username correctly "
        try:
            git_name = text[4]
        except Exception:
            return error_message_user

        try:
            issue_number = text[3]
            repo = text[2]
        except Exception:
            return error_message_repo_issues

        if git_name == "me":
            git_name = self.user_email
            first_name = self.user_email
            for user in self.username_email_dict:
                if self.username_email_dict[user]['login'] == git_name:
                    first_name = user[0].upper() + user[1:]
        else:
            first_name = git_name
            for user in self.username_email_dict:
                if user == git_name:
                    first_name = user[0].upper() + user[1:]
                    git_name = self.username_email_dict[user]['login']
                elif self.username_email_dict[user]['login'] == git_name:
                    first_name = user[0].upper() + user[1:]

        #try:
        return self.git_handle.git_assign(repo, issue_number, git_name, assign_status, first_name)
        #except Exception:
        #  return error_message

    # Send a message to the cidrbot-users announcing the new user, and adding their data to the dynamodb table
    def new_user(self, json_string, webex_msg_sender, user_name, room_id):
        user_id = json_string['data']['personId']
        user_json_details = self.Api.memberships.list(roomId=room_id, personId=user_id)
        user_json_details = user_json_details.to_dict()
        full_name = user_json_details['personDisplayName']
        name_format = f'<@personId:{user_id}|{user_name}>'
        self.dynamo.dynamo_db('create_user', webex_msg_sender, "off", user_id, full_name)

        return f"Welcome to Cidrbot Users room {name_format}, type *@CIDRbot help* for a list of commands\n"

    # Create a list of all users, their first name, their username minus the @ email tag
    # Create a secondary list for duplicate users. These lists are used when the bot processes the name in a message
    def user_email_payload(self, email, person_id, person_webex_mod_status):
        self.webex_mod_status = person_webex_mod_status
        self.user_person_id = person_id
        self.user_email = email.split("@cisco.com")[0]
        self.git_handle.user_name(self.user_email)

    # Find all the issues assigned to a specified user
    def issues(self, target_user):
        assignee_target = target_user
        for user in self.username_email_dict:
            if self.username_email_dict[user]['login'] == target_user:
                target_user = user[0].upper() + user[1:]

        edit_message = f"Retrieving issues, one moment... \n - Searching all issues \n"
        self.webex.edit_message(self.msg_id, edit_message, self.room_of_msg)

        issue_dict = self.git_handle.scan_repos(
            "Dict", 'All', self.dynamo.dynamo_db("repos", None, None, None, None), False
        )
        self.logging.debug(issue_dict)

        message = f"**Issues assigned to** **" + str(target_user) + "**\n"
        issues_found = 0
        for issue in issue_dict:
            repo_name = issue.split(', ', 1)[0]
            issue_name = issue_dict[issue]['name']
            status = issue_dict[issue]['assigned_status']
            if status:
                assignee = issue_dict[issue]['assigned'].split(", ")
                for name in assignee:
                    if name == assignee_target:
                        edit_message += f"Issue located: {issue_name} \n"
                        if issues_found < 8:
                            self.webex.edit_message(self.msg_id, edit_message, self.room_of_msg)
                        url = issue_dict[issue]['url']
                        issue_type = issue_dict[issue]['type']
                        issue_num = issue_dict[issue]['number']

                        issue_type += " #" + str(issue_num)
                        name_format = issue_name
                        hyperlink_format = f'<a href="{url}">{name_format}</a>'
                        text = f"- {issue_type} in {repo_name}: {hyperlink_format}"

                        message += text + "\n"
                        issues_found += 1

        if issues_found > 0:
            return message
        return "Specified username invalid, or no issues assigned to user"

    # When weekly_reminder_email function is called by api_gateway, find the current issues assigned to a user
    def get_user_issues(self, assigned_issues_dict, user):
        message = f"**CIDRBOT weekly reminder, please review the listed issues currently assigned to you:**\n"
        issues_found = 0
        for issue in assigned_issues_dict:
            status = assigned_issues_dict[issue]['assigned_status']
            if status:
                assignee = assigned_issues_dict[issue]['assigned']
                if assignee == user:
                    repo_name = issue.split(', ', 1)[0]
                    issue_name = assigned_issues_dict[issue]['name']
                    url = assigned_issues_dict[issue]['url']
                    issue_type = assigned_issues_dict[issue]['type']
                    issue_num = assigned_issues_dict[issue]['number']

                    name_format = issue_name + " #" + str(issue_num)
                    hyperlink_format = f'<a href="{url}">{name_format}</a>'
                    text = f"- {issue_type} in {repo_name}: {hyperlink_format}"

                    message += text + '\n'
                    issues_found += 1

        message += f"\n -To disable these messages, type: **disable reminders**"

        if issues_found > 0:
            return message
        return "No issues"

    # A list of helpful messages to aid users in interacting with cidrbot
    def help_menu(self, help_type):
        start_text = f"Here is a list of current commands and features\n"

        #url_name = ''
        url = ''
        #hyperlink_format = f'<a href="{url}">{url_name}</a>'
        end_text = (
            f"\n-For further documentation and proper message syntax, see {url}\n" +
            "-To access all of these commands in direct messages, omit **@cidrbot**\n"
        )

        list_issues_help = (
            "-Display issues: **@Cidrbot list (my, all) issues (in) (repo name or Git username, Webex firstname)**\n" +
            "- **@Cidrbot list issues** -lists unassigned issues\n" +
            "- **@Cidrbot list all issues** -lists all issues\n" + "- **@Cidrbot list my issues**\n" +
            "- **@Cidrbot list issues (Github username)**\n" + "- **@Cidrbot list issues (Webex firstname)**\n" +
            "- **@Cidrbot list issues in (repo)**\n" + "- **@Cidrbot list all issues in (repo)**\n" + "\n"
        )
        assign_issues_help = (
            f"-Assign/Unassign issue: **@Cidrbot (assign/unassign) (repo) (issue_num) (me, Git username, Webex firstname)**\n"
            + "- **@Cidrbot assign/unassign (repo) (issue_num) (me)**\n" +
            "- **@Cidrbot assign/unassign (repo) (issue_num) (Git username)**\n" +
            "- **@Cidrbot assign/unassign (repo) (issue_num) (Webex firstname)**\n" +
            "- Note: unassigning a pull request is a currently disabled feature\n" + "\n"
        )
        syntax_help = (
            f"-Syntax examples:\n" + "- Github username: **ppajersk**  \n" + "- Webex firstname: **Paul**  \n" +
            "- Repo: **ciscops/cidrbot**  \n" + "\n"
        )
        reminders_help = (
            f"-Enable/Disable weekly issue reminders & issue assigning notification\n" +
            "- **Avaliable only in direct messages with cidrbot  - DM: (Enable/Disable) reminders** \n" + "\n"
        )
        repos_help = (
            f"-Display current repo list:\n" + "- **@Cidrbot list repos**\n" +
            "- **@Cidrbot add repo (repo name)** - only for moderators in chat room\n" +
            "- **@Cidrbot remove repo (repo name)** - only for moderators in chat room\n" + "\n"
        )

        syntax_end_text = (
            f"- Syntax: Github username: **ppajersk**, Webex firstname: **Paul**, Repo: **ciscops/cidrbot**  \n"
        )

        if help_type == "all":
            return start_text + list_issues_help + assign_issues_help + syntax_help + reminders_help + repos_help + end_text
        if help_type == "assigning":
            return assign_issues_help + syntax_end_text + end_text
        if help_type == "issues":
            return list_issues_help + syntax_end_text + end_text
        if help_type == "repos":
            return repos_help + end_text
        if help_type == "reminders":
            return reminders_help + end_text
        if help_type == "syntax":
            return syntax_help + end_text
        return "No help type found"

    # Return a list of all the current repos
    def repo_list(self):
        repos = self.dynamo.dynamo_db("repos", None, None, None, None)
        message = "Current list of repositories Cidrbot searches:\n"
        for repo in repos:
            repo_url = "https://github.com/" + str(repo)
            hyperlink = f'<a href="{repo_url}">{repo}</a>\n'
            message += "- " + hyperlink + " \n"
        return message
