"""Utility functions for working with botocore"""

#  Copyright (c) NCC Group and Erik Steringer 2019. This file is part of Principal Mapper.
#
#      Principal Mapper is free software: you can redistribute it and/or modify
#      it under the terms of the GNU Affero General Public License as published by
#      the Free Software Foundation, either version 3 of the License, or
#      (at your option) any later version.
#
#      Principal Mapper is distributed in the hope that it will be useful,
#      but WITHOUT ANY WARRANTY; without even the implied warranty of
#      MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#      GNU Affero General Public License for more details.
#
#      You should have received a copy of the GNU Affero General Public License
#      along with Principal Mapper.  If not, see <https://www.gnu.org/licenses/>.

from typing import Optional

import boto3.session


def get_session(profile_arg: Optional[str], role_arg: Optional[str]) -> boto3.session.Session:
    """Returns a boto3 Session object taking into consideration Env-vars, etc.

    Tries to follow order from: https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html
    """
    # command-line args (--profile)
    if profile_arg is not None:
        result = boto3.session.Session(profile_name=profile_arg)
    # command-line args (--role)
    elif role_arg is not None:
        stsclient = boto3.client('sts')
        token = stsclient.assume_role(RoleArn=role_arg, RoleSessionName='PMapper')
        result = boto3.session.Session(aws_session_token=token)
    else:  # pull from environment vars / metadata
        result = boto3.session.Session()
        stsclient = result.client('sts')

    stsclient.get_caller_identity()  # raises error if it's not workable
    return result

def assume_role(role_arg: Optional[str]) -> boto3.session.Session:
    """Returns a boto3 Session object taking into consideration Env-vars, etc.

    Tries to follow order from: https://docs.aws.amazon.com/cli/latest/userguide/cli-chap-configure.html
    """
    # command-line args (--profile)
    if role_arg is not None:
        result = boto3.session.Session(profile_name=profile_arg)
    else:  # pull from environment vars / metadata
        result = boto3.session.Session()

    stsclient = result.client('sts')
    stsclient.get_caller_identity()  # raises error if it's not workable
    return result
