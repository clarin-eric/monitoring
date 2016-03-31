[![Build Status](https://travis-ci.org/clarin-eric/monitoring.svg?branch=master)](https://travis-ci.org/clarin-eric/monitoring)

# Monitoring configuration for networked CLARIN services and applications.

The main portal for information about CLARIN monitoring is https://trac.clarin.eu/wiki/SystemAdministration/Monitoring.

[Travis CI]: https://travis-ci.org/clarin-eric/monitoring
[Icinga]: https://clarin.fz-juelich.de/icinga
[NagVis]: https://clarin.fz-juelich.de/nagvis/frontend/nagvis-js/index.php
[Centre Registry]: https://centres.clarin.eu
[Git repository]: https://github.com/clarin-eric/monitoring

## Workflow

1. Every hour this [Git repository]’s master branch is pulled using cron scheduling, centre data is retrieved using the [Centre Registry] API by [`config_generation/config_generation_centerregistry.py`](config_generation/config_generation_centerregistry.py).
* After pushing a new revision to the [Git repository]'s master branch, you have to check immediately whether the build succeeds on [Travis CI]. If your revision results in a failed [Travis CI] build, you have fix it straight away.
1. If the [Travis CI] ‘build’ of the new revision is successful, the [Icinga] configuration in [Git repository] is processed and expanded based on that by [`config_generation/config_generation_centerregistry.py`](config_generation/config_generation_centerregistry.py). These expansions of the configuration per centre are stored in `configuration/{shorthand}.cfg`, where `{shorthand}` is the centre’s shorthand in the [Centre Registry]. The expanded configuration is pushed to the [Git repository]’s master branch.
1. A small [web service](https://github.com/BeneDicere/simplistic-webhook-listener) is listening on the monitoring server: . If this web service receives an HTTP request from [Travis CI], and the payload says the build was successful, it executes a 'reload command' on the server. The output of the 'reload command' is [publicly available](https://clarin.fz-juelich.de:7011/logs/)
1. The 'reload command' updates the production [Icinga] configuration on the monitoring server via `git pull` within `/etc/icinga/`. Finally it restarts [Icinga]. The new/expanded configuration will be used in production from then on.

## Notes
* New monitoring plugins/probes should be in the `probes` directory. In [Icinga] `.cfg` files you can refer to the directory with `$USER3$`.
* [NagVis].
