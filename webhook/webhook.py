from hashlib import sha256
import ConfigParser
import json
import logging
import subprocess
import sys

from flask import Flask, request
from flask_api.decorators import set_parsers
from flask_api.parsers import URLEncodedParser

app = Flask(__name__)


def _calculate_hash(config):
    return sha256('{}/{}{}'.format(config['travis_user'],
                                   config['travis_repo'],
                                   config['travis_token']).hexdigest())


def _compare(token, auth_header):
    logging.debug('Using own compare function for authorization token')
    # not very performant, but posts are not very often
    # and this code is not used in new python versions.
    valid = True
    if len(token) != len(auth_header):
        return False
    for iterator, item in enumerate(token):
        if item != auth_header[iterator]:
            valid = False
    return valid


def _get_config():
    config = ConfigParser.SafeConfigParser()
    config.read('./config.ini')
    return dict(config.items(section='default'))


def _restart():
    return subprocess.call(config['command'], shell=True)


@app.route('/hook/', methods=['POST'])
@set_parsers(URLEncodedParser)
def post_hook():
    logging.debug('post')
    auth_header = request.headers.get('Authorization')
    if auth_header and compare_func(unicode(token), auth_header):
        content = json.loads(request.form['payload'])
        # do status = 0 (success) do something
        if not content['status']:
            logging.debug('Executing restart action')
            _restart()
        else:
            logging.debug('No successful build, not restarting Icinga')
        return "ok"
    else:
        return 'forbidden', 403


if __name__ == '__main__':
    config = _get_config()
    token = _calculate_hash(config)
    # hmac compare_digest only available since 2.7.7 and 3.3
    if (sys.version_info.major == 2 and sys.version_info.minor <= 7 and
                sys.version_info.micro < 7) or \
            (sys.version_info.major == 3 and sys.version_info.minor < 3):
        compare_func = _compare
    else:
        import hmac

        compare_func = hmac.compare_digest

    app.run(host='0.0.0.0', port=7010, debug=True)
