# cidrbot
Lambda based bot that aids in CL pipeline by giving users an interface to interact with Github repos/issues/prs through a Webex chatroom

![cidrbot_visual_final](/assets/cidrbot_visual_final.png)

## Requirements  
  * webexteamssdk ver 1.6+
  * pygithub ver 1.55+
  * boto3 ver 1.17.6+
  * AWS Lambda, Cloudwatch, Apigateway, Secrets, DynamoDB  
  * Webex teams bot
  * Github account    

## Description

Cidrbot is is a Webex Teams bot which relies on AWS infrastructure to provide a medium
between the Webex client and Github. Cidrbot is a room based bot, which means that only
the users within the bot's chat room may interact with the bot (either through the chat room
or through direct messages).

Cidrbot's purpose is to facilitate tracking github issues as well as provide an easy method
to assign issues. @Cidrbot List all issues, will return a list of all the issues in a pool of
repositories, with the issue name, number, associated repo, as well as hyperlinking the name
for easy access. Additionally, cidrbot can display any assigned users for an issue, and any
requested reviewers for a pull request.

@Cidrbot list issues, is a command which returns only unassigned issues. This command
can be paired with a repository name, to list unassigned issues in a single repository.
Example: @Cidrbot list issues in ciscops/cidrbot

Cidrbot allows referencing a user by their first name shown in github, as long as no two
people in the room have the same name, or the user is not in the room. This is to reduce
frustration when trying to remember how to spell "ppajersk" instead of just typing "Paul".

If a user is not in the room, but they are within the Github org of the issue/pull request
which needs to be assigned, their github username can be used. The bot will let you know
if you spelt it incorrectly. Additionally, the same applied for listing issues for a user
who isn't part of the room.

## Commands/Features
    To access cidrbot commands in direct messages, omit @cidrbot

        -Display issues: @Cidrbot list (my, all) issues (in) (repo, Git username, Webex firstname)
            - @Cidrbot list (all) issues
               - Omit "all" to display only the unassigned issues

            - @Cidrbot list my issues  
              -  All issues assigned to the user making the request

            - @Cidrbot list issues (Github username/Webex firstname)
              -  All issues assigned to a specific user
              -  List issues (ppajersk) or (Paul)

            - @Cidrbot list (all) issues in (repo)
              -  Omit "all" to display only the unassigned issues
              -  Example: list all issues in ciscops/cidrbot

        -Assign/Unassign issue:
          @Cidrbot (assign/unassign) (repo) (issue_num) (me, Git username, Webex firstname)

            - @Cidrbot assign/unassign (repo) (issue_num) (me / Webex firstname / Git username)
              -  Example syntax: @Cidrbot assign ciscops/cidrbot 1 me
              -  Example syntax2: @Cidrbot unassign ciscops/cidrbot 1 ppajersk
              -  Example syntax3: @Cidrbot unassign ciscops/cidrbot 1 Paul - (Only if user is in the cidrbot room)
              -  Webex firstname = Paul or Git username = ppajersk

              -  Note: unassigning a pull request is a currently disabled feature  


        -Reminders/notifications:
          Users have the option to enable reminders. Every time an issue/pr is assgined to them
          in the cidrbot users room, a notification is sent to them. Additionally, cidrbot messages
          each user who has reminders enabled, a weekly list of all the issues they are currently
          assigned to in the repo pool.      

             - Avaliable only in direct messages with cidrbot: 'Enable reminders' | 'Disable reminders'    


        -Repo pool:
          Cidrbot uses a pool of repos that is containted within dynamodb. Unless specified otherwise,
          cidrbot will always return all issues from this pool of repos.

             - @Cidrbot list repos

             For moderators only in chat rooms, (add or remove from repo pool):

             - @Cidrbot add repo (repo name)
             - @Cidrbot remove repo (repo name)


## How Cidrbot works

