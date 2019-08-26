#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import logging
import os
import re
import requests

from git import Repo
from git.exc import GitCommandError
from os import getcwd
from urllib.parse import urlparse

REGISTRY = {}

SERVICE_URL_MAPPER = {
    'CQL': 'FCSEndpoint',
    'OAI': 'OAIPMHEndpoint'
}


class Config:
    def __init__(self, name, **kwargs):
        self.__dict__['config_names'] = {'_import', 'name', 'vars'}
        self.__dict__['_values'] = {'name': name, 'vars': {}}
        self.name = name
        for k, v in kwargs.items():
            self[k] = v

    def __eq__(self, other):
        if sorted(self.keys()) != sorted(other.keys()):
            return False
        for k in self.keys():
            if self[k] != other[k]:
                return False
        return True

    def __delattr__(self, key):
        if key in self.config_names:
            del self.__dict__['_values'][key]
        else:
            del self.__dict__['_values']['vars'][key]

    def __getattr__(self, key):
        if key == '__name__':
            return self.__class__.__name__
        else:
            if key in self.config_names:
                return self.__dict__['_values'][key]
            else:
                return self.__dict__['_values']['vars'][key]

    def __setattr__(self, key, val):
        if key in self.config_names:
            self.__dict__['_values'][key] = val
        else:
            self.__dict__['_values']['vars'][key] = val

    def __delitem__(self, key):
        if key in self.config_names:
            del self.__dict__['_values'][key]
        else:
            del self.__dict__['_values']['vars'][key]

    def __getitem__(self, key):
        if key in self.config_names:
            return self._values[key]
        else:
            return self._values['vars'][key]

    def __setitem__(self, key, val):
        if key in self.config_names:
            self._values[key] = val
        else:
            self._values['vars'][key] = val

    def __str__(self):
        def escape(v, k=None):
            if type(v) == str:
                return f'{k} = "{v}"' if k is not None else f'"{v}"'
            elif type(v) == int or type(v) == float:
                return f'{k} = {v}' if k is not None else f'{v}'
            elif type(v) == bool:
                v = 'true' if v else 'false'
                return f'{k} = {v}' if k is not None else f'{v}'
            elif type(v) == list or type(v) == tuple:
                if k is not None:
                    return f'{k} = [{", ".join(escape(i) for i in v)}]'
                else:
                    return f'[{", ".join(escape(i) for i in v)}]'
            else:
                return f'{k} = "{v}"' if k is not None else f'{v}'

        s = f'object {self.__name__} "{self.name}" {{\n'
        if '_import' in self.keys():
            s += f'    import "{self._import}"\n'

        for k, v in self.flatten():
            if k in ['name', '_import']:
                continue

            if type(v) == dict:
                is_complex = [True if type(v2) == dict else False
                              for k2, v2 in v.items()]

                if True in is_complex:
                    for k2, v2 in v.items():
                        s += f'    {k}[{escape(k2)}] = {{\n'
                        for k3, v3 in v2.items():
                            s += f'        {escape(v3, k3)}\n'
                        s += '    }\n'
                else:
                    s += f'    {k} = {{\n'
                    for k2, v2 in v.items():
                        s += f'        {escape(v2, k2)}\n'
                    s += '    }\n'
            elif v is not None:
                s += f'    {escape(v, k)}\n'
        s += '}'
        return s

    def items(self):
        return self.__dict__['_values'].items()

    def keys(self):
        return self.__dict__['_values'].keys()

    def flatten(self):
        for k, v in self.items():
            if k == 'vars':
                for k2, v2 in v.items():
                    yield f'{k}.{k2}', v2
            else:
                yield k, v

    @classmethod
    def from_str(cls, s):
        def unescape(v):
            if v == 'true':
                return True
            elif v == 'false':
                return False
            elif re.fullmatch(r'[0-9]+', v):
                return int(v)
            elif re.fullmatch(r'[0-9]+\.[0-9]+', v):
                return float(v)
            elif v.startswith('"') and v.endswith('"'):
                return v[1:-1]
            else:
                return v

        dict_list_key_pattern = r'(vars\.)?([^\[\s]+)\[([^\]]+)\]'
        import_pattern = r'\s*?import\s*?"([^"]+)"'
        vars_pattern = r'\s*?(vars\.)?([^\s=]+)\s*?=\s*(.+)$'

        name = None
        check_command = None
        values = {}
        state = 0
        pkey = None
        for line in s.split('\n'):
            if state == 0 and line.startswith(f'object {cls.__name__} '):
                match = re.search(rf'object\s{cls.__name__}\s*?"(?P<name>[^"]+)"', line)
                if match:
                    name = match.group('name')
                    state = 1
            elif state == 1:
                if re.match(import_pattern, line):
                    values['_import'] = re.match(import_pattern, line).group(1)
                elif re.match(vars_pattern, line):
                    match = re.match(vars_pattern, line)
                    k = match.group(2)
                    v = match.group(3)

                    if k == 'check_command':
                        check_command = unescape(v)
                    elif v.startswith('[') and v.endswith(']'):
                        values[k] = []
                        for s in v[1:-1].split(','):
                            values[k].append(unescape(s.strip()))
                    elif re.match(dict_list_key_pattern, k) and v == '{':
                        m = re.match(dict_list_key_pattern, k)
                        k1 = unescape(m.group(2))
                        k2 = unescape(m.group(3))

                        if k1 not in values:
                            values[k1] = {k2: {}}
                        else:
                            values[k1][k2] ={}
                        pkey = (k1, k2)
                        state = 3
                    elif v == '{':
                        values[k] = {}
                        pkey = k
                        state = 2
                    else:
                        values[k] = unescape(v)
            elif state == 2:
                if re.match(r'\s*?\}', line):
                    state = 1
                    pkey = None
                else:
                    match = re.match(vars_pattern, line)
                    k = match.group(2)
                    v = match.group(3)

                    if v.startswith('[') and v.endswith(']'):
                        values[pkey][k] = []
                        for s in v[1:-1].split(','):
                            values[pkey][k].append(unescape(s.strip()))
                    else:
                        values[pkey][k] = unescape(v)
            elif state == 3:
                if re.match(r'\s*?\}', line):
                    state = 1
                    pkey = None
                else:
                    match = re.match(vars_pattern, line)
                    k = match.group(2)
                    v = match.group(3)

                    if v.startswith('[') and v.endswith(']'):
                        values[pkey[0]][pkey[1]][k] = []
                        for s in v[1:-1].split(','):
                            values[pkey[0]][pkey[1]][k].append(unescape(s.strip()))
                    else:
                        values[pkey[0]][pkey[1]][k] = unescape(v)
        return cls(name, check_command, **values)

    @classmethod
    def load(cls, path):
        cfg = ''
        with open(path, 'r', encoding='utf8') as f:
            brackets = 0
            for line in f.readlines():
                if line.startswith(f'object {cls.__name__} '):
                    cfg = line
                    brackets = 1
                elif cfg.startswith(f'object {cls.__name__} '):
                    cfg += line
                    brackets += line.count('{')
                    brackets -= line.count('}')

                if brackets == 0 and cfg != '' and '{' in cfg and '}' in cfg:
                    break

        return cls.from_str(cfg.strip())

    def save(self, base_path, *args):
        path = os.path.join(base_path, f'{self.name}.conf')
        with open(path, 'w', encoding='utf8') as f:
            f.write(f'{self}\n')

            for arg in args:
                f.write(f'\n{arg}\n')


