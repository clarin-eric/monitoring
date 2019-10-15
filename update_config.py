#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import logging
import os
import re
import requests

from argparse import ArgumentParser
from datetime import datetime
from git import Repo
from git.exc import GitCommandError
from subprocess import Popen, PIPE
from tempfile import TemporaryDirectory
from urllib.parse import urlparse


REGISTRY = {}


class Config(dict):
    def __init__(self, name, **kwargs):
        super(Config, self).__init__()
        self.__dict__['config_names'] = {'_import', 'name', 'vars'}
        self['name'] = name
        self['vars'] = {}
        for k, v in kwargs.items():
            self[k] = v

    def __eq__(self, other):
        if sorted(self.keys()) != sorted(other.keys()):
            return False
        for k in self.keys():
            if self[k] != other[k]:
                return False
        return True

    def __contains__(self, item):
        if item in self.config_names:
            return super(Config, self).__contains__(item)
        else:
            return item in self['vars']

    def __delattr__(self, key):
        if key in self.config_names:
            del self[key]
        else:
            del self['vars'][key]

    def __delitem__(self, key):
        if key in self.config_names:
            super(Config, self).__delitem__(key)
        else:
            del self['vars'][key]

    def __getattr__(self, key):
        if key == '__name__':
            return self.__class__.__name__
        else:
            if key in self.config_names:
                return self[key]
            else:
                return self['vars'][key]

    def __getitem__(self, key):
        if key in self.config_names:
            return super(Config, self).__getitem__(key)
        else:
            return self['vars'][key]

    def __setattr__(self, key, val):
        if key in self.config_names:
            self[key] = val
        else:
            self['vars'][key] = val

    def __setitem__(self, key, val):
        if key in self.config_names:
            super(Config, self).__setitem__(key, val)
        else:
            self['vars'][key] = val

    def __str__(self):
        def escape(v):
            if type(v) == str:
                return f'"{v}"'
            elif type(v) == int or type(v) == float:
                return f'{v}'
            elif type(v) == bool:
                return f'{"true" if v else "false"}'
            else:
                return f'"{v}"'

        def to_str(values):
            lines = []
            for k, v in sorted(values.items(), key=lambda i: i[0]):
                if k == '_import':
                    lines.append(f'import "{self._import}"\n')
                elif type(v) == list or type(v) == tuple:
                    lines.append(
                        f'{k} = [{", ".join(escape(i) for i in sorted(v))}]\n')
                elif type(v) == dict:
                    indent = True
                    for i, line in enumerate(to_str(v)):
                        if line.endswith(' = {\n'):
                            if i == 0:
                                lines.append(f'{k}["{line[:-5]}"] = {{\n')
                            else:
                                lines.append('}\n')
                                lines.append(f'{k}["{line[:-5]}"] = {{\n')
                            indent = False
                        elif i == 0:
                            lines.append(f'{k} = {{\n')
                            lines.append(f'    {line}')
                        elif line == '}\n':
                            continue
                        elif indent:
                            lines.append(f'    {line}')
                        else:
                            lines.append(line)
                    lines.append('}\n')
                elif v is None:
                    continue
                else:
                    lines.append(f'{k} = {escape(v)}\n')
            return lines

        return f'object {self.__name__} "{self.name}" {{\n' + \
            f'    {"    ".join(to_str(self))}' + \
            '}'

    def items(self):
        for k, v in super(Config, self).items():
            if k == 'name':
                continue
            elif k == 'vars':
                for k2, v2 in v.items():
                    yield f'{k}.{k2}', v2
            else:
                yield k, v

    @classmethod
    def from_str(cls, s):
        obj_pattern = r'object\s+(?P<obj>[^\s]+)\s+"(?P<name>[^"]+)"\s*{' + \
            r'(?P<body>((?!object\s+[^\s]+\s+").)*)}'
        prop_pattern = r'^\s*(import\s+"(?P<import>[^"]+)"|' + \
            r'(vars\.)?(?P<list>[^\s=]+\s*=\s*\[([^\]]*)\]$)|' + \
            r'(vars\.)?(?P<dict>[^\s=]+(\[[^\]]+\])?\s*=\s*\{([^\}]+)\}$)|' + \
            r'(vars\.)?(?P<prop>[^\s=]+\s*=\s*(.+))$)'
        kv_pattern = r'(?P<k>[^\s=]+)\s*=\s*(?P<v>.+)$'

        def unescape(v):
            if v == 'true':
                return True
            elif v == 'false':
                return False
            elif re.fullmatch(r'[+-]?[0-9]+', v):
                return int(v)
            elif re.fullmatch(r'[+-]?[0-9]+\.[0-9]+', v):
                return float(v)
            elif v.startswith('"') and v.endswith('"'):
                return v[1:-1]
            else:
                return v

        def extract(s):
            values = {}
            for m in re.finditer(prop_pattern, s, flags=re.M):
                if m.group('import'):
                    values['_import'] = m.group('import')
                elif m.group('list'):
                    m2 = re.search(r'(?P<k>[^\s=]+)\s*=\s*\[(?P<v>[^\]]*)\]',
                                   m.group('list'))
                    if m2:
                        values[m2.group('k')] = []
                        for s in m2.group('v').split(','):
                            if s == '' or s == '""':
                                continue
                            values[m2.group('k')].append(unescape(s.strip()))
                elif m.group('dict'):
                    m2 = re.search(r'(?P<k>[^\s=\]]+)(\["(?P<k2>[^\]]+)"\])?' +
                                   r'\s*=\s*\{(?P<v>[^\}]+)\}',
                                   m.group('dict'))
                    if m2:
                        k = m2.group('k')
                        if m2.group('k2'):
                            if k not in values:
                                values[k] = {}
                            values[k][m2.group('k2')] = \
                                extract(m2.group('v').strip())
                        else:
                            values[k] = extract(m2.group('v').strip())
                elif m.group('prop'):
                    m2 = re.search(kv_pattern, m.group('prop'))
                    if m2:
                        values[m2.group('k')] = unescape(m2.group('v').strip())
            return values

        match = re.search(obj_pattern, s, flags=re.M | re.S)
        if match:
            name = match.group('name')
            values = extract(match.group('body'))

            if cls.__name__ == 'Config':
                return eval(match.group('obj'))(name, **values)
            else:
                return cls(name, **values)
        else:
            return None

    @classmethod
    def load(cls, path):
        obj_regex = r'object\s+(?P<obj>[^\s]+)\s+"(?P<name>[^"]+)"\s*{' + \
            r'(?P<body>((?!object\s+[^\s]+\s+").)*)}'

        objs = []
        with open(path, 'r', encoding='utf8') as f:
            for m in re.finditer(obj_regex, f.read(), flags=re.M | re.S):
                if cls.__name__ != 'Config' and cls.__name__ != m.group('obj'):
                    continue
                objs.append(cls.from_str(m.group().strip()))
        if len(objs) == 0:
            return None
        elif len(objs) == 1:
            return objs[0]
        else:
            return objs

    def save(self, path, *args):
        if os.path.isdir(path):
            path = os.path.join(path, f'{self.name}.conf')
        with open(path, 'w', encoding='utf8') as f:
            f.write(f'{self}\n')

            for arg in args:
                f.write(f'\n{arg}\n')


