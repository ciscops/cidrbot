# cidrbot
Lambda based bot that aids in CL pipeline by giving users an interface to interact with Github repos/issues/prs through a Webex chatroom

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

## Requirements  
* webexteamssdk 1.6
* pygithub 1.55
* AWS Lambda, Cloudwatch, Apigateway