class Host(Config):
    def __init__(self, name, check_command, **kwargs):
        super(Host, self).__init__(name)
        self.config_names.update(['display_name', 'address', 'address6',
                                 'groups', 'vars', 'check_command',
                                 'max_check_attempts', 'check_period',
                                 'check_timeout', 'check_interval',
                                 'retry_interval', 'enable_notifications',
                                 'enable_active_checks',
                                 'enable_passive_checks',
                                 'enable_event_handler', 'enable_flapping',
                                 'enable_perfdata', 'event_command',
                                 'flapping_threshold_high',
                                 'flapping_threshold_low', 'volatile', 'zone',
                                 'command_endpoint', 'notes', 'notes_url',
                                 'action_url', 'icon_image', 'icon_image_alt'])
        self.check_command = check_command
        for k, v in kwargs.items():
            self[k] = v


class HostGroup(Config):
    def __init__(self, name, **kwargs):
        super(HostGroup, self).__init__(name)
        self.config_names.update(['display_name','groups'])
        for k, v in kwargs.items():
            self[k] = v


class User(Config):
    def __init__(self, name, **kwargs):
        super(User, self).__init__(name)
        self.config_names.update(['display_name', 'email', 'pager', 'vars',
                                  'groups', 'enable_notifications', 'period',
                                  'types', 'states'])
        for k, v in kwargs.items():
            self[k] = v