class Host(Config):
    def __init__(self, name, **kwargs):
        super(Host, self).__init__(name)
        self.config_names.update(['display_name', 'address', 'address6',
                                  'groups', 'vars', 'check_command',
                                  'max_check_attempts', 'check_period',
                                  'check_timeout', 'check_interval',
                                  'retry_interval', 'enable_notifications',
                                  'enable_active_checks', 'icon_image_alt',
                                  'enable_passive_checks', 'icon_image',
                                  'enable_event_handler', 'enable_flapping',
                                  'enable_perfdata', 'event_command',
                                  'flapping_threshold_high', 'action_url',
                                  'flapping_threshold_low', 'volatile', 'zone',
                                  'command_endpoint', 'notes', 'notes_url'])
        for k, v in kwargs.items():
            self[k] = v

    def add_ssl_cert(self, dns):
        if 'ssl_certs' not in self:
            self.ssl_certs = {}
        self.ssl_certs[dns] = {
            'ssl_cert_address': dns,
            'ssl_cert_cn': dns,
            'ssl_cert_altnames': True,
            'ssl_cert_warn': 30,
            'ssl_cert_critical': 10
        }


class HostGroup(Config):
    def __init__(self, name, **kwargs):
        super(HostGroup, self).__init__(name)
        self.config_names.update(['display_name', 'groups'])
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
        self.config_names.update(['display_name', 'groups'])
        for k, v in kwargs.items():
            self[k] = v


def fetch_centre_registry(key):
    """Fetch data from Centre Registry, store it globally as dict.

    Args:
        key: URL endpoint

    Return:
        boolean indicating success
    """
    r = requests.get(f'https://centres.clarin.eu/api/model/{key:s}')
    if r.status_code == requests.codes.ok:
        REGISTRY[key] = r.json()
        return True
    else:
        return False


