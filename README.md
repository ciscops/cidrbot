# Cidrbot
  Cidrbot is a Lambda based script, leveraging Webex and Github apps to provide users with an interface to interact with Github through a Webex chatroom. It's main purpose is to aid in the Github pipeline by compiling Github data in a central chatroom location for any given installation.


![cidrbot_visual_final](/assets/cidrbot_visual_final.png)

## Requirements  
  * Webex teams bot
  * Github app
  * Aws    

## Description

Cidrbot is is a Webex Teams bot which relies on AWS infrastructure to provide a medium
between the Webex client and Github. Cidrbot is a room based bot, which means that only
the users within the bot's chat room may interact with the bot (either through the chat room
or through direct messages).

Cidrbot's purpose is to facilitate tracking Github issues as well as provide an easy method
to assign issues. @Cidrbot List all issues, will return a list of all the issues in a pool of
repositories, with the issue name, number, associated repo, as well as hyperlinking the name
for easy access. Additionally, Cidrbot can display any assigned users for an issue, and any
requested reviewers for a pull request.

@Cidrbot list issues, is a command which returns only unassigned issues. This command
can be paired with a repository name, to list unassigned issues in a single repository.
Example: @Cidrbot list issues in ciscops/cidrbot

Cidrbot allows referencing a user by their first name shown in Github, as long as no two
people in the room share the same name, or the user is not in the room.

If a user is not in the room, but they are within the Github org of the issue/pull request
which needs to be assigned, their Github username may be used.

Cidrbot uses the Github app infrastructure to operate, using expiring user-to-server access tokens
signed by a JWT, as well as the permissions allowed for a given installation of the Github app.
Apps can operate both in and out of Github orgs allowing for either group or individual use of the bot.

## Commands/Features

    All commands for Cidrbot are only accessible in Webex rooms. Direct messages is reserved for toggling reminders.

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

          - @Cidrbot (repo name) (issue number) info
            - Details about a certain issue (comment, commits, date created..)

    -Assign/Unassign issue:
          @Cidrbot (assign/unassign) (repo) (issue_num) (me, Git username, Webex firstname)

          - @Cidrbot assign/unassign (repo) (issue_num) (me / Webex firstname / Git username)
            -  Example syntax: @Cidrbot assign ciscops/cidrbot 1 me
            -  Example syntax2: @Cidrbot unassign ciscops/cidrbot 1 ppajersk
            -  Example syntax3: @Cidrbot unassign ciscops/cidrbot 1 Paul - (Only if user is in the cidrbot room)
            -  Webex firstname = Paul or Git username = ppajersk

    -Reminders/notifications:
          Users have the option to enable reminders. Every time an issue/pr is assgined to them
          in the cidrbot users room, a notification is sent to them. Additionally, cidrbot messages
          each user who has reminders enabled, a weekly list of all the issues they are currently
          assigned to in the repo pool.      

          - Avaliable only in direct messages with cidrbot: 'Enable reminders' | 'Disable reminders'    

    -Repo pool:
          - @Cidrbot list repos
          - Returns a list of all the repos accessible to the bot for a given room

    -Adding repos / authorizing a Github app (Github ui)
          Cidrbot uses a Github app for all interactions with Github. This
          means that authorizing a Github installation is done with the following command:

          - @Cidrbot manage repos (Only moderators of a Webex room can access this command)
          - Direct messages a user with a link that sends them to Github to authorize the app to access repo(s)

          After a successful authorization, Cidrbot informs the user of which repos
          it can now access through Webex, and all the users in the room now can
          interact with the repo through commands.

          To add/remove repos or remove an installation, navigate to Github's page for
          apps and use their ui to do so. Cidrbot will update the user accordingly in
          Webex about any of these actions. When a repo or installation is removed from
          Github, the bot no longer retains any access to the repos and the bot will
          inform users in the room that the given repos are no longer available.


## How Cidrbot works

Cidrbot uses a combination of Aws services, the Webex bot infrastructure, and Github's
app infrastructure to run. Two lambda function scripts are the core drivers of the
process, one being responsible for the core interactions with Webex and Github, and
the other performing the necessary tasks to authorize Github apps and handle the
authorization cycle.

In combination, both lambda scripts provide a beginning and end point for an
authorization, using Dynamodb to communicate and share one time codes to identify the
user between Webex and Github, and eventually back to Webex.

![cidr_auth_visual](/assets/cidr_auth_visual.png)

