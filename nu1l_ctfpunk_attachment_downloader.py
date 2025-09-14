import argparse
import os
import re
import requests
import sys
from urllib3.exceptions import NewConnectionError, MaxRetryError
# import traceback


def main():
    args = arg_parse()
    # print(args)
    get_challs(args)


def get_challs(args):
    headers = {
        'Authorization': args.token,
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0',
    }

    # get game title
    portal_id_url = f'{args.url}/competitions/converter:code2id?code=portal'
    response = requests.get(portal_id_url, headers=headers)
    if response.status_code != 200:
        print('❌', f'Failed to get game id from {portal_id_url}, status code: {response.status_code}')
        sys.exit(1)
    portal_id = response.json()['data']['id']

    game_info_url = f'{args.url}/competitions/{portal_id}'
    response = requests.get(game_info_url, headers=headers)
    if response.status_code != 200:
        print('❌', f'Failed to get game info from {game_info_url}, status code: {response.status_code}')
        sys.exit(1)
    game_info = response.json()
    game_title = game_info['data']['title']

    # get challenge list
    url_details = f'{args.url}/competitions/{portal_id}/challenges'
    response = requests.get(url_details, headers=headers)
    if response.status_code != 200:
        print('❌', f'Failed to get challenge list from {url_details}, status code: {response.status_code}')
        sys.exit(1)

    response_data = response.json()['data']['challenges']
    for object in response_data:
        if object.get('categories') and object['categories'][0].lower() not in args.allowlist:
            continue
        try:
            get_one_chall(args, object['id'], headers, game_title, portal_id)
        except (MaxRetryError, NewConnectionError, ConnectionError, OSError):
            print('❌', f'Failed to get challenge {object['name']} file')
        except Exception as e:
            print('❌', f'Failed to get challenge {object['name']}, error: {e}')
            # traceback.print_exc()

    print('🎉', 'All done.')


def get_absolute_path(args, game_title: str, category: str, chall_name: str, origin_file_name: str):
    file_path = args.file_path \
                    .strip() \
                    .lstrip('/\\') \
                    .format(game=game_title, tag=category, category=category, chall=chall_name, origin=origin_file_name)
    if not args.keep_spaces:
        file_path = re.sub(r'\s+', '-', file_path)
    file_path = re.sub(r'[:*?"<>|]', '_', file_path)

    root_directory = args.root_directory \
                        .strip() \
                        .rstrip('/\\') \
                        .format(game=game_title, tag=category, category=category, chall=chall_name, origin=origin_file_name)
    root_directory = re.sub(r'[*?"<>|]', '_', root_directory)

    local_path = f'{root_directory}/{file_path}'

    exist_flag = os.path.exists(local_path)
    if exist_flag and not args.overwrite and origin_file_name != 'README.md':
        print('⏩', f'{category}/{chall_name}'.ljust(24), f'already exists: {local_path}')
        return None, exist_flag

    local_dir = os.path.dirname(local_path)
    if not os.path.exists(local_dir):
        os.makedirs(local_dir)

    return local_path, exist_flag


