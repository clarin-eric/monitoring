#!/bin/bash
#
# Version 2018-12-06
#   - Kompatibilitaet openssl 1.1 ("CN = " vs. "CN=")
#
# Version 2017-05-17
#   - Beitrag von Markus Krieger: Anpassung an G2 der DFN-PKI
#
# Version 2014-11-21
#   - UTF-8-Umlaute ersetzt
#
# Version 2014-11-07
#   - SSL 3.0-Test: Robuster, funktioniert jetzt auch mit
#     MS IIS 7.5 Windows Server 2008R2 als Gegenstelle
#
# Version 2014-10-27
#   - SSL 3.0-Test: Funktioniert jetzt auch mit F5 als Gegenstelle
#
# Version 2014-10-23
#   - Return-Code von openssl beim SSL 3.0-Test ist versionabhaengig.
#     Test korrigiert und plattformunabhaengiger gemacht.
#
# Version 2014-10-16-1
#   - Falscher Zeitraum Zertifikatablauf korrigiert
#
# Version 2014-10-16
#   - Bei abgelaufenem/bald ablaufendem Serverzertifikat einen Hinweis ausgeben
#
# Version 2014-10-15
#   - Test auf SSL v3
#
# Version: 2014-09-22-1
#   - Beruecksichtigung des Ablaufdatums des Serverzertifikats.
#     Bei Ablauf vor 2016 keine Warnung ausgeben.
#
# Version: 2014-09-22
#   - curl alternativ (bevorzugt) zu wget
#
# Version: 2014-09-19
#   - unterstuetzt jetzt name-based virtual Web-Server (mit openssl client mit SNI)
#   - testet nun auch das Einrichtungs-CA-Zertifikat

export LC_ALL=C

SERVER="$1"
PORT="$2"

SSL3=0
EXPIRES=0

JUL2014=0
FEB2014=0
DEZ2006=0
FEB2016=0	# Das neue Global G02 Zertifikat
DFNPCA_G1=0	# G01 CA-Chain
DFNPCA_G2=0	# G02 CA-Chain
CA=0
SHA1SERVERCERT=0
SHA1CACERT=0

RC=0
CHAIN_HINWEIS_INSTALL=0
CERT_HINWEIS_REPLACE=0


if [ -z "${PORT}" ] ; then
   PORT=443
fi  

type wget >/dev/null 2>&1
if [ $? -eq 0 ] ; then
  GET_PROGRAM="wget -O - "
fi

type curl >/dev/null 2>&1
if [ $? -eq 0 ] ; then
  GET_PROGRAM="curl "
fi

if [ -z "$GET_PROGRAM" ] ; then
  echo "Dieses Skript funktioniert nur mit installiertem curl oder wget."
  exit 1
fi

type openssl >/dev/null 2>&1
if [ $? -ne 0 ] ; then
  echo "Dieses Skript funktioniert nur mit installiertem openssl."
  exit 1
fi


openssl s_client -connect "${SERVER}:${PORT}" -servername "${SERVER}" -showcerts  </dev/null 2>&1 | grep -q -- "-----BEGIN CERTIFICATE-----"

if [ $? -ne 0 ] ; then
   echo
   echo "Server ${SERVER}, Port ${PORT} ist nicht erreichbar (Tippfehler?)"
   echo
   exit 1
fi   

###################
# SSL 3? Bei SSL3 Ausgabe mit "SSL alert number 40", oder bei F5-Hosts "SSL routines:SSL3_GET_RECORD:wrong version number:"

# Versuche eine SSLv3 Verbindung zum Server aufzubauen
SSL3_PROBE_STDOUT=`openssl s_client -connect "${SERVER}:${PORT}" -servername "${SERVER}" -ssl3  </dev/null 2>/dev/null`
SSL3_PROBE_STDERR=`openssl s_client -connect "${SERVER}:${PORT}" -servername "${SERVER}" -ssl3  </dev/null 2>&1 1>/dev/null`

# Pruefung, ob eine SSLv3-Verbindung zum Server aufgemacht werden kann. False-Negatives sind zu vermeiden.

