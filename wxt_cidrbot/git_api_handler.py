import logging
import os
import sys
import base64
import json
import boto3
from github import Github
from botocore.exceptions import ClientError


class githandler:
    def __init__(self):
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "DEBUG"))
        self.logging = logging.getLogger()

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

        # List of git repos to pull from
        if "GIT_REPO_LIST" in os.environ:
            self.repos = os.getenv("GIT_REPO_LIST")
        else:
            logging.error("Environment variable GIT_REPO_LIST must be set")
            sys.exit(1)

        self.repos = self.repos.split(",")
        self.git_api = ""

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
            else:
                decoded_binary_secret = base64.b64decode(get_secret_value_response['SecretBinary'])
                json_string = json.loads(decoded_binary_secret)
                token = json_string['cidrbot_access_token']
                self.git_api = Github(token)

    def get_issue_info(self, issue, issue_type):
        self.logging.debug("get issue info is called")
        if issue_type == "Pr":
            issue = issue.raw_data
            if issue['requested_reviewers'][0]['login'] is not None:
                reviewer = issue['requested_reviewers'][0]['login']
            else:
                reviewer = None
            return {'issue_type': issue_type, 'user': reviewer}

        issue = issue.raw_data
        if issue['assignee'] is not None:
            assigned = issue['assignees'][0]['login']
        else:
            assigned = None
        return {'issue_type': issue_type, 'user': assigned}

    def get_assigned_status(self, assigned_user, issue_type, request):
        text = ""
        self.logging.debug(issue_type)
        if assigned_user is not None:
            text += f" | **Assigned**: " + str(assigned_user) + "\n"
            assigned_status = "True" + ", " + str(assigned_user)
        else:
            text += "\n"
            assigned_status = "False, None"

        if request == "List":
            return text
        return assigned_status

    def process_issue(self, issue, request, issue_type, issue_num, repository):
        message = ""

        hyperlink_format = f'<a href="{issue.html_url}">{issue.title}</a>'
        text = f"{issue_num}) {issue_type} in {repository}: {hyperlink_format}"
        issue_info = self.get_issue_info(issue, issue_type)
        issue_type = issue_info.get('issue_type')
        assigned_user = issue_info.get('user')
        status = self.get_assigned_status(assigned_user, issue_type, request)
        message += text + status

        return message

    def update_dict(self, issue_dict, issue, repo_full_name, issue_name, issue_url, issue_type, request):
        issue_info = self.get_issue_info(issue, issue_type)
        assigned_user = issue_info.get('user')
        status = self.get_assigned_status(assigned_user, issue_type, request)
        status = status.split(", ")
        self.logging.debug(status)
        assigned_status = status[0]
        assigned = status[1]

        issue_dict.update({
            repo_full_name: {
                'name': issue_name,
                'assigned_status': assigned_status,
                'assigned': assigned,
                'url': issue_url,
                'type': issue_type
            }
        })

        return issue_dict

    def scan_repos(self, request):
        self.get_git_key()
        all_issues_text = ""
        issue_dict = {}
        for repository in self.repos:
            repo_url = "https://github.com/" + repository
            all_issues_text += "\n Repo: " + f'<a href="{repo_url}">{repository}</a>\n'
            issue_num = 1

            for pr in self.git_api.get_repo(repository).get_pulls(state='open'):
                if request == "List":
                    all_issues_text += self.process_issue(pr, request, 'Pr', issue_num, repository)
                    issue_num += 1
                else:
                    repo_full_name = repository + ", " + str(issue_num)
                    issue_dict = self.update_dict(issue_dict, pr, repo_full_name, pr.title, pr.html_url, 'Pr', request)
                    issue_num += 1

            for issue in self.git_api.get_repo(repository).get_issues(state='open'):
                if request == "List":
                    issue_json = issue.raw_data
                    if 'pull_request' not in issue_json:
                        self.logging.debug("checking issues")
                        all_issues_text += self.process_issue(issue, request, 'Issue', issue_num, repository)
                        issue_num += 1
                else:
                    issue_json = issue.raw_data
                    if 'pull_request' not in issue_json:
                        repo_full_name = repository + ", " + str(issue_num)
                        issue_dict = self.update_dict(
                            issue_dict, issue, repo_full_name, issue.title, issue.html_url, 'Issue', request
                        )
                        issue_num += 1

        if request == "List":
            all_issues_text += f"\n \n  -Type **@Cidrbot help** for assigning options"
            return all_issues_text
        return issue_dict

    def git_assign(self, repo, user, url, issue_title, assign_status):
        open_issues = self.git_api.get_repo(repo).get_issues(state='open')
        for issue in open_issues:
            if issue.title == issue_title:
                issue_json = issue.raw_data
                self.logging.debug(issue_json)
                self.logging.debug("json info above")
                if 'pull_request' not in issue_json:
                    if issue.html_url == url:
                        if assign_status == "assign":
                            issue.add_to_assignees(user)
                            return "Issue assigned to " + user
                        issue.remove_from_assignees(user)
                        return "Issue unassigned from " + user

                else:
                    issue = issue.as_pull_request()
                    if issue.html_url == url:
                        if assign_status == "assign":
                            issue.create_review_request(reviewers=[user])
                            return "Pull request assigned to " + user
                        #else:
                        #   issue.delete_review_request(reviewers=[user])
                        #  return "Pull request unassigned from " + user

                        # Commented out because cidr-automationg needs admin permissions to unassign pull requests

        return "Could not assign issue"

        # The comments below are only when dynamodb is set up
        #notify user when they have been assigned. Only if user is in the cidrbot room however
        #and if the script can find the user

    def git_repos(self):
        return self.repos

    def issues_list(self, request):
        return self.scan_repos(request)