def get_one_chall(args, id: str, headers: dict, game_title: str, portal_id: str):

    # get attachment info, including URL
    
    url_chall_id = f'{args.url}/competitions/{portal_id}/challenges/{id}'
    response = requests.get(url_chall_id, headers=headers)
    if response.status_code != 200:
        print('❌', f'Failed to get challenge info from {url_chall_id}, status code: {response.status_code}')
        return

    response_data = response.json()['data']
    name = response_data['title']
    category = response_data['categories'][0].lower() if response_data.get('categories') else 'none'
    content = response_data['description']
    attachment = response_data.get('attachment')

    # challenge README.md content
    file_path, exist_flag = get_absolute_path(args, game_title, category, name, 'README.md')
    if file_path:
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)

    if attachment is None or attachment.get('filename') is None:
        print('⏩', f'{category}/{name}'.ljust(24), 'has no attachment')
        return

    size = attachment.get('size', -1)

    if size != -1 and size > args.max_size:
        print('🤯', f'{category}/{name}'.ljust(24), f'is too large ({format(size, ",")} bytes)')
        return

    file_name = attachment['filename']

    local_path, exist_flag = get_absolute_path(args, game_title, category, name, file_name)
    if local_path is None:
        return

    # download attachment
    fp = open(local_path, 'wb')

    url_file_content = f'https://ctf.junior.nu1l.com/api/competitions/{portal_id}/challenges/{id}/attachments:download?token={args.token}'
    response = requests.get(url_file_content, headers=headers, stream=True)
    got_size = 0
    for chunk in response.iter_content(chunk_size=65536):
        if chunk:
            fp.write(chunk)
            got_size += len(chunk)
            if size != -1:
                print('\r📥',
                    f'{category}/{name}'.ljust(24),
                    '>' * min(got_size*40//size, 40) + '_' * (40 - got_size*40//size),
                    f'{got_size}/{size} bytes',
                    end='')
            else:
                print('\r📥',
                    f'{category}/{name}'.ljust(24),
                    '[in progress]',
                    end='')

    fp.close()
    print('\r✅',
        f'{category}/{name}'.ljust(24),
        f'saved to {local_path} ({format(got_size, ",")} bytes)',
        '[overwritten]' if exist_flag else '')


def arg_parse():
    parser = argparse.ArgumentParser(description='A CTF platform attachment downloader.')
    parser.add_argument('-u', '--url', type=str, help='CTF platform domain, e.g. https://ctf.junior.nu1l.com or https://ctf.junior.nu1l.com/challenges')
    parser.add_argument('-t', '--token', type=str, help='value of Local Storage user.token')
    parser.add_argument('-d', '--root-directory', type=str, default='{game}', help='default is `pwd`/{game}, which can generate "./N1CTF 2025"')
    parser.add_argument('-f', '--file-path', type=str, default='{category}/{chall}/{origin}', help='style of file path, default is {category}/{chall}/{origin}, which can generate "reverse/sign in/attachment_deadbeef.zip"; ends with "{origin}" to keep extension suffix')

    # {game}      received game title, e.g. "N1CTF 2025"
    # {category}  "direction" in lowercase, e.g. "reverse"
    # {chall}     received challenge name, e.g. "sign in"
    # {origin}    received file name, e.g. "attachment_deadbeef.zip"

    parser.add_argument('-k', '--keep-spaces', action="store_true", help='if specified, spaces in "--file-path" will not be replaced by "-"')
    parser.add_argument('-s', '--max-size', type=float, default=50.0, help='max file size in MB, larger than this will be skipped, default is 50.0, set to 0 to disable')
    parser.add_argument('-o', '--overwrite', action="store_true", help='if specified, existing files will be replaced instead of skipped')

    tag_group = parser.add_argument_group('category options, default is ALL, you can specify like -mwp')
    tag_group.add_argument('-E', '--except-mode', action="store_true", help='e.g. -p means ONLY download pwn, while -E -p means download everything else EXCEPT pwn')
    tag_group.add_argument('-m', '--misc', action='store_true')
    tag_group.add_argument('-c', '--crypto', action='store_true')
    tag_group.add_argument('-p', '--pwn', action='store_true')
    tag_group.add_argument('-w', '--web', action='store_true')
    tag_group.add_argument('-r', '--reverse', action='store_true')
    tag_group.add_argument('--blockchain', action='store_true')
    tag_group.add_argument('--forensics', action='store_true')
    tag_group.add_argument('--hardware', action='store_true')
    tag_group.add_argument('--mobile', action='store_true')
    tag_group.add_argument('--ppc', action='store_true')
    tag_group.add_argument('--ai', action='store_true')

    args = parser.parse_args()

    if args.url is None:
        args.url = input('\nEnter game URL here, e.g.\n\thttps://ctf.junior.nu1l.com\n\thttps://ctf.junior.nu1l.com/challenges\n').strip()
    args.url = args.url.split(' ')[0] \
                       .rstrip('/') \
                       .replace('/challenges', '') \
                       .replace('/leaderboard', '') \
                       .rstrip('/') + '/api'
    # https://example.com/api

    if args.token is None:
        args.token = input('\nPaste Local Storage user.token value here: ').strip()

    args.max_size = args.max_size * 1024 * 1024 if args.max_size > 0 else float('inf')

    category_list = ['misc', 'crypto', 'pwn', 'web', 'reverse', 'blockchain', 'forensics', 'hardware', 'mobile', 'ppc', 'ai']
    allowlist = category_list.copy()
    if any(getattr(args, category) for category in category_list):
        for category in category_list:
            if bool(getattr(args, category)) ^ (not args.except_mode):
                allowlist.remove(category)
    
    args.allowlist = allowlist
    # for category in category_list:
    #     delattr(args, category)

    return args


if __name__ == '__main__':
    main()
