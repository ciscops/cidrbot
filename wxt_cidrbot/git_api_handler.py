import logging
import os
import sys
from github import Github


class githandler:
    def __init__(self):
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
        self.logging = logging.getLogger()

        # Connect to git, right now using no tokens
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
            print(repo)
            self.logging.debug(repo)
            open_issues = repo.get_issues(state='open')
            if repo.open_issues > 0:
                i = 1
                for issue in open_issues:
                    if issue.pull_request is None:
                        issue_type = "Issue"
                    else:
                        issue_type = "Pull Request"

                    issue_name = issue.title
                    url = issue.html_url
                    hyperlink_format = f'<a href="{url}">{issue_name}</a>'
                    text = f"{i}) {issue_type} in {repo.full_name}: {hyperlink_format}\n"
                    issues += text
                    print(issue.title)
                    print(issue.html_url)
                    issue_dict.update({i: issue_name})
                    i += 1
        if request == "List":
            return f"**All Issues:**\n" + issues
        return issue_dict

    def issues_list(self, request):
        return self.scan_repos(request)

    # This function will eventually communicate with github, the hard coded values are for testing
    def git_assign(self, repo, issue, user):
        if repo == "ciscops/cidrbot":
            if issue == "2":
                return "Issue: " + issue + " in repo " + repo + " assigned successfully to: " + user
            return "Issue cannot be located, ensure you typed the correct issue number"
        return "Repo cannot be located, ensure you typed the correct repo name"
