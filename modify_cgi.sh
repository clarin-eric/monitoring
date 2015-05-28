#!/bin/bash
. cgi_config.ini
sed -i 's/CLARINADMINS/'$CLARINADMINS'/g' cgi.cfg