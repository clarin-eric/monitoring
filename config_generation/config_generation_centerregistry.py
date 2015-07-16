# coding=utf-8
import argparse
import ConfigParser
import datetime
import httplib2
import json
import logging
import os
import re

from git import Repo
from git.exc import GitCommandError
from git.util import rmtree
from pynag import Parsers, Model

GIT = True
FETCHED = False

REGISTRY = {
    'Centre': None,
    'Contact': None,
    'OAIPMHEndpoint': None,
    'FCSEndpoint': None, }

SERVICE_URL_MAPPER = {
    'CQL': 'FCSEndpoint',
    'OAI': 'OAIPMHEndpoint',
}


def _load_script_config(section='default'):
    """
    simply load a config file and save it as dict
    :param section:
    :return:
    """
    config = ConfigParser.SafeConfigParser()
    config.read('config.ini')
    return dict(config.items(section=section))


def _get_input_via_http(url, username='', password=''):
    """
    fetch some url
    :param url: string
    :param username: string
    :param password: string
    :return: the content
    """
    conn = httplib2.Http()
    conn.add_credentials(username, password)
    response, content = conn.request(url)
    if response.status == 200:
        logging.debug('was able to fetch ' + url)
        return content
    else:
        raise IOError('response status from {}:{}'.format(url,
                                                          response.status))


def _fetch_centerregistry(key):
    """
    fetch centerregistry, store content globally as dict
    :param key: string (containing the url endpoint)
    :return: boolean
    """
    if not REGISTRY[key]:
        http_header, content = httplib2.Http().request(
            'https://centres.clarin.eu/api/model/{}'.format(key))
        if http_header['status'] == '200':
            REGISTRY[key] = json.loads(content)
            return True
        return False


def _load_icinga_config(filepath):
    """
    load the icinga config into memory
    :return:
    """
    Model.cfg_file = filepath
    Model.pynag_directory = \
        filepath.replace('icinga.cfg', 'configuration/pynag')
    config = Parsers.Config(cfg_file=filepath)
    config.parse()


def _regexp_on_url(url):
    """
    Input: string ( urlusing the format protocol://host[:port]/url)
    Output: list withprotocol, host, port and url
    """
    filtered = re.search(r'^(.*)://([a-z0-9\-:.]+)?(.*)$', url)
    port = 80
    host = filtered.group(2)
    if ':' in filtered.group(2):
        host, port = filtered.group(2).split(':')
    elif filtered.group(1) == 'https':
        port = 443
    logging.debug('schema: {} host: {} url: {} port: {}'.format(
        filtered.group(1), host, filtered.group(3), str(port)))
    return [filtered.group(1), host, filtered.group(3), str(port)]


def _replace_umlauts(text):
    """
    because pynag is not able to write utf8 we have to take care of that
    :param text: string
    :return: string
    """
    umlauts = [(u'ü', u'ue'), (u'ä', u'ae'), (u'ö', u'oe'), (u'ß', u'ss')]
    for item in umlauts:
        text = text.replace(item[0], item[1])
    return text


def _load_git_repo(repourl, repopath):
    """
    load our repo from github or, if its there, get the updates.
    If there is a directory under repopath that is not a git repo, crash.
    :param repourl: string (external repo url)
    :param repopath: string (local path)
    :return: Repo (GitPython repo object)
    """
    try:
        repo = Repo.clone_from(repourl, repopath)
    except GitCommandError:
        logging.error('Repository already there')
        repo = Repo(repopath)
        github = repo.remote('origin')
        github.pull()
    return repo


def _push_and_delete_git_repo(repo, push=False):
    """
    add new files, commit, push and delete the local repo.
    :param repo: Repo (GitPython Repo object)
    :return:
    """
    if repo.is_dirty(untracked_files=True):
        files = repo.untracked_files
        files.append('*')
        repo.index.add(files)
        message = 'Information from CenterRegistry fetched and changed in ' \
                  'configuration: {}'.format(datetime.datetime.now())
        repo.index.commit(message)
        github = repo.remote('origin')
        if push:
            logging.info('Push to git repo at: {}'
                         .format(datetime.datetime.now()))
            github.push()
    else:
        logging.info('No changes, no commit at: {}'
                     .format(datetime.datetime.now()))
    rmtree(repo.working_dir)


