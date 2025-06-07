import argparse
import os
import re
import requests
import sys
from urllib3.exceptions import NewConnectionError, MaxRetryError
# import traceback

class RemoteURLPointsToHTML(Exception):
    def __init__(self, message="The remote URL points to an HTML document"):
        self.message = message
        super().__init__(self.message)

def main():
    args = arg_parse()
    # print(args)
    get_challs(args)

def get_challs(args):
    headers = {
        'Cookie': f'GZCTF_Token={args.token}',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0',
    }

    # get game title
    response = requests.get(args.url, headers=headers)
    if response.status_code != 200:
        print('❌', f'Failed to get game title from {args.url}, status code: {response.status_code}')
        sys.exit(1)

    game_info = response.json()
    game_title = game_info['title']

    # get challenge list
    url_details = args.url + '/details'
    response = requests.get(url_details, headers=headers)
    if response.status_code != 200:
        print('❌', f'Failed to get challenge list from {url_details}, status code: {response.status_code}')
        sys.exit(1)

    response_data = response.json()
    for group in response_data['challenges']:
        if group.lower() not in args.allowlist:
            continue
        for object in response_data['challenges'][group]:
            try:
                get_one_chall(args, object["id"], headers, game_title)
            except (MaxRetryError, NewConnectionError, ConnectionError, OSError):
                print('❌', f'Failed to get challenge {object["id"]} file, try to save the download URL...')
                get_one_chall_download_error(args, object["id"], headers, game_title)
            except RemoteURLPointsToHTML:
                print('❌','The remote URL points to an HTML document, try to save the download URL...')
                get_one_chall_download_error(args, object["id"], headers, game_title)
            except Exception as e:
                print('❌', f'Failed to get challenge {object["id"]}, error: {e}')
                # traceback.print_exc()

    print('🎉', 'All done.')

def get_one_chall(args, id: int, headers: dict, game_title: str):

    # get attachment info, including URL
    
    url_chall_id = f'{args.url}/challenges/{id}'
    response = requests.get(url_chall_id, headers=headers)
    if response.status_code != 200:
        print('❌', f'Failed to get challenge info from {url_chall_id}, status code: {response.status_code}')
        return

    response_data = response.json()
    name = response_data['title']
    category = (response_data.get('category') or response_data.get('tag')).lower()
    remote_path = response_data['context']['url']         # may be relative or absolute
    info_size = response_data['context']['fileSize']      # may be null
    content = response_data['content']
    chal_type = response_data['type']
    content += f'\n\nChallenge Type: {chal_type}'
    cant_download = False

    if remote_path is None:
        print('⏩', f'{category}/{name}'.ljust(24), 'has no attachment')
        content+=f' \n\nthis challenge has no attachment'
        cant_download = True

    if info_size is not None and info_size > args.max_size:
        print('🤯', f'{category}/{name}'.ljust(24), f'is too large ({format(info_size, ",")} bytes)')
        content+=f'\n\nthis attachment is too large ({format(info_size, ",")} bytes), try use the url in download_URL.txt'
        cant_download = True
    # get attachment file name and size
    if cant_download == False:
        
        if re.match(r'^https?://', remote_path):
            url_file_content = remote_path
        else:
            url_file_content = re.sub(r'/api/game/.*$', remote_path, args.url)
        headers_range = headers.copy()
        headers_range['Range'] = 'bytes=0-10'

        response = requests.get(url_file_content, headers=headers_range, stream=True)
        if response.status_code not in (200, 206):
            print('❌', f'{category}/{name}'.ljust(24), f'Failed to get attachment info from {url_file_content}, status code: {response.status_code}')
            return
        
        if 'text/html' in response.headers.get('Content-Type', ''):
            print('❔', f'{category}/{name}'.ljust(24), f'Content-Type: text/html, URL: {url_file_content}')
            # not return
            raise RemoteURLPointsToHTML

        origin_size = int(response.headers.get('Content-Range', '0-0/-1').split('/')[-1])
        if origin_size == -1:
            try:
                origin_size = int(response.headers['Content-Length'])
            except:
                origin_size = -1
        if origin_size != -1 and origin_size > args.max_size:
            print('🤯', f'{category}/{name}'.ljust(24), f'is too large ({format(origin_size, ",")} bytes)')
            return
        
        size = origin_size if info_size is None else max(info_size, origin_size)

        origin_file_name = response.headers.get('Content-Disposition', 'filename=NONE') \
                                        .split('filename=')[1] \
                                        .split(';')[0] \
                                        .strip('"')
        if origin_file_name == 'NONE':
            origin_file_name = url_file_content.split('/')[-1]

    # format path string, check file existence, and create directory
    if cant_download == True:
        origin_file_name = "tmp_file_name"
    file_path = args.file_path \
                    .strip() \
                    .lstrip('/\\') \
                    .format(game=game_title, tag=category, category=category, chall=name, origin=origin_file_name)
    if not args.keep_spaces:
        file_path = re.sub(r'\s+', '-', file_path)
    file_path = re.sub(r'[:*?"<>|]', '_', file_path)

    root_directory = args.root_directory \
                         .strip() \
                         .rstrip('/\\') \
                         .format(game=game_title, tag=category, category=category, chall=name, origin=origin_file_name)
    root_directory = re.sub(r'[*?"<>|]', '_', root_directory)
    
    local_path = f'{root_directory}/{file_path}'

    exist_flag = os.path.exists(local_path)
    if exist_flag and not args.overwrite:
        print('⏩', f'{category}/{name}'.ljust(24), f'already exists: {local_path}')
        return

    local_dir = os.path.dirname(local_path)
    if not os.path.exists(local_dir):
        os.makedirs(local_dir)

    dir_path = '/'.join(file_path.split('/')[:-1])
    with open(f'{root_directory}/{dir_path}/description.txt', 'w', encoding='utf-8') as f:
        f.write(content)
    # download attachment
    if cant_download == True:
        return
    fp = open(local_path, 'wb')

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