Cidrbot uses a combination of AWS services, alongside webhooks from Webex to run.
Moving forward, all parts of cidrbot which rely on AWS will be set up by cloud formation.

#### File structure

    * cidrbot_run.py - lambda py file which interprets Apigateway requests
      * wxt_cidrbot
        * cidrbot.py - Driver script
        * cmd_list.py - Message interpreter
        * dynamo_api_handler.py - Communicates with dynamodb for persistent data
        * git_api_handler.py - Responsible for querying github for all needed
        information, as well as concatenating all the issues & prs

        * webex_edit_message.py - Used to edit the initial message displayed to
        the user. This is a short file but needed since the webexteamssdk does not
        support this feature, however the rest api does.

## Deploying


Steps to deploy the cloud formation as well as upload all the necessary code to the lambda functions

1) * [Create a webex bot](https://developer.webex.com/docs/bots)
From webex bot creation, save the following: Webex bot id, Webex bot access token


2) * [Create a github app](https://docs.github.com/en/developers/apps/building-github-apps/creating-a-github-app)
From github bot creation, save the following: App ID, Client ID, Client Secret, Private key
Leave all the current settings as is for now

3) In cloud_formation.yaml, parameters should be set up as follows: (replace the empty string in the "default:" section)
    - For awsSecretsKey, paste the literal contents of the Private key for the github app (which comes as a pem file)
    - For appId, appClientId, appClientSecret, use the secrets and ids you saved from step 2
    - For securityPolicyName, securityGroupId, subnetId, lambdaExecutionRole, paste in desired values according to how the aws account is setup
    - For organizationId, enter in the webex org id for the organization using the webex bot
    - For regionName, enter the region of the aws account that the aws secrets manager and lambda function both share
    - For webexBotId, webexAccessToken, use the values from step 1
    - For lambdaDomainName, this will be the name you use for the custom domain name inside Apigateway
    - For lambdaAcmCert, fill this out with the necessary cert
    - For route53RecordGroupSetHostedZone, provide the necessary hosted zone id
    - For any values that are pre-filled, leave these alone

4) Run the following command to push the cloud formation template into a desired aws account:
    - "aws cloudformation deploy --stack-name desired_stack_name_here --template-file cloud_formation.yaml"

5) Pushing code into both lambda functions
    - In the make file, ensure lines 5 and 6, match the lambda function names entered in the cloud formation file, with the github lambda function name in line 5, and the main lambda function name on line 6
    (In cloud_formation.yaml they are referenced in the parameters as gitLambdaFunctionName and lambdaFunctionName respectively)
    - Ensure on line 11, that PYDIRS=wxt_cidrbot for the first make file code push
    - (note on macs, run "make build-container" then "make lambda-packages-docker" then run the two following commands)
    Run the following commands: (make lambda-layer-cidrbot) then (make lambda-upload-cidrbot)
    - On line 11, change PYDIRS=wxt_cidrbot to PYDIRS=git_cidrbot
    - Run the following commands: (make lambda-layer-gitauth) then (make lambda-upload-gitauth)

6) In the github app ui, set the Callback URL to the value stored in the environment variables for the git lambda function. It will be the value for the key "CALLBACKURL"
    - Check the button underneath for "Request user authorization (OAuth) during installation"
    - Under "webhook" check the button for "active" and in the "webhook url" box, set the url to
    "https://" + 1 + / + 2
    1. (custom domain name specified in cloud_formation under lambdaDomainName)
    2. (the value for the key "GITHUB_WEBHOOK_PATH" in environment variables for the main lambda function)

7) Permissions for github app in the ui
    - Discussions : Read & write
    - Issues : Read & write
    - Metadata : Read only
    - Pull requests : Read & write

#### Build on MacOS

##### Create builder image (only needs to be done once)
```bash
make build-container
```

##### Build and push
```bash
make lambda-packages-docker
make lambda-layer
make lambda-upload-webhook
make lambda-upload-auto
```