def parse_url(url):
    """Parse a given URL an spilt in its parts.

    Args:
        url: URL

    Return:
        address, uri, ssl (boolean)
    """
    parsed_url = urlparse(url)
    components = parsed_url.netloc.split(':')

    address = components[0]
    uri = f'{parsed_url.path}{parsed_url.params}{parsed_url.query}' + \
        f'{parsed_url.fragment}'
    return address, '/' if uri == '' else uri, parsed_url.scheme == 'https'


def translit_to_ascii(text):
    """Helper function to transliterate UTF-8 to ASCII.

    Args:
        text: text to transliterate

    Return:
        transliterated text
    """
    process = Popen(['iconv', '-f', 'utf-8', '-t' 'ascii//TRANSLIT'],
                    stdout=PIPE, stdin=PIPE)
    stdoutdata, _ = process.communicate(text.encode('utf-8'))
    return stdoutdata.decode(encoding='utf-8')


def git_repo(url, path, pull=True):
    """Load our repo from github or, if its there, get the updates.
    If there is a directory under path that is not a git repo, crash.

    Args:
        url: Repository URL
        path: Local path
        pull: pull changes?

    Return:
        GitPython repo object
    """
    try:
        logging.info(f'Clone repository {url} to {path}.')
        repo = Repo.clone_from(url, path)
    except GitCommandError:
        logging.info('Repository already exists.')
        repo = Repo(path)
        if pull:
            logging.info(f'Pull changes.')
            github = repo.remote('origin')
            github.pull()
    return repo


def commit_changes(repo, push=False):
    """Add new files, commit, push.

    Args:
        repo: GitPython repo object
        push: whether to push the changes or not.
    """
    if repo.is_dirty(untracked_files=True):
        repo.index.add(repo.untracked_files)
        for f in repo.index.diff(None):
            if f.change_type == 'D':
                logging.debug(f'Remove file from git {f.a_path}.')
                repo.index.remove([f.a_path])
            else:
                logging.debug(f'Add file from git {f.a_path}.')
                repo.index.add([f.a_path])

        now = datetime.now()
        logging.info(f'Found changes, commit changes.')
        repo.index.commit('Information from Centre Registry updated.')

        if push:
            logging.info(f'Push to origin.')
            repo.remote('origin').push()
    else:
        logging.info(f'No changes, nothing to commit.')


def load_hosts(path='./conf.d/hosts/'):
    """Load hosts and host groups from config.

    Args:
        path: path to host config dir

    Return:
        dict of hosts, dict of host groups
    """
    logging.info(f'Load exinting host configs from {path}.')
    hosts = {}
    host_groups = {}
    with os.scandir(path) as it:
        for entry in it:
            if entry.name.endswith('.conf') and entry.is_file():
                for cfg in Config.load(entry.path):
                    if type(cfg) == Host:
                        hosts[cfg.name] = cfg
                    elif type(cfg) == HostGroup:
                        host_groups[cfg.name] = cfg
    logging.info(f'Found {len(hosts)} hosts and {len(host_groups)} host ' +
                 'groups.')
    return hosts, host_groups


def load_users(path='./conf.d/users.conf'):
    """Load users from config.

    Args:
        path: path to user config

    Return:
        dict of users, dict of user groups
    """
    logging.info(f'Load exinting users config from {path}.')
    return {user.email: user for user in User.load(path)}, \
        {group.name: group for group in UserGroup.load(path)}


def save_users(users, groups, groups_to_del=set(), path='./conf.d/users.conf'):
    """Save users and user groups.

    Args:
        users: dict of users
        groups: dict of user groups
        groups_to_del: user groups to remove, if a user has only groups which
                       are deleted the user gets also removed.
        path: path to user config
    """
    users = [v for v in users.values()]

    for k in groups_to_del:
        if k in groups:
            logging.info(f'Remove user group {k}.')
            del groups[k]

    for user in users:
        if 'groups' in user:
            user.groups = list(set(user.groups))
            if len(user.groups) > 0:
                for k in groups_to_del:
                    if k in user.groups:
                        user.groups.remove(k)
                if len(user.groups) == 0:
                    logging.info(f'Remove user {user.name}.')
                    users.remove(user)
            else:
                del user.groups

    logging.info(f'Saving users config to {path}.')
    users[0].save(path, *(users[1:] + [v for v in groups.values()]))