def get_one_chall_download_error(args, id: int, headers: dict, game_title: str):

    # get attachment info, including URL
    url_chall_id = f'{args.url}/challenges/{id}'
    response = requests.get(url_chall_id, headers=headers)
    if response.status_code != 200:
        print('❌', f'Failed to get challenge info from {url_chall_id}, status code: {response.status_code}')
        return

    response_data = response.json()
    name = response_data['title']
    category = (response_data.get('category') or response_data.get('tag')).lower()
    remote_path = response_data['context']['url']         # may be relative or absolute
    info_size = response_data['context']['fileSize']      # may be null
    content = response_data['content']
    chal_type = response_data['type']
    content += f'\n\nChallenge Type: {chal_type}'
    cant_download = True

    if remote_path is None:
        print('⏩', f'{category}/{name}'.ljust(24), 'has no attachment')
        content+=f' \n\nthis challenge has no attachment'
        cant_download = True

    if info_size is not None and info_size > args.max_size:
        print('🤯', f'{category}/{name}'.ljust(24), f'is too large ({format(info_size, ",")} bytes)')
        content+=f'\n\nthis attachment is too large ({format(info_size, ",")} bytes), try use the url in download_URL.txt'
        cant_download = True
    # get attachment file name and size

    if cant_download == False:
        if re.match(r'^https?://', remote_path):
            url_file_content = remote_path
        else:
            url_file_content = re.sub(r'/api/game/.*$', remote_path, args.url)
        headers_range = headers.copy()
        headers_range['Range'] = 'bytes=0-10'

        response = requests.get(url_file_content, headers=headers_range, stream=True)
        if response.status_code not in (200, 206):
            print('❌', f'{category}/{name}'.ljust(24), f'Failed to get attachment info from {url_file_content}, status code: {response.status_code}')
            return
        
        if 'text/html' in response.headers.get('Content-Type', ''):
            print('❔', f'{category}/{name}'.ljust(24), f'Content-Type: text/html, URL: {url_file_content}')
            # not return

        origin_size = int(response.headers.get('Content-Range', '0-0/-1').split('/')[-1])
        if origin_size == -1:
            try:
                origin_size = int(response.headers['Content-Length'])
            except:
                origin_size = -1
        if origin_size != -1 and origin_size > args.max_size:
            print('🤯', f'{category}/{name}'.ljust(24), f'is too large ({format(origin_size, ",")} bytes)')
            return
        
        size = origin_size if info_size is None else max(info_size, origin_size)

        origin_file_name = response.headers.get('Content-Disposition', 'filename=NONE') \
                                        .split('filename=')[1] \
                                        .split(';')[0] \
                                        .strip('"')
        if origin_file_name == 'NONE':
            origin_file_name = url_file_content.split('/')[-1]

    # format path string, check file existence, and create directory

    if cant_download == True:
        origin_file_name = "tmp_file_name"
    file_path = args.file_path \
                    .strip() \
                    .lstrip('/\\') \
                    .format(game=game_title, tag=category, category=category, chall=name, origin=origin_file_name)
    if not args.keep_spaces:
        file_path = re.sub(r'\s+', '-', file_path)
    file_path = re.sub(r'[:*?"<>|]', '_', file_path)

    root_directory = args.root_directory \
                         .strip() \
                         .rstrip('/\\') \
                         .format(game=game_title, tag=category, category=category, chall=name, origin=origin_file_name)
    root_directory = re.sub(r'[*?"<>|]', '_', root_directory)
    
    local_path = f'{root_directory}/{file_path}'

    exist_flag = os.path.exists(local_path)
    if exist_flag and not args.overwrite:
        print('⏩', f'{category}/{name}'.ljust(24), f'already exists: {local_path}')
        return

    local_dir = os.path.dirname(local_path)
    if not os.path.exists(local_dir):
        os.makedirs(local_dir)
    # print(file_path)
    save_dir = f'{root_directory}/' + '/'.join(file_path.split('/')[:-1])
    # dir_path = 
    with open(f'{save_dir}/description.txt', 'w', encoding='utf-8') as f:
        f.write(content)
    with open(f'{save_dir}/download_URL.txt', 'w', encoding='utf-8') as f:
        f.write(remote_path)
    # download attachment
    print('\r✅',
          f'{category}/{name}'.ljust(24),
          f'saved download URL to {save_dir}/download_URL.txt',
          '[overwritten]' if exist_flag else '')

