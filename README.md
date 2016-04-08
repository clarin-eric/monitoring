[![Build Status](https://travis-ci.org/clarin-eric/monitoring.svg?branch=master)](https://travis-ci.org/clarin-eric/monitoring)

# Monitoring configuration for networked CLARIN services and applications.

The main portal for information about CLARIN monitoring is https://trac.clarin.eu/wiki/SystemAdministration/Monitoring.

## Workflow

1. After pushing a new revision to the [Git repository]'s master branch, [Travis CI] attempts to build it.
  * You have to check immediately whether that build succeeds. If your revision results in a failed build, you have fix it straight away.
1. After completion of the Travis CI build of the new revision, Travis CI triggers a GitHub [web hook]. A small [web service] is listening on the [monitoring host]. If this web service is triggered via the `push` web hook, and the payload says the build was successful, the web service invokes a `reload`. 
1. The `reload` operation updates the [Icinga] configuration on the monitoring server via `git pull` within `/etc/icinga/`. Finally it restarts the Icinga daemon. The revised configuration will be used from then on. The output of previous `reload` operations is [publicly available](https://clarin.fz-juelich.de:7011/logs/).

## Automatically used Centre Registry information
The Python program [`config_generation_centerregistry.py`] performs a configuration processing.
1. It pulls this [Git repository]’s `master` branch using [cron scheduling].
2. Retrieves data about centre endpoints using the [Centre Registry] API.
3. It modifies the Icinga configuration in this Git repo, in particular the configuration per centre as stored in `configuration/{shorthand}.cfg` files, where `{shorthand}` is the centre’s shorthand in the [Centre Registry].
4. It then pushes the changes to the Git repository to the `master` branch, if there were changes

## Notes
* New monitoring plugins/probes should be in the `probes` directory. In [Icinga] `.cfg` files you can refer to the directory with `$USER3$`.

[Travis CI]: https://travis-ci.org/clarin-eric/monitoring
[Icinga]: https://clarin.fz-juelich.de/icinga
[Centre Registry]: https://centres.clarin.eu
[Git repository]: https://github.com/clarin-eric/monitoring
[`config_generation_centerregistry.py`]: config_generation/config_generation_centerregistry.py
[cron scheduling]: https://trac.clarin.eu/wiki/SystemAdministration/Hosts/fsd-cloud22.zam.kfa-juelich.de#Scheduledjobs
[web service]: https://github.com/BeneDicere/simplistic-webhook-listener
[web hook]: https://developer.github.com/webhooks/
[monitoring host]: https://trac.clarin.eu/wiki/SystemAdministration/Hosts/fsd-cloud22.zam.kfa-juelich.de
