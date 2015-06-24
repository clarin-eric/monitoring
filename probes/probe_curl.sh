#!/bin/sh

tmp_file_path="$(mktemp)"
REFERER='https://clarin.fz-juelich.de/icinga/'

saved_traps=$(trap)
trap 'rm -vf "${tmp_file_path}" ; $saved_traps' 'EXIT' 'INT' 'TERM' 'HUP'

probe_curl_head() {
    # HTTP HEAD request.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional extra command-line parameter(s) for curl.
    /usr/bin/curl --fail --head --location --referer "${REFERER}" --show-error --silent --stderr - --tlsv1.2 --verbose --write-out "@${2}/curl.format" "${1}" $3 ||
    return "$?" ;
}

probe_curl_get() {
    # HTTP GET request.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Expected Internet media type of HTTP response (MIME/content type).
    # $4: Optional extra command-line parameter(s) for curl.
    /usr/bin/curl --fail --header "Accept: ${3}" --location --output "${tmp_file_path}" --referer "${REFERER}" --show-error --silent --stderr - --tlsv1.2 --verbose --write-out "@${2}/curl.format" "${1}" $4 &&
    return "$?" ;
}

probe_curl_ldap() {
    /usr/bin/curl --fail --netrc --show-error --silent --stderr - --verbose --write-out "@${2}/curl.format" "${1}" $2 ||
    return "$?" ;
}

probe_curl_imdi() {
    # HTTP GET request with IMDI response data validation.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional extra command-line parameter(s) for curl.
    probe_curl_get "${1}" "${2}" 'application/xml' $3 &&
    xmllint --noout <"${tmp_file_path}" 2>&1 || # TODO: validate using correct schema "$2/IMDI/IMDI_3.0.xsd"
    return "$?" ;
}

probe_curl_handle_json() {
    # HTTP GET request with Handle JSON response data validation.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional extra command-line parameter(s) for curl.
    probe_curl_get "${1}" "${2}" 'application/xml' $3 &&
    python3 -I -c 'from json import load; from sys import stdin, exit; json_obj=load(stdin); exit(0 if json_obj["responseCode"] == 1 else 2)' <"${tmp_file_path}" 2>&1 ||
    return "$?" ;
}

probe_sru_endpoint() {
    # HTTP GET request with SRU XML response data validation.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional extra command-line parameter(s) for curl.
    probe_curl_get "${1}" "${2}" 'application/xml' $3 &&
    # TODO: validate using definite set of schemas --schema "$2/SRU.xsd"
    xmllint --noout "${tmp_file_path}" ||
    return "$?" ;
}

probe_oai_pmh_endpoint() {
    # HTTP GET request with OAI-PMH XML response data validation.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional extra command-line parameter(s) for curl.
    probe_curl_get "${1}?verb=Identify" "${2}" 'application/xml' $3 &&
    xmllint --noout --schema "$2/_OAI-PMH-all.xsd" "${tmp_file_path}" 2>&1 ||
    probe_curl_head "${1}" "${2}" $3 |
    grep -Eio 'Retry-After: [[:digit:]]+' 2>&1 ||
    return "$?" ;
}

probe_json() {
    # HTTP GET request with JSON response data wellformedness check.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional extra command-line parameter(s) for curl.
    probe_curl_get "${1}" "${2}" 'application/json' $3 &&
    python3 -I -m 'json.tool' <"${tmp_file_path}" 1> '/dev/null' 2>&1 ||
    return "$?" ;
}

probe_saml_metadata() {
    # HTTP GET request with SAML metadata XML response data validation.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional extra command-line parameter(s) for curl.
    probe_curl_get "${1}" "${2}" 'application/xml' $3 &&
    # TODO: validate using SAML tools
    xmllint --noout - 1> '/dev/null' "${tmp_file_path}" 2>&1 ||
    return "$?" ;
}