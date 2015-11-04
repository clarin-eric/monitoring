#!/bin/sh

temp_data_file_path="$(mktemp)"
tmp_details_file_path="$(mktemp)"
REFERER='https://clarin.fz-juelich.de/icinga/'

saved_traps=$(trap)
trap 'rm -vf "${temp_data_file_path}" ; $saved_traps' 'EXIT' 'INT' 'TERM' 'HUP'

##
## Private functions
##
_probe_curl_http_head() {
    # HTTP HEAD request.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional acceptable failure-indicating HTTP response code.
    # $4: Optional extra command-line parameter(s) for curl.
    _stdout_data=$(/usr/bin/curl --fail --head --location --output "${temp_data_file_path}" --referer "${REFERER}" --show-error --silent --stderr "${tmp_details_file_path}" --tlsv1.2 --verbose --write-out "@${2}/curl.format" $4 "${1}" ; ) ;
    curl_exit_status="$?" ;
    performance_data=$(printf '%s' "${_stdout_data}" | sed -n '1{p;q;}' ; )
    response_code=$(printf '%s' "${_stdout_data}" | sed -n '2{p;q;}' ; )
    details_data="$(cat "${tmp_details_file_path}" ; )" ;
    printf 'curl exit status: %d | %s\n%s %s\n\n' "${curl_exit_status}" "${performance_data}" "${details_data}" ;
    if [ -n "$3" ] && [ "${response_code}" = "$3" ]; then
        curl_exit_status='0' ;
    fi
    return "${curl_exit_status}" ;
}

_probe_curl_http_get() {
    # HTTP GET request.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Expected Internet media type of HTTP response (MIME/content type).
    # $4: Optional extra command-line parameter(s) for curl.
    performance_data_1=$(/usr/bin/curl --fail --header "Accept: ${3}" --location --output "${temp_data_file_path}" --referer "${REFERER}" --show-error --silent --stderr "${tmp_details_file_path}" --tlsv1.2 --verbose --write-out "@${2}/curl.format" $4 "${1}" ; ) ;
    curl_exit_status="$?" ;
    details_data=$(cat "${tmp_details_file_path}" ; ) ;
    printf 'curl exit status: %d | %s\n%s %s\n\n' "${curl_exit_status}" "${performance_data_1}" "${details_data}" ;
    return "${curl_exit_status}" ;
}

_probe_curl_ldap_bind() {
    # LDAP bind.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional extra command-line parameter(s) for curl.
    performance_data_1=$(/usr/bin/curl --fail --netrc --output "${temp_data_file_path}" --show-error --silent --stderr "${tmp_details_file_path}" --tlsv1 --verbose --write-out "@${2}/curl.format" $3 "${1}" ; ) ;
    curl_exit_status="$?" ;
    details_data=$(cat "${tmp_details_file_path}" ; ) ;
    printf 'curl exit status: %d | %s\n%s %s\n\n' "${curl_exit_status}" "${performance_data_1}" "${details_data}" ;
    return "${curl_exit_status}" ;
}

##
## Public data-validating functions
##

probe_imdi() {
    # HTTP GET request with IMDI response data validation.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional extra command-line parameter(s) for curl.
    _probe_curl_http_get "${1}" "${2}" 'application/xml' $3 &&
    xmllint --noout --schema "$2/IMDI/IMDI_3.0.xsd" "${temp_data_file_path}" 2>&1 ||
    # TODO: validate using correct schema "$2/IMDI/IMDI_3.0.xsd"
    return 2 ;
}

probe_handle_json() {
    # HTTP GET request with Handle JSON response data validation.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional extra command-line parameter(s) for curl.
    _probe_curl_http_get "${1}" "${2}" 'application/json' $3 &&
    python3 -I -c 'from json import load; from sys import stdin, exit; json_obj=load(stdin); exit(0 if json_obj["responseCode"] == 1 else 2)' <"${temp_data_file_path}" 2>&1 ||
    return 2 ;
}

probe_central_discovery_service_json() {
    # HTTP GET request with Handle JSON response data validation.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional extra command-line parameter(s) for curl.
    _probe_curl_http_get "${1}" "${2}" 'application/json' $3 &&
    python3 -I -c 'from json import load; from sys import stdin, exit; json_obj=load(stdin); previous_sum=962; current_sum=sum(country["count"] for country in json_obj["countries"]); exit(0 if new_sum >= old_sum else 2)' <"${temp_data_file_path}" 2>&1 ||
    return 2 ;
}

probe_sru_endpoint() {
    # HTTP GET request with SRU XML response data validation.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional extra command-line parameter(s) for curl.
    _probe_curl_http_get "${1}" "${2}" 'application/xml' $3 ||
    # TODO: validate using definite set of schemas --schema "$2/SRU.xsd"
    return 2 ;
}

probe_oai_pmh_endpoint() {
    # HTTP GET request with OAI-PMH XML response data validation.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional extra command-line parameter(s) for curl.
    _probe_curl_http_get "${1}?verb=Identify" "${2}" 'application/xml' $3 ;
    curl_exit_status="$?"
    if [ $curl_exit_status -eq 22 ]; then
        # Check for a probable 503 response that gives a Retry-After response header: we accept this as it is.
        _probe_curl_http_head "${1}?verb=Identify" "${2}" '503' $3 |
        grep -Eio 'Retry-After: [[:digit:]]+' 2>&1 ||
        return 2 ;
    else
        xmllint --noout --schema "$2/_OAI-PMH-all.xsd" "${temp_data_file_path}" 2>&1 ||
        return 2 ;
    fi
}

probe_json() {
    # HTTP GET request with JSON response data wellformedness check.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional extra command-line parameter(s) for curl.
    _probe_curl_http_get "${1}" "${2}" 'application/json' $3 &&
    python3 -I -m 'json.tool' <"${temp_data_file_path}" 1> '/dev/null' 2>&1 ||
    return 2 ;
}

probe_saml_metadata() {
    # HTTP GET request with SAML metadata XML response data validation.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional extra command-line parameter(s) for curl.
    _probe_curl_http_get "${1}" "${2}" 'application/xml' $3 &&
    # TODO: validate using SAML tools
    xmllint --noout "${temp_data_file_path}" 2>&1 ||
    return 2 ;
}

##
## Public functions (wrapped for Icinga)
##

probe_http_head() {
    # HTTP HEAD request.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional acceptable failure-indicating HTTP response code.
    # $4: Optional extra command-line parameter(s) for curl.
    _probe_curl_http_head "${1}" "${2}" "${3}" $4 ||
    return 2 ;
}

probe_http_get() {
    # HTTP GET request.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Expected Internet media type of HTTP response (MIME/content type).
    # $4: Optional extra command-line parameter(s) for curl.
    _probe_curl_http_get "${1}" "${2}" "${3}" $4 ||
    return 2 ;
}

probe_ldap_bind() {
    # LDAP bind.
    # $1: Full URL.
    # $2: Root directory path for curl.format and other data files.
    # $3: Optional extra command-line parameter(s) for curl.
    _probe_curl_ldap_bind "${1}" "${2}" $3 ||
    return 2 ;
}