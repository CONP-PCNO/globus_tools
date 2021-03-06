#!/usr/bin/env python

"""
Copy data from a shared endpoint to your private endpoint

Required: You create a private endpoint by either going to https://app.globus.org
navigating to Endpoints then clicking Create a personal endpoint (manual set up) or alternatively
bu following the guides available based on your OS found at https://www.globus.org/globus-connect-personal

"""

from __future__ import print_function
import os
import sys
import argparse
import json
import globus_sdk
from globus_sdk.exc import TransferAPIError
from fair_research_login import NativeClient

# Both Native App and Client Credential authentication require Client IDs.
# Create your app at developers.globus.org. The following id is for testing
# only and should not be relied upon (You should create your own app).
CLIENT_ID = '01589ab6-70d1-4e1c-b33d-14b6af4a16be'
# CLIENT_ID = '29755a43-66b8-455d-a876-e6a049a79f4c'

# Client Secret is only needed for Confidential apps. Make your app
# confidential instead of native by _not_ checking the 'Native App' checkbox
# on developers.globus./home/giuly/Documents/NeuroHub/my-conp-dataset/conp-datasetorg for your app.
# CLIENT_SECRET = 'Mako83daiAggRilawcvjNuO5JoW9EwmalTfSQEi/Wbg='
CLIENT_SECRET = ''

# Native is better for user machines, where the user is capable of hitting
# a browser to get an authentication code. Native only stores temporary
# access tokens (unless you enable refresh tokens), and does not require
# safeguarding client secrets.
#
# Client Credentials grant requires storing a 'client_secret', which does
# not require a browser or user intervention, but does require safeguarding
# the client_secret. Use Confidential on servers or trusted machines.
# *Notice*: A confidential app is a bot which acts on your behalf. You will
# need to give it permission to access your shared endpoint. You can do so
# with globus-cli via:
# globus endpoint permission create
#   --identity <client_id>@clients.auth.globus.org
#   <Your shared_endpoint UUID>:/
#   --permissions rw
# (Your bot's identity will always match the client id for your
# app + '@clients.auth.globus.org')
#
# You can also go to https://app.globus.org/endpoints?scope=shared-by-me
# and under "Identity/E-mail" set: "<client_id>@clients.auth.globus.org"
APP_AUTHENTICATORS = ('native', 'client-credentials')

# Default is native for this script.
AUTHENTICATION = 'native'

# Redirect URI specified when registering a native app
REDIRECT_URI = 'https://auth.globus.org/v2/web/auth-code'

# For this example, we will be liberal with scopes.
SCOPES = ('openid email profile '
          'urn:globus:auth:scope:transfer.api.globus.org:all')

TOKEN_FILE = 'refresh-tokens.json'

APP_NAME = 'Share Data Example App'

get_input = getattr(__builtins__, 'raw_input', input)


def load_tokens_from_file(filepath):
    """Load a set of saved tokens."""
    if not os.path.exists(filepath):
        return []
    with open(filepath, 'r') as f:
        tokens = json.load(f)

    return tokens


def save_tokens_to_file(filepath, tokens):
    """Save a set of tokens for later use."""
    with open(filepath, 'w') as f:
        json.dump(tokens, f)


def eprint(*args, **kwargs):
    """Same as print, but to standard error"""
    print(*args, file=sys.stderr, **kwargs)


def get_native_app_authorizer(client_id):
    tokens = None
    client = NativeClient(client_id=client_id, app_name=APP_NAME)
    try:
        # if we already have tokens, load and use them
        tokens = client.load_tokens(requested_scopes=SCOPES)    
    except:
        pass

    if not tokens:
        tokens = client.login(requested_scopes=SCOPES,
                              refresh_tokens=True)
        try:
            client.save_tokens(tokens)
        except:
            pass

    transfer_tokens = tokens['transfer.api.globus.org']

    auth_client = globus_sdk.NativeAppAuthClient(client_id=client_id)

    return globus_sdk.RefreshTokenAuthorizer(
            transfer_tokens['refresh_token'],
            auth_client,
            access_token=transfer_tokens['access_token'],
            expires_at=transfer_tokens['expires_at_seconds'])