class UserGroup(Config):
    def __init__(self, name, **kwargs):
        super(UserGroup, self).__init__(name)
        self.config_names.update(['display_name','groups'])
        for k, v in kwargs.items():
            self[k] = v

#         object Host "icinga2-client1.localdomain" {
#   display_name = "Linux Client 1"
#   address = "192.168.56.111"
#   address6 = "2a00:1450:4001:815::2003"

#   groups = [ "linux-servers" ]display_name

#   check_command = "hostalive"
# }

def _fetch_centre_registry(key):
    """
    Fetch data from Centre Registry, store it globally as dict.

    :param key: string (containing the url endpoint)
    :return: boolean
    """
    r = requests.get(f'https://centres.clarin.eu/api/model/{key:s}')
    if r.status_code == 200:
        REGISTRY[key] = r.json()
        return True
    else:
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


def parse_url(url):
    parsed_url = urlparse(url)
    components = parsed_url.netloc.split(':')

    http_address = components[0]
    http_uri = parsed_url.path + parsed_url.params + parsed_url.query + \
        parsed_url.fragment
    if http_uri == '':
        http_uri = '/'
    http_ssl = parsed_url.scheme == 'https'

    return http_address, http_uri, http_ssl


def transliterate_to_ascii(text):
    """
    Helper function to transliterate UTF-8 to ASCII.

    :param text: string
    :return: string
    """
    from subprocess import Popen, PIPE

    process = Popen(['iconv', '-f', 'utf-8', '-t' 'ascii//TRANSLIT'],
                    stdout=PIPE, stdin=PIPE)
    stdoutdata, _ = process.communicate(text.encode('utf-8'))

    return stdoutdata.decode(encoding='utf-8')


def _load_git_repo(repourl, repopath, pull_repo=True):
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
        if pull_repo:
            github = repo.remote('origin')
            github.pull()
    return repo


def _push_and_delete_git_repo(repo,
                              push_repo=False,
                              dont_remove_repo=False):
    """
    add new files, commit, push and delete the local repo.
    :param repo: Repo (GitPython Repo object)
    :return:
    """
    from datetime import datetime
    from os import unlink
    from os.path import islink
    from shutil import rmtree

    if repo.is_dirty(untracked_files=True):
        files = repo.untracked_files
        files.append('*')
        repo.index.add(files)
        message = 'Information from Centre Registry fetched and changed in ' \
                  'configuration: {}'.format(datetime.now())
        repo.index.commit(message)
        github = repo.remote('origin')
        if push_repo:
            logging.info('Push to git repo at: {}'
                         .format(datetime.now()))
            github.push()
    else:
        logging.info('No changes, no commit at: {}'
                     .format(datetime.now()))
    if not dont_remove_repo:
        if islink(repo.working_dir):
            unlink(repo.working_dir)
        else:
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
    # find all service_type services for a centre, based on centre registry
    endpoints = list()
    for item in REGISTRY[SERVICE_URL_MAPPER[service_type]]:
        if item['fields']['centre'] == centre_definition['pk']:
            endpoints.append(item['fields']['uri'])
    endpoints.sort()

    # find all service_type service for a centre, based on icinga
    services = Model.Service.objects.get_all()
    services = [item.get_shortname() for item in services]
    site_services = set()
    for service in services:
        if service and host_name in service and service_type in service:
            site_services.add(service)
    logging.debug('ALL site services {}'.format(site_services))

    # go through services and add/modify them
    for item in endpoints:
        probeargs = _parse_url(item)
        service_description = '{}@{}@{}{}'.format(service_type,
                                                  host_name,
                                                  probeargs[1],
                                                  probeargs[2])
        check_command = 'check_{}!{}!{}!{}!{}'.format(service_type.lower(),
                                                      probeargs[0],
                                                      probeargs[1],
                                                      probeargs[2],
                                                      probeargs[3])

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
            site_services.discard(shortname)

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
            site_services.discard('{}/{}'.format(host_name,
                                                 service_description))
        logging.debug('%s service: %s on host: %s',
                      action,
                      service_description,
                      host_name)
        config_service.save()

    # delete old services for a site
    for service in site_services:
        logging.info('Removing obsolete service: %s from host: %s',
                     service,
                     host_name)
        config_service = Model.Service.objects.get_by_shortname(service)
        config_service.delete()