# pruefe, ob die typischen Fehlermeldungen beim Verbindungsaufbau mit Server-seitig abgeschaltetem SSLv3 auftreten:
#
# normalerweise ein "SSL alert number 40"
# bei F5-Hosts "SSL routines:SSL3_GET_RECORD:wrong version number:"
# generell ein ":ssl handshake failure:"
echo "${SSL3_PROBE_STDERR}" | egrep -qi "(SSL alert number 40|SSL routines:SSL3_GET_RECORD:wrong version number:|:ssl handshake failure:)"
if [ $? -eq 0 ] ; then
   # ja es gibt Fehler, also ist keine SSLv3 Verbindung aufgebaut
   SSL3=0
else
   # nein, also weiter pruefen, ob es dann eben Anzeichen fuer einen *erfolgreichen* Verbindungsaufbau gibt
   #
   # pruefe, ob es eine neue SSLv3 Verbindung gibt (da openssl mit -ssl3 Option gestartet wird, kann es keine TLSv1 Verbindung sein) 
   echo "${SSL3_PROBE_STDOUT}" | egrep -qi "^ *New, TLSv1/SSLv3, Cipher is "
   if [ $? -eq 0 ] ; then
      # ja, also gibt es eine SSLv3 Verbindung
      SSL3=1
   else
      # nein, also
      # pruefe weiter, ob ein Master-Key augehandelt wurde
      echo "${SSL3_PROBE_STDOUT}" | egrep -qi "^ *Master-Key\: ([0-9a-f])+ *$"
      if [ $? -eq 0 ] ; then
         # ja, also gibt es eine SSLv3 Verbindung
         SSL3=1
      else
         # nein, also
         # pruefe weiter, ob ein Server-Zertifikat gesendet wurde
         echo "${SSL3_PROBE_STDOUT}" | egrep -qi "^ *Server certificate *$"
         if [ $? -eq 0 ] ; then
            # ja, also gibt es eine SSLv3 Verbindung
            SSL3=1
         else  
            # nein, es gibt keine Anzeichen fuer eine erfolgreiche SSLv3 Verbindung
            SSL3=0
         fi
      fi   
   fi
fi   



# Daten des Server-Zertifikats:
SERVERCERT=`openssl s_client -connect "${SERVER}:${PORT}" -servername "${SERVER}"  </dev/null 2>&1 | openssl x509 -text`

SERIAL=`echo "${SERVERCERT}" | egrep '^ *Serial Number *\:' | sed 's/ *Serial Number: *//'`
ISSUER=`echo "${SERVERCERT}" | egrep '^ *Issuer *\:' | sed 's/ *Issuer: *//'`
SUBJECT=`echo "${SERVERCERT}" | egrep '^ *Subject *\:' | sed 's/ *Subject: *//'`
VALIDITY_NOTBEFORE=`echo "${SERVERCERT}" | egrep '^ *Not Before *\:' | sed 's/ *Not Before: *//'`
VALIDITY_NOTAFTER=`echo "${SERVERCERT}" | egrep '^ *Not After *\:' | sed 's/ *Not After *: *//'`
SANS=`echo "${SERVERCERT}" | egrep -1 '^ *X509v3 Subject Alternative Name *\:' | tail -1 | sed 's/^ *//'`
AIA=`echo "${SERVERCERT}" |egrep ' *CA Issuers - URI *\: *http\://cdp1?.pca.dfn.de/'|sed 's/ *CA Issuers - URI://'`
AIAPEM=`echo "${AIA}" | sed 's/\.crt *$/\.pem/'`
HOST=`host "${SERVER}" | grep -v 'mail is handled by' | sed 's/^/        /'`
CHAIN=`echo ${AIA} | sed 's/http:\/\/cdp1/https:\/\/pki/' | sed 's/\/pub\/.*/\/cgi-bin\/pub\/pki?cmd=getStaticPage;name=index;id=2/'`

##################
# Abgelaufen?
echo "${SERVERCERT}" | openssl x509 -checkend 864000 -noout
if [ $? -eq 1 ] ; then
   EXPIRES=1
fi

echo "=========================================================="
echo "Informationen:"
echo "--------------"
echo "Server: ${SERVER}"
echo "${HOST}"
echo "Port: ${PORT}" 
if [ $SSL3 -eq 1 ] ; then
  echo "!!!!Not OK: SSLv3 wird noch unterstuetzt!"
