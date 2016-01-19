from sopel import module
from redis import Redis
import pprint, re, json

ENTRY_NOT_FOUND = '`%s` does not exist in the learndb!'
ENTRY_TOO_LONG = 'Eschew verbosity! Learndb entries have a max length of 255 characters.'
ADD_SUCCESS = '`%s` entry added!'
INVALID_KEY_FORMAT = 'Invalid key format!'
INVALID_COMMAND_FORMAT = 'Invalid Command, syntax is `!learn (add|del|edit) KEY_NAME[PAGE_NUMBER] command_body`'


def redis_connect():
    return Redis('localhost', 6379, 0) 


@module.rule('\?\?')
def lookup(bot, trigger):
    r = redis_connect()
    key = trigger.replace('??', '')
    # split the key so that we know the entry being searched for and the index within that entry
    key, index = split_key(key)
    
    bot.reply(_lookup(r, key, index))
    

def _lookup(r, key, index):
    entry = r.get(key)

    if not entry:
        return ENTRY_NOT_FOUND % key

    # its stored as a string but are expecting a list
    obj = json.loads(entry)
    # if there is more than one key in the stored list, show the index
    index_suffix = '[%d/%d]' % (index+1, len(obj))

    if index < 0 or index >= len(obj):
        return INVALID_KEY_FORMAT
   
    entry = obj[index]

    # recursive lookup pattern testing, does the value of our lookup point to another entry?
    rlp = re.compile(r"^see \{(.+?)\}")
    match = rlp.match(entry)

    if match:
        key, index = split_key(match.group(1))
        entry = _lookup(r, key, index)
    else:
        entry = '%s%s: %s' % (key, index_suffix, entry)

    return entry


@module.commands('learn')
def learn(bot, trigger):
    r = redis_connect()
    trigger = trigger.strip()
    del_command = '%s%s del ' % (bot.config.core.prefix, learn.commands[0])
    
    # delete doesn't have an entry, only command and key
    if trigger.startswith(del_command):
        _, command, key = trigger.split(' ', 2)
    else:
        _, command, key, entry = trigger.split(' ', 3)
    
    # split the key into its tuple form
    key_tuple = split_key(key)

    # valid keys cannot be less than 1
    if key_tuple[1] < 0:
        message = INVALID_KEY_FORMAT
    elif command in ['add', 'edit']:
        if len(entry) > 255:
            message = ENTRY_TOO_LONG
        elif command == 'add':
            message = add_entry(r, key_tuple, entry)
        elif command == 'edit':
            message = edit_entry(r, key_tuple, entry)
        else:
            message = INVALID_COMMAND_FORMAT
    elif command == 'del':
        message = delete_entry(r, key_tuple)
    else:
        message = INVALID_COMMAND_FORMAT

    if message:
        bot.reply(message)

    r.save()


def add_entry(r, key_tuple, entry):
    if len(entry) > 255:
        return ENTRY_TOO_LONG

    key, index = key_tuple

    existing_entry = r.get(key)
    # If a key already exists, parse the json object and add to it;
    # otherwise create an object and put its json into redis
    if existing_entry:
        obj = json.loads(existing_entry)
        obj.append(entry)
    else:
        obj = [entry]
        
    r.set(key, json.dumps(obj))

    return _lookup(r, key, len(obj)-1)


def delete_entry(r, key_tuple):
    key, index = key_tuple
    existing_entry = r.get(key)

    if existing_entry:
        obj = json.loads(existing_entry)
        entry = obj.pop(index)

        if len(obj) > 0:
            r.set(key, json.dumps(obj))
        else:
            r.delete(key)

        return 'Deleted %s' % entry 
    
    return ENTRY_NOT_FOUND % key


def edit_entry(r, key_tuple, edit_pattern):
    key, index = key_tuple
    existing_entry = r.get(key)

    if existing_entry:
        match = re.match(r"s/(.+)/(.+)/", edit_pattern)

        if match is None:
            return ''

        find, replace = match.group(1, 2)

        obj = json.loads(existing_entry)
        entry = re.sub(re.escape(find), replace, obj.pop(index))
        obj.insert(index, entry)

        r.set(key, json.dumps(obj))

        return _lookup(r, key, index)

    return ENTRY_NOT_FOUND % key


def clean_key(key):
    return key.replace(' ', '_').lower()


def split_key(key):
    match = re.search(r"(\w+?)\[(\d)\]", key)

    if not match:
        r = (clean_key(key), 0)
    else:
        r = match.group(1, 2)
        r = (clean_key(r[0]), int(r[1])-1)
    
    return r