def merge_centerregistry_icinga_users():
    """
    We have contacts with e-mail address/ePPN from Centre Registry and we
    have already stored contacts in Icinga. Merge them.
    :rtype : dict
    """
    # contacts from Centre Registry
    users = {}
    for contact in REGISTRY['Contact']:
        name = contact['fields']['name']
        eppn = contact['fields']['edupersonprincipalname']

        if name is not None and name.strip():
            name = name.strip()
        elif eppn is not None and eppn.strip():
            name = eppn.strip()
        else:
            name = contact['fields']['email_address'].strip()
        email = contact['fields']['email_address'].strip()

        telephone_number = contact['fields']['telephone_number'].strip()
        if telephone_number == '':
            telephone_number = None
        website_url = contact['fields']['website_url'].strip()
        if website_url == '':
            website_url = None

        users[contact['pk']] = User(name=contact['pk'], display_name=name,
                                    email=email, period='24x7',
                                    telephone_number=telephone_number,
                                    website_url=website_url, groups=[])
        # print(users[contact['pk']])



    # Which contacts are available in Icinga?
    icinga_contacts = {}
    # for contact in Model.Contact.objects.all:
    #     # Only modify registered contacts, unregistered contacts are templates.
    #     if str(contact.get_attribute('register')) != '0':
    #         contact_name = (contact.get_attribute('contact_name')).strip()
    #         if contact_name is not None and contact_name.strip():
    #             icinga_contacts[contact_name] = \
    #                 {'name': contact_name,
    #                  'email': contact.get_attribute('email')}

    # Store contacts available in Icinga to corresponding Centre Registry ones
    # # contacts['dummy'] = icinga_contacts['dummy']
    # for contact in list(users.keys()):
    #     if users[contact]['name'] in list(icinga_contacts.keys()):
    #         users[contact]['name_icinga'] = \
    #             icinga_contacts[users[contact]['name']]['name']
    #     else:
    #         users[contact]['name_icinga'] = False
    logging.debug("Contacts from creg, with local representation: %s",
                  users)
    return users


def _extract_contact(contact_id, icinga_contacts):
    contact_name = icinga_contacts[contact_id]['name_icinga']

    if contact_name:
        # Contact is already in Icinga.
        config_contact = \
            Model.Contact.objects.get_by_shortname(contact_name)
        config_contact.set_attribute('email',
                                     icinga_contacts[contact_id]['email'])
    else:
        # Contact not in Icinga: add him/her.
        contact_name = icinga_contacts[contact_id]['name']
        icinga_contacts[contact_id]['name_icinga'] = contact_name
    #     config_contact = \
    #         Model.Contact(contact_name=contact_name,
    #                       use='generic-contact',
    #                       email=icinga_contacts[contact_id]['email'],
    #                       filename='{cwd:s}/configuration/configuration/pynag/'
    #                                'contacts.cfg'.format(cwd=getcwd()))
    # config_contact.save()
    return contact_name


def get_site_usergroup(centre, users):
    """
    Extract all contacts from the Centre Registry that should be notified about
    a given centre's services. If we do not have them in Icinga already, add em

    :param centre: dict
    :param icinga_contacts: dict (already in Icinga)
    :return: string (containing concatenated contacts)
    """
    name = transliterate_to_ascii(centre['fields']['shorthand'].strip())
    display_name = transliterate_to_ascii(centre['fields']['name'].strip())
    group = UserGroup(name=f'{name}_group',
                      display_name=f'{display_name} User Group')

    for contact_id in centre['fields']['monitoring_contacts']:
        users[contact_id].groups.append(group.name)
        # print(users[contact_id])
        # contacts.append(_extract_contact(contact_id=contact_id,
        #                                  icinga_contacts=icinga_contacts))

    tech_contact_id = centre['fields']['technical_contact']
    users[tech_contact_id].groups.append(group.name)
    # print(users[tech_contact_id])
    # contacts.append(_extract_contact(contact_id=tech_contact_id,
    #                                  icinga_contacts=icinga_contacts))
    # print(group)
    return group


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