def merge_centerregistry_users(users):
    """Merge icinga users with users from Centre Registry.

    Args:
        users: existing icinga users, gets updated with new users.

    Return:
        dict with IDs from Centre Registry and icinga user IDs.
    """
    logging.info('Merge icinga users with Centre Registry users.')
    ids = {}
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

        ids[contact['pk']] = email
        if email in users:
            users[email].display_name = name
            users[email].telephone_number = telephone_number
            users[email].website_url = website_url
            logging.info(f'Update user {email}.')
            logging.debug(users[email])
        else:
            users[email] = User(name=email, display_name=name,
                                _import='generic-user', email=email,
                                telephone_number=telephone_number,
                                website_url=website_url, groups=[])
            logging.info(f'Create user {email}.')
            logging.debug(users[email])
    return ids


def config_from_centerregistry():
    """Creates config from center registry."""

    logging.info('Generate config form center regestry.')

    users, user_groups = load_users()
    hosts, host_groups = load_hosts()
    if fetch_centre_registry('Centre') and fetch_centre_registry('Contact'):
        oai_success = fetch_centre_registry('OAIPMHEndpoint')
        cql_success = fetch_centre_registry('FCSEndpoint')
        ids = merge_centerregistry_users(users)

        for i, centre in enumerate(REGISTRY['Centre']):
            logging.info(f'Centre registry {centre["fields"]["name"].strip()}')

            name = translit_to_ascii(centre['fields']['shorthand'].strip())
            display_name = centre['fields']['name'].strip()

            if name in hosts:
                logging.info(f'Update host {name}.')
                host = hosts[name]
                host.display_name = display_name
                del hosts[name]
            else:
                logging.info(f'Create host {name}.')
                host = Host(name=name, display_name=display_name,
                            _import='clarin-generic-host')

            if name in host_groups:
                logging.info(f'Update host group {name}.')
                host_group = host_groups[name]
                host_group.display_name = display_name
                del host_groups[name]
            else:
                logging.info(f'Create host group {name}.')
                host_group = HostGroup(name=name, display_name=display_name)
            host.groups = [host_group.name]

            if name not in user_groups:
                user_groups[name] = UserGroup(name=name,
                                              display_name=display_name)
            else:
                user_groups[name].display_name = display_name
            for contact_id in centre['fields']['monitoring_contacts']:
                users[ids[contact_id]].groups.append(name)
            tech_contact_id = centre['fields']['technical_contact']
            users[ids[tech_contact_id]].groups.append(name)

            host.address, host.http_uri, host.http_ssl = parse_url(
                centre['fields']['website_url'].strip())
            if host.http_ssl:
                host.add_ssl_cert(host.address)

            host.geolocation = '' + \
                f'{float(centre["fields"]["latitude"].strip())},' + \
                f'{float(centre["fields"]["longitude"].strip())}'

            # OAI
            if oai_success:
                host.oaipmh_endpoints = {}
                for item in REGISTRY['OAIPMHEndpoint']:
                    fields = item['fields']
                    if fields['centre'] == centre['pk']:
                        logging.debug(f'Add OAI-PMH endpoint {item["pk"]}: ' +
                                      f'{fields["uri"]}')
                        host.oaipmh_endpoints[f'{item["pk"]}'] = {
                            'oaipmh_endpoint': fields['uri'],
                            'oaipmh_metadata_format':
                                fields['metadata_format'],
                            'oaipmh_web_services_set':
                                fields['web_services_set'],
                            'oaipmh_web_services_type':
                                fields['web_services_type']
                        }

                        if fields['uri'].startswith('https://'):
                            http_address, http_uri, http_ssl = parse_url(
                                fields['uri'].strip())
                            host.add_ssl_cert(http_address)
                if host.oaipmh_endpoints == {}:
                    del host.oaipmh_endpoints

            # CQL
            if cql_success:
                host.srucql_endpoints = {}
                for item in REGISTRY['FCSEndpoint']:
                    fields = item['fields']
                    if fields['centre'] == centre['pk']:
                        logging.debug(f'Add SRU/CQL endpoint {item["pk"]}: ' +
                                      f'{fields["uri"]}')
                        host.srucql_endpoints[f'{item["pk"]}'] = {
                            'srucql_endpoint': fields['uri']
                        }

                        if fields['uri'].startswith('https://'):
                            http_address, http_uri, http_ssl = parse_url(
                                fields['uri'].strip())
                            host.add_ssl_cert(http_address)
                if host.srucql_endpoints == {}:
                    del host.srucql_endpoints

            logging.debug(f'Saving {host.name} host config.')
            logging.debug(host)
            host_group.save('./conf.d/hosts', host)

        for k in set(list(hosts.keys()) + list(host_groups.keys())):
            logging.info(f'Remove ./conf.d/hosts/{k}.conf config file.')
            os.remove(os.path.join('./conf.d/hosts', f'{k}.conf'))

        save_users(users, user_groups,
                   set(list(hosts.keys()) + list(host_groups.keys())))


