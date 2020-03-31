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

"""
The following is an example of how to use Principal Mapper like a library in a script. This code pulls graph data for
an AWS account, runs analysis on it, then prints the output of the analysis. The graph data is not stored on-disk.

"""

import argparse

from principalmapper.analysis import find_risks
from principalmapper.graphing import graph_actions
# from principalmapper.graphing import gathering
from principalmapper.graphing.edge_identification import checker_map
from principalmapper.util import botocore_tools


def main():
    """Body of the script."""
    # Handle input args --profile and --format
    parser = argparse.ArgumentParser()
    parser.add_argument('--profile', required=False)
    parser.add_argument('--role', required=False)
    parser.add_argument('--format', default='text', choices=['text', 'json'])
    parsed_args = parser.parse_args()


    # Create session using the default search order + optional assumed role or a config profile
    #session = botocore_tools.get_session()
    # session = botocore_tools.get_session(parsed_args.role)
    session = botocore_tools.get_session(parsed_args.profile)

    # Generate the graph (such as with `pmapper graph --create`)
    # graph_obj = gathering.create_graph(session, checker_map.keys())  # gets a Graph object without printing info
    graph_obj = graph_actions.create_new_graph(session, checker_map.keys())

    # Print out or write identified findings (such as with `pmapper analysis`)
    find_risks.gen_findings_and_print(graph_obj, parsed_args.format)
    # find_risks.gen_findings_to_file(graph_obj, parsed_args.format, outfile)


if __name__ == '__main__':
    main()
