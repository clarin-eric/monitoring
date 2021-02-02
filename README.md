[![Build Status](https://travis-ci.com/clarin-eric/monitoring.svg?branch=master)](https://travis-ci.com/clarin-eric/monitoring)

# Monitoring configuration for networked CLARIN AND DARIAH services and applications.

The main portal for information about CLARIN monitoring is https://trac.clarin.eu/wiki/SystemAdministration/Monitoring/Icinga.

## Workflow

1. After pushing a new revision to the [Git repository]'s, [Travis CI] attempts to build it, i.e. running the `update_config` script and checks the resulting icinga2 config.
  * You have to check immediately whether that build succeeds. If your revision results in a failed build, you have fix it straight away.
  * Files in `conf.d/sites` are host for manual edit only.
2. Every our a cron job on the Server pulls the latest revision if the Travis build succeeded and runs the `update_script`, which pushed changes if there are any and restarts icinga with the latest config. The cron job is configured to notify the sysadmins on failure.

## Automated config manipulation using Centre Registry information
The Python program [`update_config.py`] performs a hourly configuration manipulation, triggered by a cron job on the monitoring host.

1. It pulls this [Git repository]’s `master` branch and the `master` branch from the [`monitoring-users`](https://github.com/clarin-eric/monitoring-users) submodule.
2. Retrieves data about centre endpoints using the [Centre Registry] API.
2. Retrieves data about switchboard tool registry using the [Switchboard] API.
3. It modifies the Icinga configuration in this Git repo, in particular the configuration per centre as stored in `conf.d/hosts/{shorthand}.cfg` files, where `{shorthand}` is the centre’s shorthand in the [Centre Registry], `conf.d/switchboard-tool-registry.conf` for the [Switchboard]. The user information in `conf.d/users/centre-registry.conf`, `conf.d/users/switchboard-tool-registry.conf` and in `conf.d/user-groups.conf`.
4. It then pushes the changes to the Git repository to the `master` branch and submodule, if there were changes.

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
   * Create roles, either by using the web interface or by editing `roles.ini`. Create an `Administrator` role for all adminsitrators and a `Clarin` role for everyone else with just view permissions, e.g. `permissions = "module/idoreports,module/ipl,module/map,module/monitoring,monitoring/command/acknowledge-problem,module/reactbundle,module/reporting,module/translation"`, current `roles.ini`:
   ```
   [Administrators]
   users = "ADMIN_USERS_LIST"
   permissions = "*"
   groups = "Administrators"

   [DARIAH-DE]
   users = "DARIAH_USERS_LIST"
   permissions = "module/idoreports,module/ipl,module/map,module/monitoring,monitoring/command/acknowledge-problem,module/reactbundle,module/reporting,module/translation"
   groups = "DARIAH-DE"
   monitoring/filter/objects = "hostgroup_name=DARIAH-DE"

   [CLARIN]
   users = "CLARIN_USERS_LIST"
   permissions = "module/idoreports,module/ipl,module/map,module/monitoring,monitoring/command/acknowledge-problem,monitoring/command/comment/add,monitoring/command/downtime/schedule,module/reactbundle,module/reporting,module/translation"
   groups = "CLARIN"
   monitoring/filter/objects = "hostgroup_name=CLARIN"

   [Guests]
   users = "*"
   permissions = "application/share/navigation,module/reporting,module/map"
   ```
4. Add cronjob to regularly update from centre config.
```@hourly (cd /etc/icinga2 && /usr/bin/python3 /etc/icinga2/update_config.py --travis && git pull && git submodule update && git submodule update && /usr/bin/python3 /etc/icinga2/update_config.py --push && systemctl reload icinga2 && sleep 3 && echo "icinga2 status: $(systemctl is-active icinga2)") 2>&1 | mail -s "Cronjob update_config.py" -a "From: monitoring@clarin.eu" MAIL1 MAIL2```


[Travis CI]: https://travis-ci.com/clarin-eric/monitoring
[Icinga]: https://monitoring.clarin.eu
[Centre Registry]: https://centres.clarin.eu
[Git repository]: https://github.com/clarin-eric/monitoring
[`update_config.py`]: update_config.py