else
  echo "SSLv3 ist abgeschaltet (gut!)"
fi
echo "Serverzertifikat:"
echo "  SubjectDN:    ${SUBJECT}"
echo "  Seriennummer: ${SERIAL}"
echo "  IssuerDN:     ${ISSUER}"
echo "  Gueltigkeit:   von ${VALIDITY_NOTBEFORE}"
echo "                bis ${VALIDITY_NOTAFTER}"
echo "  Alternative Namen:         ${SANS}"

echo ""
echo "=========================================================="

if [ -z "${AIA}" ] ; then
   echo
   echo "Kein Server-Zertifikat der DFN-PKI!"
   echo
   exit 1
fi

# Test auf das DFN-PCA-Zertifikat vom Februar 2014
# ^LWEV... ist die letzte Zeile des Base64-Codes des Zertifikats. Darin ist
# die Signatur enthalten, ein false positive ist so gut wie ausgeschlossen.
openssl s_client -connect "${SERVER}:${PORT}" -servername "${SERVER}" -showcerts </dev/null 2>&1 | grep -q "^LWEVuniWh7WSz+FQkZ5ZOhXsnlrGhvwoPma61Nk1r608SSKFh+5vjw==$"
if [ $? -eq 0 ] ; then
   FEB2014=1
fi;

# Test auf das DFN-PCA-Zertifikat vom Dezember 2006
# ^qAD... ist die letzte Zeile.
openssl s_client -connect "${SERVER}:${PORT}" -servername "${SERVER}" -showcerts </dev/null 2>&1 | grep -q "^qAD38hw=$"
if [ $? -eq 0 ] ; then
   DEZ2006=1
fi

# Test auf das DFN-PCA-Zertifikat vom Juli 2014
# ^fbV7pQ... ist die letzte Zeile.
openssl s_client -connect "${SERVER}:${PORT}" -servername "${SERVER}" -showcerts </dev/null 2>&1 | grep -q "^fbV7pQLxJMUkYxE0zFqTICp5iDolQpCpZTt8htMSFSMp/CzazDlbVBc=$"
if [ $? -eq 0 ] ; then
   JUL2014=1
fi

# Test auf neues DFN-Verein Certification Authority 2 Zertifikat
#
openssl s_client -connect "${SERVER}:${PORT}" -servername "${SERVER}" -showcerts </dev/null 2>&1 | grep -q "^GqK1chk5$"
if [ $? -eq 0 ] ; then
   FEB2016=1
fi

# Analyse des Ablaufdatums  des Serverzertifikats:
YEAR_NOTAFTER=`echo "$VALIDITY_NOTAFTER" | sed -e 's/.*\(....\) GMT/\1/'`

# Analyse des Signaturalgorithmus des Serverzertifikats:
openssl s_client -connect "${SERVER}:${PORT}" -servername "${SERVER}"  </dev/null 2>&1 | openssl x509 -text -noout | grep "Signature Algo" | head -1 | grep -q "sha1WithRSAEncryption"
if [ $? -eq 0 ] ; then
   SHA1SERVERCERT=1
fi

# Hole das im AIA des Server-Zertifikats referenzierte Issuing-CA-Zertifikat im DER Format
CACERT=$(${GET_PROGRAM} "${AIA}" 2>/dev/null | openssl x509  -inform der 2>/dev/null)

if [ -z "${CACERT}" ] ; then

   CACERT=$(${GET_PROGRAM} "${AIA}" 2>/dev/null | openssl x509  2>/dev/null)

   if [ -z "${CACERT}" ] ; then
      echo
      echo "Kann das CA-Zertifikat unter ${AIA} nicht per curl/wget herunterladen!"
      echo
      exit 1
   fi
fi

# Bestimmung des DFN-PKI-Sicherheitsniveaus des Issuing-CA-Zertifikats (G01 + G02):
echo "${CACERT}" | openssl x509 -text -noout | sed -e 's/ = /=/g' | egrep -q "^ *Issuer: *C=DE, O=DFN-Verein, OU=DFN-PKI, CN=DFN-Verein PCA Global - G01$"
if [ $? -eq 0 ]; then DFNPCA_G1=1; fi
echo "${CACERT}" | openssl x509 -text -noout | sed -e 's/ = /=/g' | egrep -q "^ *Issuer: C=DE, O=Verein zur Foerderung eines Deutschen Forschungsnetzes e. V., OU=DFN-PKI, CN=DFN-Verein Certification Authority 2$"
if [ $? -eq 0 ]; then DFNPCA_G2=1; fi

