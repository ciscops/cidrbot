import logging
import os
import sys
from github import Github


class githandler:
    def __init__(self):
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
        self.logging = logging.getLogger()

        # Connect to git
        self.git_api = Github()

        # List of git repos to pull from
        if "GIT_REPO_LIST" in os.environ:
            self.repos = os.getenv("GIT_REPO_LIST")
        else:
            logging.error("Environment variable GIT_REPO_LIST must be set")
            sys.exit(1)

        self.repos = self.repos.split(",")

    def scan_repos(self, request):
        issues = ""
        issue_dict = {}
        for repository in self.repos:
            repo = self.git_api.get_repo(repository)
            repo_url = "https://github.com/" + repo.full_name
            issues += "\n Repo: " + f'<a href="{repo_url}">{repo.full_name}</a>\n'
            print(repo)
            self.logging.debug(repo)
            open_issues = repo.get_issues(state='open')
            if repo.open_issues > 0:
                i = 1
                for issue in open_issues:
                    assigned = None
                    reviewer = None
                    if issue.pull_request is None:
                        issue_type = "Issue"
                        try:
                            assigned = issue.assignee.login
                        except Exception:
                            pass
                    else:
                        issue_type = "Pull Request"
                        issue = issue.as_pull_request()
                        try:
                            self.check_reviewer(issue.get_review_requests())
                        except Exception:
                            pass

                    issue_name = issue.title
                    url = issue.html_url
                    hyperlink_format = f'<a href="{url}">{issue_name}</a>'

                    text = f"{i}) {issue_type} in {repo.full_name}: {hyperlink_format}"

                    assigned_status = "False, none"

                    if assigned is not None:
                        text += f" | **Assigned**: " + str(assigned) + "\n"
                        assigned_status = "True" + ", " + str(assigned)
                    elif reviewer is not None:
                        text += f" | **Assigned**: " + str(reviewer) + "\n"
                        assigned_status = "True" + ", " + str(reviewer)
                    else:
                        text += "\n"

                    issues += text
                    repo_issue_num = repo.full_name + ", " + str(i)
                    issue_assigned_status = issue_name + ", " + assigned_status + ", " + str(url) + ", " + issue_type
                    issue_dict.update({repo_issue_num: issue_assigned_status})
                    i += 1
        issues += f"\n \n  -Type **@Cidrbot help** for assigning options"
        self.logging.debug(issue_dict)
        if request == "List":
            return issues
        return issue_dict

    def check_reviewer(self, review_requests):
        for x in review_requests():
            for y in x:
                reviewer = y.login
        return reviewer

    # This function will eventually communicate with github, the hard coded values are for testing
    def git_assign(self, repo, issue, user):
        if repo == "ciscops/cidrbot":
            if issue == "2":
                return "Issue: " + issue + " in repo " + repo + " assigned successfully to: " + user
            return "Issue cannot be located, ensure you typed the correct issue number"
        return "Repo cannot be located, ensure you typed the correct repo name"

    def git_repos(self):
        return self.repos

    def issues_list(self, request):
        return self.scan_repos(request)