#### File structure

    Main Lambda function (cidrbot)
    - cidrbot_run.py - lambda py file which interprets Apigateway requests
       /wxt_cidrbot
        - cidrbot.py (Processes webhooks and directs them the appropriate class)
        - cidrbot_room_setup.py (Handles the bot being invited to a webex chatroom/builds Webex webhooks and Dynamodb room data)
        - cmd_list.py (interprets user messages and executes the appropriate function in response)
        - dynamo_api_handler (Handles all interactions to dynamodb)
        - git_api_handler (Handles assigning/listing issues and all other repo based interactions)
        - git_webhook_handler (Handles Github app installation webhooks, currently for adding/removing repos via Git ui)
        - webex_edit_message (Webex api doesn't provide support for editing messages, hence the reason for this)

    Secondary Lambda function (cidrbot/gitauth)    
    - cidr_git_lambda_function.py - lambda py file which interprets Apigateway requests
       /git_cidrbot
        - gitauth.py (Accepts callback requests from Github, processing the data of auth
          request, creating an app access key, adding the necessary data to Dynamo, and
          sending an update message to the Webex room)

## Deploying
Steps to deploy the cloud formation as well as upload all the necessary code to the lambda functions
1) * [Create a webex bot](https://developer.webex.com/docs/bots)
Save Bot access token, and bot name
2) * [Get bot id](https://developer.webex.com/docs/api/v1/people/list-people)
Under email, input the bot's email (botName + @webex.bot)
Press Run, and save the bot's id from the response (this is the bot's true webex id that shows in webhooks)
2) * [Create a github app](https://docs.github.com/en/developers/apps/building-github-apps/creating-a-github-app)
From github bot creation, save the following: App ID, Client ID, Client Secret, Private key and bot name
Leave all the current settings as is for now

3) In cloud_formation.yaml, parameters should be set up as follows: (replace the empty string in the "default:" section)
    - For awsSecretsKey, paste the literal contents of the Private key for the github app (which comes as a pem file)
    - For appId, appClientId, appClientSecret, use the secrets and ids you saved from step 3
    - For securityPolicyName, securityGroupId, subnetId, lambdaExecutionRole, paste in desired values according to how the aws account is setup
    - For organizationId, enter in the webex org id for the organization using the webex bot
    - For regionName, enter the region of the aws account that the aws secrets manager and lambda function both share
    - For webexBotId, webexAccessToken, webexBotName, use the values from step 1 and step 2
    - For lambdaDomainName, this will be the name you use for the custom domain name inside Apigateway
    - For lambdaAcmCert, fill this out with the necessary cert
    - For route53RecordGroupSetHostedZone, provide the necessary hosted zone id
    - For any values that are pre-filled, leave these alone

4) Run the following command to push the cloud formation template into a desired aws account:
    - "aws cloudformation deploy --stack-name desired_stack_name_here --template-file cloud_formation.yaml"

5) Pushing code into both lambda functions
    - In the make file, ensure lines 5 and 6, match the lambda function names entered in the cloud formation file, with the github lambda function name in line 5, and the main lambda function name on line 6
    (In cloud_formation.yaml they are referenced in the parameters as gitLambdaFunctionName and lambdaFunctionName respectively)
    - (note on macs, run "make build-container" then "make lambda-packages-docker" then run the two following commands)
    Run the following commands: (make lambda-layer-cidrbot) then (make lambda-upload-cidrbot)
    - In aws lambda console, add the layers to the lambda functions before continuing
    - Run the following commands:
    1) make clean clean-lambda
  	2) make lambda-upload-cidrbot
  	3) make clean clean-lambda
  	4) make lambda-upload-gitauth

6) Configuring Github app with correct webhook and callback urls (in Github ui)
    The values in parentheses can be fine as parameters in the cloud formation file
    - Set the Callback URL to the following:
    "https://" + (lambdaDomainName) + / + (apiGitAuthMappingKeyName) + / + (gitLambdaFunctionName)

    - Check the button underneath for "Request user authorization (OAuth) during installation"
    - Under "webhook" check the button for "active" and in the "webhook url" box, set the url to
    "https://" + (lambdaDomainName) + / + (apiGitMappingKeyName) + / + (lambdaFunctionName)
    - Navigate to permissions and events tab
    Under "Subscribe to events" at the bottom of the page, select "Repository", "Issues" and "Pull Request" and save all changes
7) Permissions for Github app in the ui
    - Discussions : Read & write
    - Issues : Read & write
    - Metadata : Read only
    - Pull requests : Read & write
8) * [Create direct message and bot invited to room webhooks in Webex ui](https://developer.webex.com/docs/api/v1/webhooks/create-a-webhook)
    The target url used in these webhooks will be the following: (values from cloud formation)
    targetUrl: "https" + (lambdaDomainName) + / + (lambdaFunctionName)
    Using the link above, create the following two webhooks
        - (Use bot's access token)(name : 'Direct Message')(targetUrl)(resource : 'messages')('event' : 'created')('filter': 'roomType=direct')
        - (Use bot's access token)(name : 'Bot add to room')(targetUrl)(resource : 'memberships')('event' : 'created')

9) Enabling the timed actions:
    - To ensure the daily and weekly reminders work, in aws console, enable both timers as they are set to off by default        

    - Side note, testing the daily and weekly reminders:
    Create an aws lambda test with the values

     - { "Type": "Timer"}
     and for test 2
     - { "Type": "Weekly Timer"}

     Timer will send the daily room message with all issues and prs
     Weekly timer will send all users with reminders enabled, a direct message to review the issues/prs assigned to them.
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