if [ $DFNPCA_G1 -eq 0 -a $DFNPCA_G2 -eq 0 ] ; then
   echo
   echo "Das Serverzertifikat ist nicht unter der DFN-PKI Global Hierarchie ausgestellt."
   echo "Es ist nichts zu tun, da das Serverzertifikat aus einer PKI-Hierarchie kommt,"
   echo "die nicht standardmaessig in Browser integriert ist."
   echo
   exit 1
fi



# Analyse des Signaturalgorithmus des Einrichtungs-CA-Zertifikats:
echo "${CACERT}" | openssl x509 -text -noout | grep "Signature Algo" | head -1 | grep -q "sha256WithRSAEncryption"
if [ $? -ne 0 ] ; then
   echo
   echo "Das unter dem AIA des Serverzertifikats ${AIA}"
   echo "referenzierte Issuing-CA-Zertifikat ist nicht mit SHA-256 signiert."
   echo "Bitte wenden Sie sich an die DFN-PCA dfnpca@dfn-cert.de"
   echo
   exit 1
fi

# Extrahiere ID-String des Issuing-CA-Zertifikats
CAID=`echo "${CACERT}" | grep -B1 -e '-----END CERTIFICATE-----' | head -1`

# Test auf das Issuing-CA-Zertifikat in der Kette
openssl s_client -connect "${SERVER}:${PORT}" -servername "${SERVER}" -showcerts </dev/null 2>&1 | grep -q "^${CAID}$"
if [ $? -eq 0 ] ; then
   CA=1
fi

echo "Pruefe das Issuing CA-Zertifikat:"
echo ""

if [ $CA -eq 0 -a $YEAR_NOTAFTER -gt 2015 ] ; then
   echo "    !!!!Not OK: ${SERVER}:${PORT} liefert kein SHA-2 signiertes Issuing-CA-Zertifikat mit der Zertifikatkette aus."
   echo ""
   RC=1
   CHAIN_HINWEIS_INSTALL=1
elif [ $CA -eq 0 -a $YEAR_NOTAFTER -lt 2016 ] ; then
   echo "    OK: ${SERVER}:${PORT} liefert noch kein SHA-2 signiertes Einrichtungs-CA-Zertifikat mit der Zertifikatkette aus."
   echo "        Allerdings laeuft das Serverzertifikat vor 2016 ab, so dass Google Chrome keine Warnmeldungen erzeugen wird."
   echo ""
else
   echo "    OK: ${SERVER}:${PORT} liefert das mit SHA-2 signierte Issuing-CA-Zertifikat aus." 
   echo ""
fi

echo "Pruefe das DFN-Verein PCA-Zertifikat:"
echo ""

if [ $FEB2014 -eq 1 ] ; then
   echo "    !!!!Not OK: ${SERVER}:${PORT} liefert das ungueltige PCA-Zertifikat vom Februar 2014 aus."
   echo ""
   RC=1
   CHAIN_HINWEIS_INSTALL=1
fi

if [ $DEZ2006 -eq 1 -a $YEAR_NOTAFTER -gt 2015 ] ; then
   echo "    !!!!Not OK: ${SERVER}:${PORT} liefert das mit SHA-1 signierte G01-PCA-Zertifikat von Dezember 2006 aus." 
   echo ""
   RC=1
   CHAIN_HINWEIS_INSTALL=1
elif  [ $DEZ2006 -eq 1 -a $YEAR_NOTAFTER -lt 2016 ] ; then
   echo "    OK: ${SERVER}:${PORT} liefert das mit SHA-1 signierte G01-PCA-Zertifikat von Dezember 2006 aus." 
   echo "        Allerdings laeuft das Serverzertifikat vor 2016 ab, so dass Google Chrome keine Warnmeldungen erzeugen wird."
   echo ""
fi;