def create_config_from_centerregistry():
    """

    :return:
    """
    # _load_icinga_config('configuration/icinga.cfg')
    user_groups = []
    if _fetch_centre_registry('Centre') and _fetch_centre_registry('Contact'):
        oai_success = _fetch_centre_registry('OAIPMHEndpoint')
        cql_success = _fetch_centre_registry('FCSEndpoint')
        users = merge_centerregistry_icinga_users()

        for i, centre in enumerate(REGISTRY['Centre']):
            print(centre)

            user_groups.append(get_site_usergroup(centre, users))

            name = transliterate_to_ascii(centre['fields']['shorthand'].strip())
            display_name = centre['fields']['name'].strip()

            host_group = HostGroup(name=name, display_name=display_name)

            http_address, http_uri, http_ssl = parse_url(
                centre['fields']['website_url'].strip())

            location = {
                'latitude': float(centre['fields']['latitude'].strip()),
                'longitude': float(centre['fields']['longitude'].strip())
            }
            host = Host(name=name, display_name=display_name,
                        _import='clarin-generic-host', check_command=None,
                        location=location, http_address=http_address,
                        http_uri=http_uri, http_ssl=http_ssl,
                        groups=[host_group.name], ssl_certs=set())
            if http_ssl:
                host.ssl_certs.add(http_address)

            # OAI
            if oai_success:
                host.oaipmh_endpoints = {}
                for item in REGISTRY['OAIPMHEndpoint']:
                    if item['fields']['centre'] == centre['pk']:
                        host.oaipmh_endpoints[item['pk']] = {
                            'oaipmh_endpoint': item['fields']['uri'],
                            'oaipmh_metadata_format': item['fields']['metadata_format'],
                            'oaipmh_web_services_set': item['fields']['web_services_set'],
                            'oaipmh_web_services_type': item['fields']['web_services_type']
                        }

                        if item['fields']['uri'].startswith('https://'):
                            http_address, http_uri, http_ssl = parse_url(
                                item['fields']['uri'].strip())
                            host.ssl_certs.add(http_address)
                if host.oaipmh_endpoints == {}:
                    del host.oaipmh_endpoints
                # _create_centerregistry_services(host_name=host_name,
                #                                 site_contacts=site_contacts,
                #                                 centre_definition=centre,
                #                                 service_type='OAI',
                #                                 filename=filename)

            # CQL
            if cql_success:
                host.srucql_endpoints = {}
                for item in REGISTRY['FCSEndpoint']:
                    if item['fields']['centre'] == centre['pk']:
                        host.srucql_endpoints[item['pk']] = {
                            'srucql_endpoint': item['fields']['uri']
                        }

                        if item['fields']['uri'].startswith('https://'):
                            http_address, http_uri, http_ssl = parse_url(
                                item['fields']['uri'].strip())
                            host.ssl_certs.add(http_address)
                if host.srucql_endpoints == {}:
                    del host.srucql_endpoints
                # _create_centerregistry_services(host_name=host_name,
                #                                 site_contacts=site_contacts,
                #                                 centre_definition=centre,
                #                                 service_type='CQL',
                #                                 filename=filename)

            if len(host.ssl_certs) == 0:
                del host.ssl_certs
            else:
                host.ssl_certs = {dns: {
                        'ssl_cert_address': dns,
                        'ssl_cert_warn': 30,
                        'ssl_cert_critical': 10
                    } for dns in host.ssl_certs
                }

            host_group.save('./conf.d/hosts', host)
            host2 = Host.load(f'./conf.d/hosts/{name}.conf')
            print(host.name, host == host2)

        # contacts = merge_centerregistry_icinga_users()

        # check_command = 'check_dummy'
        # use = 'custom-active-host'
        # for iterator, centre in enumerate(REGISTRY['Centre']):
        #     host_name = \
        #         transliterate_to_ascii(
        #             centre['fields']['shorthand'].strip()))
        #     filename = \
        #         '{}/configuration/configuration/{}.cfg'.format(getcwd(),
        #                                                        host_name)
        #     _LAT = str(centre['fields']['latitude'].strip())
        #     _LONG = str(centre['fields']['longitude'].strip())
        #     display_name = \
        #         transliterate_to_ascii(centre['fields']['name'].strip()))
        #     try:
        #         config_host = Model.Host.objects.get_by_shortname(host_name)
        #         config_host = _move_objekt_to_siteconfig(config_host, filename)
        #         action = 'Modifying'
        #     except KeyError:
        #         action = 'Adding'
        #         config_host = Model.Host(host_name=host_name,
        #                                  filename=filename)
        #     logging.debug('%s host: %s', action, host_name)
        #     config_host.set_attribute('_LAT', _LAT)
        #     config_host.set_attribute('_LONG', _LONG)
        #     config_host.set_attribute('check_command', check_command)
        #     config_host.set_attribute('display_name', display_name)
        #     config_host.set_attribute('use', use)

        #     # A hack to make sure sysops@clarin.eu always receives
        #     # notifications. Service escalations are not a workable alternative
        #     # for us. Only migration to Icinga 2 will make this cleaner and
        #     # easier.
        #     site_contacts = 'sysops@clarin.eu,' + \
        #                     get_site_usergroup(centre=centre,
        #                                             icinga_contacts=contacts)
        #     config_host.set_attribute('contacts', site_contacts)
        #     config_host.save()

        #     # create servicegroup for site and for Centre Registry services per
        #     for item in ['_centerregistry', '']:
        #         servicegroup_name = host_name + item
        #         try:
        #             config_servicegroup = \
        #                 Model.Servicegroup.objects.get_by_shortname(
        #                     servicegroup_name)
        #             config_servicegroup = \
        #                 _move_objekt_to_siteconfig(
        #                     config_servicegroup, filename)
        #         except KeyError:
        #             logging.debug('Adding new Servicegroup: %s',
        #                           servicegroup_name)
        #             config_servicegroup = Model.Servicegroup(
        #                 servicegroup_name=servicegroup_name,
        #                 alias=servicegroup_name,
        #                 filename=filename)
        #         current_groups = \
        #             config_servicegroup.get_attribute('servicegroup_members')
        #         if not current_groups:
        #             current_groups = list()
        #         else:
        #             current_groups = map(str.strip, current_groups.split(','))
        #         creg_group = servicegroup_name + '_centerregistry'
        #         if item is '' and creg_group not in current_groups:
        #             current_groups.append(creg_group)
        #             config_servicegroup.set_attribute(
        #                 'servicegroup_members',
        #                 ','.join(sorted(current_groups)))
        #         config_servicegroup.save()
        #     # OAI
        #     if oai_success:
        #         _create_centerregistry_services(host_name=host_name,
        #                                         site_contacts=site_contacts,
        #                                         centre_definition=centre,
        #                                         service_type='OAI',
        #                                         filename=filename)

        #     # CQL
        #     if cql_success:
        #         _create_centerregistry_services(host_name=host_name,
        #                                         site_contacts=site_contacts,
        #                                         centre_definition=centre,
        #                                         service_type='CQL',
        #                                         filename=filename)