def _create_centerregistry_services(host_name,
                                    site_contacts,
                                    centre_definition,
                                    service_type,
                                    filename):
    """

    :param host_name:
    :param site_contacts:
    :param centre_definition:
    :param service_type:
    :param filename:
    :return:
    """
    endpoints = list()
    for item in REGISTRY[SERVICE_URL_MAPPER[service_type]]:
        if item['fields']['centre'] == centre_definition['pk']:
            endpoints.append(item['fields']['uri'])
    endpoints.sort()
    for item in endpoints:
        probeargs = _regexp_on_url(item)
        service_description = '{}@{}@{}{}'.format(service_type,
                                                  host_name,
                                                  probeargs[1],
                                                  probeargs[2])
        check_command = 'check_{}!{}!{}!{}!{}'.format(service_type.lower(),
                                                      probeargs[0],
                                                      probeargs[1],
                                                      probeargs[2],
                                                      probeargs[3])
        services = Model.Service.objects.get_all()
        services = [item.get_shortname() for item in services]

        if '{}/{}'.format(host_name, service_description) in services:
            shortname = '{}/{}'.format(host_name, service_description)
        elif '{}'.format(service_description) in services:
            shortname = '{}'.format(service_description)
        else:
            shortname = None

        if shortname:
            action = 'Modifying'
            config_service = Model.Service.objects.get_by_shortname(shortname)
            config_service = _move_objekt_to_siteconfig(config_service,
                                                        filename)
            config_service.set_attribute('check_command', check_command)
            config_service.set_attribute('contacts', site_contacts)
            config_service.set_attribute('host_name', host_name)
        else:
            action = 'Adding'
            config_service = Model.Service(
                service_description=service_description,
                check_command=check_command,
                use='custom-active-service,srv-pnp',
                host_name=host_name,
                servicegroups=host_name + '_centerregistry',
                contacts=site_contacts,
                filename=filename)
        logging.debug('%s service: %s on host: %s',
                      action,
                      service_description,
                      host_name)
        config_service.save()


def _manage_creg_icinga_contacts():
    """
    we have contacts with email/eppn from creg and we have already
    stored contacts in icinga. merge them
    :rtype : dict
    """
    # contacts we got from creg
    tmp_contact_list = dict()
    for contact in REGISTRY['Contact']:
        name = contact['fields']['edupersonprincipalname'] \
            if contact['fields']['edupersonprincipalname'] else \
            contact['fields']['email_address']
        tmp_contact_list[contact['pk']] = {
            'name': name,
            'email': contact['fields']['email_address']}
    contacts = tmp_contact_list

    # which contacts are available in icinga?
    available_contacts = dict()
    for contact in Model.Contact.objects.all:
        # only modify registered contacts, unregistered contacts are templates.
        if str(contact.get_attribute('register')) != '0':
            available_contacts[contact.get_attribute('contact_name')] = \
                {'name': contact.get_attribute('contact_name'),
                 'email': contact.get_attribute('email')}
    contacts['dummy'] = available_contacts['dummy']

    # store contacts available in icinga to corresponding centerregistry one
    for contact in contacts.keys():
        if contacts[contact]['name'] in available_contacts.keys():
            contacts[contact]['name_icinga'] = \
                available_contacts[contacts[contact]['name']]['name']
        else:
            contacts[contact]['name_icinga'] = False
    logging.debug("Contacts from creg, with local representation: %s",
                  contacts)
    return contacts

def _extract_contact(contact_id, contacts, icinga_contacts):
    from os import getcwd

    contact_name = icinga_contacts[contact_id]['name_icinga']

    if contact_name:
        # Contact is already in Icinga.
        config_contact = \
            Model.Contact.objects.get_by_shortname(contact_name)
        config_contact.set_attribute('email', contacts[contact]['email'])
    else:
        # Contact not in Icinga: add him/her.
        contact_name = contacts[contact_id]['name']
        icinga_contacts[contact_id]['name_icinga'] = contact_name
        config_contact = \
            Model.Contact(contact_name=contact_name,
                          use='generic-contact',
                          email=contacts[contact]['email'],
                          filename='{cwd:s}/configuration/configuration/pynag/'
                                   'contacts.cfg'.format(cwd=getcwd()))
    config_contact.save()
    contacts.append(contact_name)

    return contacts


def _get_site_contacts_list(centre, icinga_contacts):
    """
    Extract all contacts from the Centre Registry that should be notified about a given centre's services.
    If we do not have them in Icinga already, add them.

    :param centre: dict
    :param icinga_contacts: dict (already in Icinga)
    :return: string (containing concatenated contacts)
    """
    contacts = list()
    for contact_id in centre['fields']['monitoring_contacts']:
        contact_list = _extract_contact(contact_id=contact_id,
                                        contacts=contacts,
                                        icinga_contacts=icinga_contacts)

    tech_contact_id = centre['fields']['technical_contact']
    contacts = _extract_contact(contact_id=tech_contact_id,
                                contacts=contacts,
                                icinga_contacts=icinga_contacts)

    site_contacts = ','.join(contacts).encode('latin-1')
    return site_contacts or icinga_contacts['dummy']['name']


