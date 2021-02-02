FROM ubuntu:20.04

RUN apt-get update \
    && apt-get install -yy \
        wget \
        icinga2-bin

ENTRYPOINT ["icinga2", "daemon"]
CMD [ "-C" ]
