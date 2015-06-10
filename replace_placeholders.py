import logging

from pynag import Model

from config_generation.config_generation_centerregistry \
    import _is_encrypted, _decrypt, _load_icinga_config, _load_script_config

CONFIG = None


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


def _manipulate_cgi_admins():
    f = open('cgi.cfg', 'r')
    content = f.read()
    f.close()
    content = content.replace('CLARINADMINS', CONFIG['clarinadmins'])
    f = open('cgi.cfg', 'w')
    f.write(content)
    f.close()


if __name__ == '__main__':
    global CONFIG
    CONFIG = _load_script_config()
    _load_icinga_config('icinga.cfg')
    _decrypt_contacts()
    _manipulate_cgi_admins()
