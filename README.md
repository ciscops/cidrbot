# cidrbot
CIDR bot

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