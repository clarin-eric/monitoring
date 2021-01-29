FROM ubuntu:20.04

RUN apt-get update \
    && apt-get install -yy \
        wget \
        icinga2-bin

RUN wget https://raw.githubusercontent.com/clarin-eric/monitoring/master/conf.d/templates.conf -O /etc/icinga2/conf.d/templates.conf
RUN wget https://raw.githubusercontent.com/clarin-eric/monitoring/master/conf.d/user-groups.conf -O /etc/icinga2/conf.d/user-groups.conf

ENTRYPOINT ["icinga2", "daemon"]
CMD [ "-C" ]
