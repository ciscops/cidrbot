import logging
import os
import sys
from github import Github


class githandler:
    def __init__(self, git_token=None):
        logging.basicConfig(level=os.environ.get("LOGLEVEL", "INFO"))
        self.logging = logging.getLogger()

        # Connect to git, right now using no tokens
        self.git_init = Github()

        # List of git repos to pull from
        if "GIT_REPO_LIST" in os.environ:
            self.repos = os.getenv("GIT_REPO_LIST")
        else:
            logging.error("Environment variable GIT_REPO_LIST must be set")
            sys.exit(1)

    def scan_repos(self):
        self.repos = self.repos.split(",")
        issues = ""
        for repository in self.repos:
            repo = self.git_init.get_repo(repository)
            print(repo)
            self.logging.debug(repo)
            open_issues = repo.get_issues(state='open')
            if repo.open_issues > 0:
                #i = 1
                for issue in open_issues:
                    issue_name = issue.title
                    url = issue.html_url
                    hyperlink_format = f'<a href="{url}">{issue_name}</a>'
                    text = f"Issue in {repo.full_name}: {hyperlink_format}\n"
                    issues += text
                    print(issue.title)
                    print(issue.html_url)
                    #i += 1
        message = f"**Issues:**\n" + issues
        return message
