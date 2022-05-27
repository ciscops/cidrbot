import logging
import os
import json
import re
import sys
from difflib import SequenceMatcher
import requests
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

        if 'WEBEX_TEAMS_ACCESS_TOKEN' in os.environ:
            self.wxt_access_token = os.getenv("WEBEX_TEAMS_ACCESS_TOKEN")
        else:
            logging.error("Environment variable WEBEX_TEAMS_ACCESS_TOKEN must be set")
            sys.exit(1)

        if 'WEBEX_BOT_NAME' in os.environ:
            self.bot_name = os.getenv("WEBEX_BOT_NAME")
        else:
            logging.error("Environment variable WEBEX_BOT_NAME must be set")
            sys.exit(1)

        # Init sibling py files and used global vars
        self.git_handle = git_api_handler.githandler()
        self.dynamo = dynamo_api_handler.dynamoapi()
        self.webex = webex_edit_message.webex_message()
        self.Api = ""
        self.webex_mod_status = ""
        self.msg_id = ""
        self.room_of_msg = ""
        self.user_email = ""
        self.user_person_id = ""
        self.username_email_dict = {}
        self.first_name_dups = {}

    def similar(self, a, b):
        return SequenceMatcher(None, a, b).ratio()

    # Clean the message and detemine what the user typed, then execute the appropriate commands
    def message_handler(self, request, event_type, room_id, pt_id):
        if self.bot_name in request:
            text = request.replace(self.bot_name, "")
            text = text.lstrip()
            text = text.lower()
            text_split = text.split(" ")
            text_split.insert(0, '')
        else:
            text = ' ' + request
            text = text.lower()
            text_split = text.split(' ')

        if event_type == "Direct Message":
            #Change this self.webex thing to be a more accurate name please
            for user in self.webex_mod_status:
                user = user.to_dict()
                #full_name = user['personDisplayName']
            if "enable reminders" in text:
                return self.dynamo.update_user(self.user_email, "on", self.user_person_id, room_id)
            if "disable reminders" in text:
                return self.dynamo.update_user(self.user_email, "off", self.user_person_id, room_id)
            if "help" in text:
                return self.help_menu("all")
            return f"List of avaliable commands in direct messages: \n - enable/disable reminders"

        words_list = [
            'list', 'issues', 'me', 'my', 'all', 'help', 'repos', 'enable', 'disable', 'reminders', 'in', 'assign',
            'unassign', 'info', 'test', 'triage', 'update', 'name'
        ]
        help_words_list = ['assigning', 'issues', 'repos', 'reminders', 'syntax', 'triage']

        repo_names = self.dynamo.get_repositories(room_id)
        repo_names = sorted(repo_names, key=str.lower)
        repo_search = []

        for i in repo_names:
            repo_search.append(i.lower())

        user_dict = self.dynamo.user_dict(room_id)
        #self.logging.debug("User dict: " + str(user_dict))

        name_list = []
        for user in user_dict:
            name_list.append(user)

            if user_dict[user]['dup_status'] is False:
                first_name = str(user_dict[user]['first_name']).lower()
                name_list.append(first_name)
            else:
                first_name_lower = str(user_dict[user]['first_name']).lower()
                name_list.append(first_name_lower + str(user)[1].lower())
                name_list.append(first_name_lower)
                first_name = str(first_name_lower + str(user)[1].lower())
                self.first_name_dups.update({user: {'first_name': first_name_lower}})
                self.username_email_dict.update({
                    first_name_lower: {
                        'login': user,
                        'duplicate': user_dict[user]['dup_status']
                    }
                })

            self.username_email_dict.update({first_name: {'login': user, 'duplicate': user_dict[user]['dup_status']}})

        name_list.append('me')

        repos = self.message_similarity(text_split, repo_search, 0.9)
        words = self.message_similarity(text_split, words_list + help_words_list, 0.9)
        names = self.message_similarity(text_split, name_list, 0.9)

        self.logging.debug(words)

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

                if re.match(r'^[a-zA-Z-0-9._]+$', search_name):
                    if self.similar(sim_text, "list issues " + search_name) > 0.93:
                        if self.git_handle.check_github_user(search_name):
                            return self.send_update_msg(room_id, "user", search_name, None, pt_id)
                return "Please enter a valid name, omit the @email for usernames"

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
            return self.repo_list(room_id)
        if self.similar(sim_text, "list triage users") > 0.8:
            return self.list_triage_message(room_id)
        if 'triage' in words:
            for user in self.webex_mod_status:
                if user.isModerator:
                    triage_text = text_split[1] + " " + text_split[2]
                    if self.similar(triage_text, "triage add") > 0.9:
                        return self.send_update_msg(room_id, "triage add", text_split[3], text_split, pt_id)
                    if self.similar(triage_text, "triage remove") > 0.9:
                        return self.send_update_msg(room_id, "triage remove", text_split[3], text_split, pt_id)
                else:
                    return "Only moderators can access triage commands"
        if 'info' in words:
            return self.send_update_msg(room_id, 'info', None, text_split, pt_id)
        if 'assign' in words:
            return self.send_update_msg(room_id, 'assign', None, text_split, pt_id)
        if 'unassign' in words:
            return self.send_update_msg(room_id, 'unassign', None, text_split, pt_id)
        for help_word in help_words_list:
            if self.similar(sim_text, "help" + help_word) > 0.8:
                return self.help_menu(help_word)
        if self.similar(sim_text, "help") > 0.8:
            return self.help_menu("all")

        if "update name" in text:
            for user in self.webex_mod_status:
                if user.isModerator:
                    return self.send_update_msg(room_id, "update name", text_split[3], text_split, pt_id)
        if "manage repos" in text:
            if event_type == "Message":
                #doesn't need to be webex_mod_status - confusing name, change to "webex user"
                for user in self.webex_mod_status:
                    if user.isModerator:
                        self.git_handle.send_auth_link(self.user_person_id, room_id, pt_id)
                        return "Check direct messages to complete Github authentication"

                    return "That command is only avaliable to space moderators"
            else:
                return "That command is only avaliable for moderators in the chatroom"

        help_text = (
            f"Type **@CIDRbot help** for a list of commands: Add any of the following strings for specific help \n" +
            "- **@CIDRbot help** + (assigning, issues, repos, reminders, syntax, triage) \n"
        )
        return help_text

    # Send a status message to the user to let them know the bot is trying to find all the issues, then continue
    def send_update_msg(self, room_id, cmd_type, name, text_split, pt_id):
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
        elif cmd_type == 'info':
            text = f"Retrieving issue information..."
        elif cmd_type == 'triage add':
            text = f"Searching github for user {name} ..."
        elif cmd_type == 'triage remove':
            text = f"Removing triage user {name} ..."
        elif cmd_type == 'update name':
            text = f"Updating {name}'s github name reference..."
        else:
            display_name = name[0].split("/", 1)[1]
            text = f"Retrieving a list of issues in repo: {display_name}, one moment..."

        URL = f'https://webexapis.com/v1/messages'
        headers = {'Authorization': 'Bearer ' + self.wxt_access_token, 'Content-type': 'application/json;charset=utf-8'}
        post_message = {'roomId': room_id, 'markdown': text, 'parentId': pt_id}
        response = requests.post(URL, json=post_message, headers=headers)
        if response.status_code == 200:
            self.logging.debug("Message created successfully")
            self.logging.debug(str(response.text))
            resp = json.loads(str(response.text))
            msg_edit_id = resp["id"]
        else:
            self.logging.debug(str(response.status_code))
            self.logging.debug(str(response.text))

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
            message = self.issues(name, room_id)
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
        if cmd_type == 'info':
            message = self.git_handle.issue_details(text_split)
            message_info_list.append(message)
            return message_info_list
        if cmd_type == 'triage add':
            message = self.git_handle.triage_user(text_split, room_id)
            message_info_list.append(message)
            return message_info_list
        if cmd_type == 'triage remove':
            message = self.dynamo.remove_triage_user(name, room_id)
            message_info_list.append(message)
            return message_info_list
        if cmd_type == 'update name':
            message = self.dynamo.update_github_username(text_split[3], text_split[4], room_id)
            message_info_list.append(message)
            return message_info_list
        return "Interal error"

    # Prevent cidrbot from choosing the wrong name when invoked with webex user's "first name"
    # Since cidrbot allows for referencing users in the cidrbot-users room by their webex first name, users with duplicate first names may exist
    def dup_user(self, name):
        login_list = ""
        user_list = ""
        name = name[0].upper() + name[1:]

        for i in self.first_name_dups:
            self.logging.debug(name)
            self.logging.debug(self.first_name_dups[i]['first_name'])
            if self.first_name_dups[i]['first_name'] == name.lower():
                login_list += "(" + i + ")"
            else:
                user_list += "(" + i + ")"

        if login_list != "":
            return f"Multiple users exist with the name **" + name + "**; please use one of the following names instead: **" + login_list + "**"
        return f"Try using one of the following names: **" + user_list + "**"

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
        error_message_repo_issues = "The issue or repo you listed cannot be found, ensure you typed the repo, issue number correctly "

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

        if re.match(r'^[a-zA-Z-0-9._]+$', git_name):
            if re.match(r'^[a-zA-Z-0-9._]+/[a-zA-Z-0-9._]+$', repo):
                return self.git_handle.git_assign(repo, issue_number, git_name, assign_status, first_name)
            return error_message_repo_issues
        return error_message_user

    # Send a message to the cidrbot-users announcing the new user, and adding their data to the dynamodb table
    def new_user(self, json_string, webex_msg_sender, user_name, room_id):
        self.Api = WebexTeamsAPI()
        user_id = json_string['data']['personId']

        user_json_details = self.Api.memberships.list(roomId=room_id, personId=user_id)
        for i in user_json_details:
            user_json_details = i.to_dict()
        full_name = user_json_details['personDisplayName']
        name_format = f'<@personId:{user_id}|{user_name}>'

        self.dynamo.create_user(webex_msg_sender, user_id, full_name, room_id)

        return f"Welcome to Cidrbot Users room {name_format}, type *@CIDRbot help* for a list of commands I support\n"

    # Create a list of all users, their first name, their username minus the @ email tag
    # Create a secondary list for duplicate users. These lists are used when the bot processes the name in a message
    def user_email_payload(self, email, person_id, person_webex_mod_status):
        self.webex_mod_status = person_webex_mod_status
        self.user_person_id = person_id
        self.user_email = email.split("@", 1)[0]
        self.git_handle.user_name(self.user_email)

    # Find all the issues assigned to a specified user
    def issues(self, target_user, room_id):
        #assignee_target = target_user
        # name == assignee_target or
        try:
            git_name_target = self.dynamo.user_dict(room_id)[target_user]['git_name']
        except Exception:
            return "Specified username invalid"

        for user in self.username_email_dict:
            if self.username_email_dict[user]['login'] == target_user:
                target_user = user[0].upper() + user[1:]

        edit_message = f"Retrieving issues, one moment... \n "
        self.webex.edit_message(self.msg_id, edit_message + f"- Searching all issues \n", self.room_of_msg)

        issue_dict = self.git_handle.scan_repos("Dict", 'All', self.dynamo.get_repositories(room_id), False)
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
                    if name == git_name_target:
                        edit_message += f"- Issue located: {issue_name} \n"
                        if issues_found < 8:
                            self.webex.edit_message(self.msg_id, edit_message, self.room_of_msg)
                        url = issue_dict[issue]['url']
                        issue_type = issue_dict[issue]['type']
                        issue_num = issue_dict[issue]['number']
                        issue_color_code = issue_dict[issue]['color_code']

                        issue_type += " #" + str(issue_num)
                        name_format = issue_name
                        hyperlink_format = f'<a href="{url}">{name_format}</a>'
                        text = f"{issue_color_code} &nbsp; {issue_type} in {repo_name}: {hyperlink_format}"

                        message += text + "\n"
                        issues_found += 1

        if issues_found > 0:
            return message
        return "no issues assigned to user"

    # When weekly_reminder_email function is called by api_gateway, find the current issues assigned to a user
    def get_user_issues(self, assigned_issues_dict, user):
        issues_found = 0
        message = ""
        for issue in assigned_issues_dict:
            status = assigned_issues_dict[issue]['assigned_status']
            if status:
                assignee = assigned_issues_dict[issue]['assigned']
                assignee_list = assignee.split(', ')
                for assigned_user in assignee_list:
                    if assigned_user == user:
                        repo_name = issue.split(', ', 1)[0]
                        issue_name = assigned_issues_dict[issue]['name']
                        url = assigned_issues_dict[issue]['url']
                        issue_type = assigned_issues_dict[issue]['type']
                        issue_num = assigned_issues_dict[issue]['number']
                        issue_color_code = assigned_issues_dict[issue]['color_code']

                        name_format = issue_name + " #" + str(issue_num)
                        hyperlink_format = f'<a href="{url}">{name_format}</a>'
                        text = f"{issue_color_code} &nbsp; {issue_type} in {repo_name}: {hyperlink_format}"

                        message += text + '\n'
                        issues_found += 1

        if issues_found > 0:
            return message
        return "No issues"

    # A list of helpful messages to aid users in interacting with cidrbot
    def help_menu(self, help_type):
        start_text = f"Here is a list of current commands and features (Note: excluding reminder toggling, no other commands are accessible in direct messages with cidrbot)\n" + "\n"

        #url_name = ''
        #url = ''
        #hyperlink_format = f'<a href="{url}">{url_name}</a>'
        end_text = (
            f"\n-For further documentation and proper message syntax, see README\n" +
            "-To access all of these commands in direct messages, omit **@cidrbot**\n"
        )

        list_issues_help = (
            "-Display issues: **@Cidrbot list (my, all) issues (in) (repo name or Git username, Webex firstname)**\n" +
            "- **@Cidrbot list issues** -lists unassigned issues\n" +
            "- **@Cidrbot list all issues** -lists all issues\n" + "- **@Cidrbot list my issues**\n" +
            "- **@Cidrbot list issues (Github username)**\n" + "- **@Cidrbot list issues (Webex firstname)**\n" +
            "- **@Cidrbot list issues in (repo)**\n" + "- **@Cidrbot list all issues in (repo)**\n" +
            "- **@Cidrbot (repo name) (issue number) info** (@Cidrbot repopath/reponame 20 info) \n" + "\n"
        )
        assign_issues_help = (
            f"-Assign/Unassign issue: **@Cidrbot (assign/unassign) (repo) (issue_num) (me, Git username, Webex firstname)**\n"
            + "- **@Cidrbot assign/unassign (repo) (issue_num) (me)**\n" +
            "- **@Cidrbot assign/unassign (repo) (issue_num) (Git username)**\n" +
            "- **@Cidrbot assign/unassign (repo) (issue_num) (Webex firstname)**\n" + "\n"
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
            "- **@Cidrbot manage repos** - only for moderators in chat room\n" + "\n"
        )

        triage_help = (
            f"-Display current triage list:\n" + "- **@Cidrbot list triage users**\n" +
            "- Add or remove triage users (Username has to be the **exact** github username)\n" +
            "- Only github users who are able to be assigned to an issue/pr can be assigned by cidrbot\n" +
            "- **@Cidrbot triage add username** - only for moderators in chat room\n" +
            "- **@Cidrbot triage remove username** - only for moderators in chat room\n"
        )

        syntax_end_text = (
            f"- Syntax: Github username: **ppajersk**, Webex firstname: **Paul**, Repo: **ciscops/cidrbot**  \n"
        )

        if help_type == "all":
            return start_text + list_issues_help + assign_issues_help + syntax_help + reminders_help + repos_help + triage_help + end_text
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
        if help_type == "triage":
            return triage_help + end_text
        return "No help type found"

    def list_triage_message(self, room_id):
        try:
            triage = self.dynamo.get_triage(room_id)
            message = "Current list of triage users Cidrbot assigns issues to:\n"
            for user in triage:
                message += "- " + user + " \n"
        except Exception:
            message = "No users in triage list. To add users, type: triage add username"

        return message

    # Return a list of all the current repos
    def repo_list(self, room_id):
        repos = self.dynamo.get_repositories(room_id)
        message = "Current list of repositories Cidrbot searches:\n"
        for repo in repos:
            repo_url = "https://github.com/" + str(repo)
            hyperlink = f'<a href="{repo_url}">{repo}</a>\n'
            message += "- " + hyperlink + " \n"
        return message
