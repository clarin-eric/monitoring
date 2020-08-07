[![Build Status](https://travis-ci.org/clarin-eric/monitoring.svg?branch=master)](https://travis-ci.org/clarin-eric/monitoring)

# Monitoring configuration for networked CLARIN services and applications.

The main portal for information about CLARIN monitoring is https://trac.clarin.eu/wiki/SystemAdministration/Monitoring.

## Workflow

1. After pushing a new revision to the [Git repository]'s master branch, [Travis CI] attempts to build it.
  * You have to check immediately whether that build succeeds. If your revision results in a failed build, you have fix it straight away.
1. After completion of the Travis CI build of the new revision, Travis CI triggers a GitHub [web hook]. A small [web service] is listening on the [monitoring host]. If this web service is triggered via the `push` web hook, and the payload says the build was successful, the web service invokes a `reload`.
1. The `reload` operation updates the [Icinga] configuration on the monitoring server via `git pull` within `/etc/icinga/`. Finally it restarts the Icinga daemon. The revised configuration will be used from then on. The output of previous `reload` operations is [publicly available](https://clarin.fz-juelich.de:7011/logs/).

## Automated config manipulation using Centre Registry information
The Python program [`update_config.py`] performs a hourly configuration manipulation, triggered by a cron job on the monitoring host.

1. It pulls this [Git repository]’s `master` branch.
2. Retrieves data about centre endpoints using the [Centre Registry] API.
3. It modifies the Icinga configuration in this Git repo, in particular the configuration per centre as stored in `conf.d/hosts/{shorthand}.cfg` files, where `{shorthand}` is the centre’s shorthand in the [Centre Registry].
4. It then pushes the changes to the Git repository to the `master` branch, if there were changes.

## Setup
1. Setup `icinga2`, requires at the moment MySQL/MariaDB due to icingaweb2 modules. Following instructions from the [docu](https://icinga.com/docs/icinga2/latest/doc/02-installation/).
2. Clone this repo to `/etc/icinga2`. Several config files are overritten by this. Keep all that are in the gitignore.
3. Setup (`icingaweb2`)[https://icinga.com/docs/icingaweb2/latest/doc/02-Installation/] with modules:
   * For authentication setup (Shibboleth)[https://wiki.shibboleth.net/confluence/display/SHIB2/NativeSPApacheConfig]
   * [reporting](https://github.com/Icinga/icingaweb2-module-reporting) including [](https://github.com/Icinga/icingaweb2-module-reporting/pull/64)
   * [idoreports](https://github.com/Icinga/icingaweb2-module-idoreports)
   * [map](https://github.com/nbuchwitz/icingaweb2-module-map)
       * Add `/etc/icingaweb2/modules/map/maps.ini` for the german clarin centres
          ```
          [clarin]
          default_zoom=7
          default_lat=51.00
          default_long=11.36
          hostgroup=(ASV|BAS|BBAW|EKUT|HZSK|IDS|IMS|UdS)
         ```
       * Edit `/usr/share/icingaweb2/modules/map/configuration.php` to add navigation for german map.
   * Create roles, either by using the web interface or by editing `roles.ini`. Create an `Administrator` role for all adminsitrators and a `Clarin` role for everyone else with just view permissions, e.g. `permissions = "module/idoreports,module/ipl,module/map,module/monitoring,monitoring/command/acknowledge-problem,module/reactbundle,module/reporting,module/translation"`.
4. Add cronjob to regularly update from centre config.
```0 */1 * * * cd /etc/icinga2 && /usr/bin/python3 /etc/icinga2/update_config.py --push && systemctl reload icinga2 >> PATH/cron.log 2>&1```

[Travis CI]: https://travis-ci.org/clarin-eric/monitoring
[Icinga]: https://clarin.fz-juelich.de/icinga
[Centre Registry]: https://centres.clarin.eu
[Git repository]: https://github.com/clarin-eric/monitoring
[`update_config.py`]: update_config.py
[cron scheduling]: https://trac.clarin.eu/wiki/SystemAdministration/Hosts/fsd-cloud22.zam.kfa-juelich.de#Scheduledjobs
[web service]: https://github.com/BeneDicere/simplistic-webhook-listener
[web hook]: https://developer.github.com/webhooks/
[monitoring host]: https://trac.clarin.eu/wiki/SystemAdministration/Hosts/fsd-cloud22.zam.kfa-juelich.de