def arg_parse():
    parser = argparse.ArgumentParser(description='A GZ::CTF attachment downloader.')
    parser.add_argument('-u', '--url', type=str, help='GZ::CTF game URL, e.g. https://example.com/games/1/challenges or https://example.com/games/1')
    parser.add_argument('-t', '--token', type=str, help='value of Cookie GZCTF_Token')
    parser.add_argument('-d', '--root-directory', type=str, default='{game}', help='default is `pwd`/{game}, which can generate "./LRCTF 2024"')
    parser.add_argument('-f', '--file-path', type=str, default='{category}/{chall}/{origin}', help='style of file path, default is {category}/{chall}/{origin}, which can generate "misc/sign in/attachment_deadbeef.zip"; ends with "{origin}" to keep extension suffix')

    # {game}      received game title, e.g. "BaseCTF 2024"
    # {category}  "direction" in lowercase, e.g. "misc"
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
        args.url = input('\nEnter game URL here, e.g.\n\thttps://example.com/games/1/challenges\n\thttps://example.com/games/1\n').strip()
    args.url = args.url.split(' ')[0] \
                       .replace('/challenges', '') \
                       .replace('/scoreboard', '') \
                       .replace('/games/', '/api/game/') \
                       .rstrip('/')
    # https://example.com/api/game/1

    if args.token is None:
        args.token = input('\nPaste GZCTF_Token Cookie value here: ').strip()
    args.token = args.token.replace('GZCTF_Token=', '').strip()

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
