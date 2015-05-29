from cryptography.fernet import Fernet, InvalidToken
from pynag import Parsers, Model
import ConfigParser
import logging

CONFIG = None

def _get_config(section='default'):
    global CONFIG
    config = ConfigParser.SafeConfigParser()
    config.read('config.ini')
    CONFIG = dict(config.items(section=section))


def _is_encrypted(string):
    # are we already encrypted?
    if string.startswith('gAAAAA'):
        return True
    else:
        return False


def _decrypt(string):
    try:
        string = Fernet(CONFIG['token']).decrypt(bytes(string))
    except InvalidToken as err:
        logging.info('String not encrypted, returning: %s', string)
    return string


def _load_icinga_config():
    Model.cfg_file = 'icinga.cfg'
    Model.pynag_directory = 'configuration/pynag'
    config = Parsers.Config(cfg_file='icinga.cfg')
    config.parse()


def _decrypt_contacts():
    for contact in Model.Contact.objects.all:
        if str(contact.get_attribute('register')) != '0' and _is_encrypted(contact.get_attribute('contact_name')):
            contact.rename(_decrypt(contact.get_attribute('contact_name')))
            contact.set_attribute('email', _decrypt(contact.get_attribute('email')))
            logging.debug('Writing Contact %s', contact)
            contact.save()


def _manipulate_cgi_admins():
    f = open('cgi.cfg', 'r')
    content = f.read()
    f.close()
    content = content.replace('CLARINADMINS', CONFIG['clarinadmins'])
    f = open('cgi.cfg', 'w')
    f.write(content)
    f.close()


if __name__ == '__main__':
    _get_config()
    print CONFIG
    _load_icinga_config()
    _decrypt_contacts()
    _manipulate_cgi_admins()
