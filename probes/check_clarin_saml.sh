#!/bin/sh

clean_up() {
  rm -f "{$XML_file}" ; 
  rm -f "{$signing_certificate_file}"
}

# TODO: this scripts needs to be fixed and integrated in probe_curl.sh

XML_file="$(mktemp --suffix='check_clarin__saml_XML_file')" && 
signing_certificate_file="$(mktemp --suffix='check_clarin_saml__signing_certificate')" && 
curl --tlsv1 -f -L -s -v -o "${signing_certificate_file}" 'https://www.clarin.eu/sites/default/files/SPF_signing_pub_1.crt' 1>&2 && 
curl --tlsv1.2 -f -L -s -v -o "${XML_file}" -w "@${2}/curl.format" "https://$1/aai/prod_md_about_spf_sps.xml" 1>&2 && 
sh 'xmlsectool.sh' --inFile "${XML_file}" --validateSchema --schemaDirectory 'saml-schema/' --verifySignature --certificate "${signing_certificate_file}" 1>&2 || exit 2

trap 'clean_up' EXIT
