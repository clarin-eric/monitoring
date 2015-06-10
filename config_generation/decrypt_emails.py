import ConfigParser
import logging

from pynag import Model

from config_generation_centerregistry import \
    _is_encrypted, _decrypt, _load_icinga_config, _load_script_config

CONFIG = None


def _get_script_config(section='centerregistry'):
    global CONFIG
    config = ConfigParser.SafeConfigParser()
    config.read('config.ini')
    CONFIG = dict(config.items(section=section))


def _decrypt_contacts():
    for contact in Model.Contact.objects.all:
        if str(contact.get_attribute('register')) != '0' and \
                _is_encrypted(contact.get_attribute('contact_name')):
            contact.rename(_decrypt(CONFIG['token'],
                                    contact.get_attribute('contact_name')))
            contact.set_attribute('email',
                                  _decrypt(CONFIG['token'],
                                           contact.get_attribute('email')))
            logging.debug('Writing Contact %s', contact)
            contact.save()


if __name__ == '__main__':
    global CONFIG
    CONFIG = _load_script_config()
    _load_icinga_config('configuration/icinga.cfg')
    _decrypt_contacts()
