#!/bin/sh

tmp_file_path="$(mktemp)"

probe_curl_head() {
    /usr/bin/curl -I -o "${tmp_file_path}" --tlsv1.2 -e 'https://clarin.fz-juelich.de/icinga/' -f -L -S -s -v -w "@${2}/curl.format" "${1}" ||
    return "$?" ;
}

probe_curl_get() {
    /usr/bin/curl -o "${tmp_file_path}" --tlsv1.2 -e 'https://clarin.fz-juelich.de/icinga/' -f -L -S -s -v -w "@${2}/curl.format" -H "Accept: ${3}" "${1}" 1>&2 &&
    cat "${tmp_file_path}" ||
    return "$?" ;
}

probe_curl_ldap() {
    /usr/bin/curl -v -n -f "${1}" ||
    return "$?" ;
}

probe_sru_endpoint() {
    probe_curl_get "${1}" "${2}" 'application/xml' |
    xmllint --noout - || # TODO: validate using definite set of schemas --schema "$2/SRU.xsd"
    return "$?" ;
}

probe_oai_pmh_endpoint() {
    { probe_curl_get "${1}" "${2}" 'application/xml' |
    xmllint --noout --schema "$2/OAI-PMH/OAI-PMH.xsd" - ; } ||
    probe_curl_head "${1}" |
    grep -Eio 'Retry-After: [[:digit:]]+' ||
    return "$?" ;
}

probe_json() {
    probe_curl_get "${1}" "${2}" 'application/json' |
    python -I -m json.tool 1> /dev/null 2>&1
    return "$?" ;
}

probe_saml_metadata() {
    probe_curl_get "${1}" "${2}" 'application/xml' |
    xmllint --noout - 1> /dev/null # TODO: validate using SAML tools
    return "$?" ;
}

trap 'rm -vf "${tmp_file_path}"' 'EXIT' 'INT' 'TERM' 'HUP'