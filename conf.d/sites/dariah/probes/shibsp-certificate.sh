#!/bin/bash

ENTITYID=$1

function getdays {
  text="# This Python file uses the following encoding: utf-8
from datetime import datetime
from datetime import date
date_object = datetime.strptime('${1}', '%b %d %H:%M:%S %Y %Z').date()
validtime = date_object - date.today()
print validtime.days
"
  validdays=`echo "$text" | python -`
  echo "${validdays}"
}


function getnotafter {
  text="# This Python file uses the following encoding: utf-8
from lxml import etree
metadatastring=u'''${1}'''
SSLRESULT = etree.fromstring(metadatastring)
CERT = SSLRESULT.xpath('/md:EntityDescriptor/md:SPSSODescriptor/md:KeyDescriptor/ds:KeyInfo/ds:X509Data/ds:X509Certificate', namespaces={'md':'urn:oasis:names:tc:SAML:2.0:metadata', 'ds':'http://www.w3.org/2000/09/xmldsig#'})[0].text
print('-----BEGIN CERTIFICATE-----')
print(CERT.strip())
print('-----END CERTIFICATE-----')
"
  NOTAFTER=`echo "$text" | python3 - | openssl x509 -text -noout | grep 'Not After' | sed 's/.*Not After : \(.*\)$/\1/'`
  echo $NOTAFTER
}


METADATA=`curl -s -L $ENTITYID`

NOTAFTER=`getnotafter "${METADATA}"`

DAYS=`getdays "${NOTAFTER}"`

if [ "$DAYS" -lt 10 ]; then
  echo "Less than 10 days until ${NOTAFTER}"
  exit 2
elif  [ "$DAYS" -lt 31 ]; then
  echo "Less than one month until ${NOTAFTER}"
  exit 1
else
  echo "Shibboleth Certificate valid until ${NOTAFTER}"
  exit 0
fi