def _move_objekt_to_siteconfig(nagios_object, filename):
    """

    :param nagios_object:
    :param filename:
    :return:
    """
    if nagios_object.get_filename() != filename:
        tmp = nagios_object.move(filename)
        # this if else is due to a bug in pynag move command
        if type(tmp) is list:
            return tmp[0]
        else:
            return tmp
    else:
        return nagios_object


def _create_config_from_centerregistry():
    """

    :return:
    """
    _load_icinga_config('configuration/icinga.cfg')
    if _fetch_centerregistry('Centre') and _fetch_centerregistry('Contact'):
        oai_success = _fetch_centerregistry('OAIPMHEndpoint')
        cql_success = _fetch_centerregistry('FCSEndpoint')
        contacts = _manage_creg_icinga_contacts()

        check_command = 'check_dummy'
        use = 'custom-active-host'
        for iterator, centre in enumerate(REGISTRY['Centre']):
            host_name = \
                str(_replace_umlauts(centre['fields']['shorthand'].strip()))
            filename = \
                '{}/configuration/configuration/{}.cfg'.format(os.getcwd(),
                                                               host_name)
            _LAT = str(centre['fields']['latitude'].strip())
            _LONG = str(centre['fields']['longitude'].strip())
            display_name = \
                str(_replace_umlauts(centre['fields']['name'].strip()))
            try:
                config_host = Model.Host.objects.get_by_shortname(host_name)
                config_host = _move_objekt_to_siteconfig(config_host, filename)
                action = 'Modifying'
            except KeyError:
                action = 'Adding'
                config_host = Model.Host(host_name=host_name,
                                         filename=filename)
            logging.debug('%s host: %s', action, host_name)
            config_host.set_attribute('_LAT', _LAT)
            config_host.set_attribute('_LONG', _LONG)
            config_host.set_attribute('check_command', check_command)
            config_host.set_attribute('display_name', display_name)
            config_host.set_attribute('use', use)

            site_contacts = _get_site_contacts_list(centre=centre,
                                                    icinga_contacts=contacts)
            config_host.set_attribute('contacts', site_contacts)
            config_host.save()

            # create servicegroup for site and for Centre Registry services per
            for item in ['', '_centerregistry']:
                try:
                    config_servicegroup = \
                        Model.Servicegroup.objects.get_by_shortname(
                            host_name + item)
                    config_servicegroup = \
                        _move_objekt_to_siteconfig(
                            config_servicegroup, filename)
                except KeyError:
                    logging.debug('Adding new Servicegroup: %s',
                                  host_name + item)
                    config_servicegroup = Model.Servicegroup(
                        servicegroup_name=host_name + item,
                        alias=host_name + item,
                        filename=filename)
                config_servicegroup.save()
            # OAI
            if oai_success:
                _create_centerregistry_services(host_name=host_name,
                                                site_contacts=site_contacts,
                                                centre_definition=centre,
                                                service_type='OAI',
                                                filename=filename)

            # CQL
            if cql_success:
                _create_centerregistry_services(host_name=host_name,
                                                site_contacts=site_contacts,
                                                centre_definition=centre,
                                                service_type='CQL',
                                                filename=filename)


def run(push=False):
    """
    get repository, modify config, push repo
    :return:
    """
    repo = _load_git_repo('git@github.com:clarin-eric/monitoring.git',
                          'configuration')
    _create_config_from_centerregistry()
    _push_and_delete_git_repo(repo=repo, push=push)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug",
                        help="get debug output",
                        action="store_true")
    parser.add_argument("--logstash",
                        help="log everything (in addition) to logstash "
                             ", give host:port")
    parser.add_argument("--push",
                        help="push repo to GitHub",
                        action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(format='%(message)s', level=logging.DEBUG)
    else:
        logging.basicConfig(format='%(message)s', level=logging.INFO)

    push = args.push

    if args.logstash:
        logger = logging.getLogger()
        import logstash
        host, port = args.logstash.split(':')
        logger.addHandler(logstash.TCPLogstashHandler(host=host,
                                                      port=int(port),
                                                      version=1))
    run(push=push)