def run(push_repo=False, pull_repo=True, dont_remove_repo=False):
    """
    get repository, modify config, push repo
    :return:
    """
    # repo = _load_git_repo('git@github.com:clarin-eric/monitoring.git',
    #                       'configuration', pull_repo=pull_repo)
    create_config_from_centerregistry()
    # _push_and_delete_git_repo(repo=repo, push_repo=push_repo,
    #                           dont_remove_repo=dont_remove_repo)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--debug",
                        help="get debug output",
                        action="store_true")
    parser.add_argument("--logstash",
                        help="log everything (in addition) to logstash "
                             ", give host:port")
    parser.add_argument("--push",
                        help="push Git repository",
                        action="store_true")
    parser.add_argument("--nopull",
                        help="Don't pull Git repository",
                        action="store_false")
    parser.add_argument("--nocleanup",
                        help="don't remove repo after push",
                        action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.basicConfig(format='%(message)s', level=logging.DEBUG)
    else:
        logging.basicConfig(format='%(message)s', level=logging.INFO)

    push = args.push
    remove = args.nocleanup
    pull_repo = args.nopull

    if args.logstash:
        logger = logging.getLogger()
        import logstash
        ls_host, ls_port = args.logstash.split(':')
        logger.addHandler(logstash.TCPLogstashHandler(host=ls_host,
                                                      port=int(ls_port),
                                                      version=1))
    run(push_repo=push, pull_repo=pull_repo, dont_remove_repo=remove)
