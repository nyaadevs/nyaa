__author__ = 'dale mcdiarmid'

import re
import os.path

def modify_list(values=[], pattern='', replacement='', ignorecase=False):
    ''' Perform a `re.sub` on every item in the list'''
    if ignorecase:
        flags = re.I
    else:
        flags = 0
    _re = re.compile(pattern, flags=flags)
    return [_re.sub(replacement, value) for value in values]

def append_to_list(values=[], suffix=''):
    if isinstance(values, basestring):
        values = values.split(',')
    return [str(value+suffix) for value in values]

def array_to_str(values=[],separator=','):
    return separator.join(values)

def extract_role_users(users={}):
    role_users=[]
    for user,details in users.iteritems():
        if "roles" in details:
            for role in details["roles"]:
                role_users.append(role+":"+user)
    return role_users

def filename(filename=''):
    return os.path.splitext(os.path.basename(filename))[0]

def filter_reserved(user_roles={}):
    not_reserved = []
    for user_role,details in user_roles.items():
        if not "metadata" in details or not "_reserved" in details["metadata"] or not details["metadata"]["_reserved"]:
            not_reserved.append(user_role)
    return not_reserved


class FilterModule(object):
    def filters(self):
        return {'modify_list': modify_list,
        'append_to_list':append_to_list,
        'array_to_str':array_to_str,
        'extract_role_users':extract_role_users,
        'filter_reserved':filter_reserved,
        'filename':filename}