if [ $JUL2014 -eq 1 ] ; then
   echo "    OK: ${SERVER}:${PORT} liefert das mit SHA-2 signierte G01-PCA-Zertifikat von Juli 2014 aus." 
   echo ""
fi;

if [ $FEB2016 -eq 1 ] ; then
   echo "    OK: ${SERVER}:${PORT} liefert das mit SHA-2 signierte G02-PCA-Zertifikat von Februar 2016 aus." 
   echo ""
fi;

NR=`expr $JUL2014 + $FEB2014 + $DEZ2006 + $FEB2016`
if [ $NR -gt 1 ] ; then
   echo "    !!!!Not OK: ${SERVER}:${PORT} liefert mehrere, widerspruechliche PCA-Zertifikate aus."
   echo ""
   CHAIN_HINWEIS_INSTALL=1
   RC=1
fi

if [ $NR -eq 0 ] ; then
   echo "    Not OK: ${SERVER}:${PORT} liefert kein PCA-Zertifikat aus."
   echo ""
   CHAIN_HINWEIS_INSTALL=1
   RC=1
fi

echo "Pruefe das Serverzertifikat:"
echo ""


if [ $SHA1SERVERCERT -eq 1 -a $YEAR_NOTAFTER -gt 2015 ] ; then
   echo "    !!!!Not OK: Das Serverzertifikat von ${SERVER}:${PORT} ist noch mit SHA-1 signiert,"
   echo "                und wird in Google Chrome zu Warnmeldungen fuehren."
   echo ""
   CERT_HINWEIS_REPLACE=1
   RC=1
elif [ $SHA1SERVERCERT -eq 1 -a $YEAR_NOTAFTER -lt 2016 ] ; then
   echo "    OK: Das Serverzertifikat von ${SERVER}:${PORT} ist noch mit SHA-1 signiert,"
   echo "        laeuft aber vor 2016 ab. Daher wird Google Chrome keine Warnmeldungen erzeugen."
   echo ""
else
   echo "    OK: Das Serverzertifikat von ${SERVER}:${PORT} ist mit SHA-2 signiert."
   echo ""
fi
if [ $EXPIRES -eq 1 ] ; then
  echo "!!!!Not OK: Das Zertifikat ist schon abgelaufen oder wird innerhalb der naechsten 10 Tage ablaufen!"
  echo ""
fi

echo "=========================================================="
echo "Ergebnisse:"

if [ $RC -eq 0 ] ; then
   echo
   if [ $YEAR_NOTAFTER -lt 2016 ] ; then
     echo "Kette OK: ${SERVER}:${PORT} hat ein Serverzertifikat, das vor 2016 ablaeuft. Es ist nichts weiter zu tun."
   else
     echo "Kette OK: ${SERVER}:${PORT} hat eine korrekte SHA-2 Konfiguration von Serverzertifikat und Zertifikatkette. Es ist nichts weiter zu tun."
   fi
   echo
else
   echo
   echo "${SERVER}:${PORT} hat keine korrekte SHA-2 Konfiguration von Serverzertifikat und Zertifikatkette."
   echo

   if [ $CHAIN_HINWEIS_INSTALL -eq 1 ] ; then
     echo "*Wichtig*: Bitte installieren bzw. ersetzen Sie im Server die neue SHA-2 Zertifikatkette."
     echo "           Die Zertifikatkette erhalten Sie ueber:"
     echo "           ${CHAIN}"
     echo ""
   fi  


   if [ $CERT_HINWEIS_REPLACE -eq 1 ] ; then
     echo "*Wichtig*: Bitte tauschen Sie das Serverzertifikat gegen ein neues mit SHA-2-Signatur aus."
     echo ""
   else
     echo "Das Serverzertifikat selbst muessen Sie *nicht* austauschen."
     echo ""
   fi  
fi

if [ $SSL3 -eq 1 ] ; then
  echo "!!!!Not OK: SSLv3 wird noch unterstuetzt!"
     echo ""
else
  echo "SSLv3 ist abgeschaltet (gut!)"
     echo ""
fi

if [ $EXPIRES -eq 1 ] ; then
  echo "!!!!Not OK: Das Zertifikat ist schon abgelaufen oder wird innerhalb der naechsten 10 Tage ablaufen!"
fi



exit $RC