def do_client_credentials_app_authentication(client_id, client_secret):
    """
    Does a client credential grant authentication and returns a
    dict of tokens keyed by service name.
    """
    client = globus_sdk.ConfidentialAppAuthClient(
            client_id=client_id,
            client_secret=client_secret)
    token_response = client.oauth2_client_credentials_tokens()

    return token_response.by_resource_server


def get_confidential_app_authorizer(client_id, client_secret):
    tokens = do_client_credentials_app_authentication(
            client_id=client_id,
            client_secret=client_secret)
    transfer_tokens = tokens['transfer.api.globus.org']
    transfer_access_token = transfer_tokens['access_token']

    return globus_sdk.AccessTokenAuthorizer(transfer_access_token)


def share_data(args):

    user_source_endpoint = args.source_endpoint
    user_destination_endpoint = args.destination_endpoint
    if not user_destination_endpoint:
        eprint('Invalid shared endpoint')
        sys.exit(1)

    user_source_path = args.source_path
    user_destination_path = args.destination_path
    if not user_source_path.startswith('/'):
        eprint('Source path must be absolute')
        sys.exit(1)
    if not user_destination_path.startswith('/'):
        eprint('Destination path must be absolute')
        sys.exit(1)

    if args.auth == 'native':
        # get an authorizer if it is a Native App
        authorizer = get_native_app_authorizer(client_id=CLIENT_ID)
    elif args.auth == 'client-credentials':
        secret = args.client_secret or CLIENT_SECRET
        if not secret:
            eprint('--auth client-credentials chosen, but no secret provided!'
                   ' Set "--client-secret <your secret>"'
                   )
            sys.exit(1)
        # get an authorizer if it is a Confidential App
        authorizer = get_confidential_app_authorizer(client_id=CLIENT_ID,
                                                     client_secret=secret
        )
    else:
        raise ValueError('Invalid Authenticator, this script only understands '
                         'Native and Client Credential')

    # # look for an identity uuid for the specified identity username
    # username_uuid = None
    # if args.user_uuid:
    #     print(args.user_uuid)
    #     ac = globus_sdk.AuthClient(authorizer=authorizer)
    #     r = ac.get_identities(usernames=args.user_uuid)
    #     print(r)
    #     if not len(r['identities']):
    #         eprint('No such identity username \'{}\''.format(args.user_uuid))
    #         exit(1)
    #     username_uuid = r['identities'][0]['id']

    # create a TransferClient object
    tc = globus_sdk.TransferClient(authorizer=authorizer)

    # check if a destination directory exists at all
    try:
        tc.operation_ls(user_destination_endpoint, path=user_destination_path)
    except TransferAPIError as e:
        eprint(e)
        sys.exit(1)

    dirname, leaf = os.path.split(user_source_path)
    if leaf == '':
        _, leaf = os.path.split(dirname)
    destination_directory = os.path.join(user_destination_path, leaf) + '/'

    """
    check if a directory with the same name was already transferred to the
    destination path if it was and --delete option is specified, delete the
    directory
    """
    try:
        tc.operation_ls(user_destination_endpoint, path=destination_directory)
        if not args.delete:
            eprint('Destination directory exists. Delete the directory or '
                   'use --delete option')
            sys.exit(1)
        print('Destination directory, {}, exists and will be deleted'
              .format(destination_directory))
        ddata = globus_sdk.DeleteData(
                tc,
                user_destination_endpoint,
                label='Share Data Example',
                recursive=True)
        ddata.add_item(destination_directory)
        print('Submitting a delete task')
        task = tc.submit_delete(ddata)
        print('\ttask_id: {}'.format(task['task_id']))
        tc.task_wait(task['task_id'])
    except TransferAPIError as e:
        if e.code != u'ClientError.NotFound':
            eprint(e)
            sys.exit(1)

    # create a destination directory
    try:
        print('Creating destination directory {}'
              .format(destination_directory))
        tc.operation_mkdir(user_destination_endpoint, destination_directory)
    except TransferAPIError as e:
        eprint(e)
        sys.exit(1)

    # # grant group/user read access to the destination directory
    # if args.user_uuid:
    #     rule_data = {
    #         "DATA_TYPE": "access",
    #         "principal_type": "identity",
    #         "principal": args.user_uuid,
    #         "path": destination_directory,
    #         "permissions": "r",
    #     }
    #
    #     try:
    #         print('Granting user, {}, read access to the destination directory'
    #               .format(args.user_uuid))
    #         tc.add_endpoint_acl_rule(user_destination_endpoint, rule_data)
    #     except TransferAPIError as e:
    #         if e.code != u'Exists':
    #             eprint(e)
    #             sys.exit(1)
    #
    # if username_uuid:
    #     rule_data = {
    #         "DATA_TYPE": "access",
    #         "principal_type": "identity",
    #         "principal": username_uuid,
    #         "path": destination_directory,
    #         "permissions": "r",
    #     }
    #
    #     try:
    #         print('Granting user, {}, read access to the destination directory'
    #               .format(username_uuid))
    #         tc.add_endpoint_acl_rule(user_destination_endpoint, rule_data)
    #     except TransferAPIError as e:
    #         if e.code != u'Exists':
    #             eprint(e)
    #             sys.exit(1)
    #
    # if args.group_uuid:
    #     rule_data = {
    #         "DATA_TYPE": "access",
    #         "principal_type": "group",
    #         "principal": args.group_uuid,
    #         "path": destination_directory,
    #         "permissions": "r",
    #     }
    #
    #     try:
    #         print('Granting group, {}, read access to '
    #               .format(args.group_uuid))
    #         tc.add_endpoint_acl_rule(user_destination_endpoint, rule_data)
    #     except TransferAPIError as e:
    #         if e.code != u'Exists':
    #             eprint(e)
    #             sys.exit(1)

    # transfer data - source directory recursively
    tdata = globus_sdk.TransferData(tc,
                                    user_source_endpoint,
                                    user_destination_endpoint,
                                    label='Share Data Example')
    tdata.add_item(user_source_path, destination_directory, recursive=True)
    try:
        print('Submitting a transfer task')
        task = tc.submit_transfer(tdata)
    except TransferAPIError as e:
        eprint(e)
        sys.exit(1)
    print('\ttask_id: {}'.format(task['task_id']))
    print('You can monitor the transfer task programmatically using Globus SDK'
          ', or go to the Web UI, https://app.globus.org/activity/{}.'
          .format(task['task_id']))


if __name__ == '__main__':

    parser = argparse.ArgumentParser(
        description='Copy data from a shared endpoint to your private one'
    )
    parser.add_argument(
        '--source-endpoint',
        help='Source Endpoint UUID where data is stored.'
    )
    parser.add_argument(
        '--destination-endpoint',
        help='The place you will transfer your data to'
    )
    parser.add_argument(
        '--source-path',
    )
    parser.add_argument(
        '--destination-path',
    )
    # parser.add_argument(
    #     '--client-id',
    #     help='Your App Client ID'
    # )
    parser.add_argument(
        '--user-uuid',
        help='UUID of a user to whom data are transferred')
    parser.add_argument(
        '--delete', action='store_true',
        help='Delete a destination directory if already exists before '
        'transferring data')
    parser.add_argument('--auth', choices=APP_AUTHENTICATORS,
                        default=AUTHENTICATION)
    parser.add_argument('--client-secret')
    args = parser.parse_args()

    share_data(args)