def config_from_switchboard_tool_registry():
    """Creates config from switchboard-tool-registry repo."""

    logging.info('Generate config form switchboard-tool-registry repo.')

    users, user_groups = load_users()
    switchboard_users = set()
    with TemporaryDirectory() as tmp_dir:
        repo = git_repo('https://github.com/clarin-eric/switchboard-tool-' +
                        'registry.git', tmp_dir)

        logging.info('Create host group Switchboard Tool Registry.')
        host_group = HostGroup(name='switchboard-tool-registry',
                               display_name='Switchboard Tool Registry')
        hosts = []
        with os.scandir(tmp_dir) as it:
            for entry in it:
                if entry.name.endswith('.json') and entry.is_file():
                    with open(os.path.join(tmp_dir, entry.name), 'r',
                              encoding='utf8') as f:
                        logging.info(f'Switchboard Tool Registry {entry.name}')

                        data = json.loads(f.read())
                        if 'homepage' not in data:
                            continue

                        name = translit_to_ascii(data['name'].strip())
                        logging.info(f'Create host {name}.')
                        host = Host(name=name, _import='clarin-generic-host',
                                    groups=[host_group.name])
                        host.address, host.http_uri, host.http_ssl = \
                            parse_url(data['homepage'].strip())

                        if host.http_ssl:
                            host.add_ssl_cert(host.address)

                        http_address, http_uri, http_ssl = \
                            parse_url(data['url'].strip())
                        host.http_vhosts = {data['name']: {
                            'http_address': http_address,
                            'http_uri': http_uri,
                            'http_ssl': http_ssl
                        }}
                        if data['authentication'].startswith('Yes.'):
                            host.http_vhosts[data['name']]['http_expect'] = \
                                '401 UNAUTHORIZED'
                        if http_ssl:
                            host.add_ssl_cert(host.address)

                        email = data['contact']['email']
                        name = data['contact']['person']

                        if email != 'Unknown email' and email is not None:
                            switchboard_users.add(email)
                            if email not in users:
                                logging.info(f'Create user {email}.')
                                users[email] = User(name=email,
                                                    display_name=name,
                                                    _import='generic-user',
                                                    email=email,
                                                    groups=[host_group.name])
                            else:
                                logging.info(f'Update user {email}.')
                                users[email].display_name = name
                                if 'groups' in users[email]:
                                    if host_group.name not in \
                                            users[email].groups:
                                        users[email].groups.append(
                                            host_group.name)
                                else:
                                    users[email].groups = [host_group.name]
                            host.notification = {'mail': {'users': [email]}}

                        logging.debug(users[email])
                        logging.debug(host)
                        hosts.append(host)

        logging.info(f'Saving switchboard tool registry host configs.')
        host_group.save('./conf.d/', *sorted(hosts, key=lambda x: x.name))

        to_del = []
        for k in users.keys():
            if 'groups' in users[k] and host_group.name in users[k].groups:
                if users[k].name not in switchboard_users:
                    if len(users[k].groups) == 1:
                        to_del.append(k)
                    else:
                        users[k].groups.remove(host_group.name)
        for k in to_del:
            logging.info(f'Remove user {users[k].name}.')
            del users[k]
        save_users(users, user_groups)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('-v', '--verbose', help='Verbose output.',
                        action='store_true')
    parser.add_argument('-f', '--log-format', help='Logging format.',
                        default='%(asctime)s %(levelname)s %(message)s')
    parser.add_argument('--push', help='Push Git repository.',
                        action='store_true')
    parser.add_argument('--nopull', help="Don't pull Git repository.",
                        action='store_false')
    parser.add_argument('--nocleanup', help="Don't remove repo after push.",
                        action='store_true')
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(format=args.log_format, level=logging.DEBUG)
    else:
        logging.basicConfig(format=args.log_format, level=logging.INFO)

    repo = git_repo('git@github.com:clarin-eric/monitoring.git', '.',
                    args.nopull)
    config_from_centerregistry()
    config_from_switchboard_tool_registry()
    commit_changes(repo, args.push)
