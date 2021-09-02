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

#### Creating a webex bot

    Note: When creating, hold on to the access token, this is needed inside
    the lambda function to connect to the webex bot and send messages through
    it to the cidrbot room

* [Create a webex bot](https://developer.webex.com/docs/bots)


#### Webhooks:

    Cidrbot uses 4 main webhooks from webex. These can be created by following
    the link and using the appropriate arguments listed below. It's crucial
    to use the bots access token when creating the webhook for direct messages!

    - Webex: https://developer.webex.com/docs/api/v1/webhooks/create-a-webhook

    1) Message webhook for when a user sends a message inside the cidrbot room
      - Authorization: Use bot's access token!
      - name: "Message"
      - targetUrl: (Aws Custom domain name)
      - resource: "messages"
      - event: "created"
      - filter: roomId=(room id where the bot will operate)

    2)  Message webhook for when a user sends cidrbot a direct message
      - Authorization: Use bot's access token!
      - name: "Direct Message"
      - targetUrl: (Aws Custom domain name)
      - resource: "messages"
      - event: "created"
      - filter: "roomType=direct"

    3)  Memberships Webhook for when a user enters the cidrbot room
      - Authorization: Use bot's access token!
      - name: "New user"
      - targetUrl: (Aws Custom domain name)
      - resource: "memberships"
      - event: "created"
      - filter: roomId=(room id where the bot will operate)

    4)  Memberships Webhook for when a user enters the cidrbot room
      - Authorization: Use bot's access token!
      - name: "User left"
      - targetUrl: (Aws Custom domain name)
      - resource: "memberships"
      - event: "deleted"
      - filter: roomId=(room id where the bot will operate)    

* [Aws Custom domain name](https://docs.aws.amazon.com/apigateway/latest/developerguide/how-to-custom-domains.html)



#### Github

      Creating a Github account for cidrbot is necessary for assigning issues/prs
      as well as increasing the ratelimit of api calls from 60/hour to
      1,000 per hour per repo.

      Remember to hang onto the access token, as well as giving the token the needed
      permissions to assign/unassign issues/prs. This account will need to be added
      to an org or repo, and given triage access. (Note triage access does not allow
      unassigning requested reviewers from a pull request)


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
