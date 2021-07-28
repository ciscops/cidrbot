FROM public.ecr.aws/bitnami/python:3.8-prod

WORKDIR /build
RUN apt -y update && \
    apt -y install \
      git \
      make \
      zip && \
    rm -rf /var/lib/apt/lists/* && \
    mkdir /.local && \
    chmod 1777 /.local