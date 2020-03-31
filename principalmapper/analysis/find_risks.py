"""Python code for identifying risks using a Graph generated by Principal Mapper. The findings are tracked using
dictionary objects with the format:
{
   "title": <str>,
   "severity": "Low|Medium|High",
   "impact": <str>,
   "description": <str>,
   "recommendation": <str>
}
"""


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

import datetime as dt
import json
import os
from typing import List

import principalmapper
from principalmapper.analysis.finding import Finding
from principalmapper.analysis.report import Report
from principalmapper.common import Graph, Node
from principalmapper.querying import query_interface
from principalmapper.querying.presets.privesc import can_privesc
from principalmapper.util import arns


def gen_findings_and_print(graph: Graph, formatting: str) -> None:
    """Generates findings of risk, prints them out."""

    report = gen_report(graph)

    if formatting == 'text':
        print_report(report)
    else:  # format == 'json'
        print(json.dumps(report.as_dictionary(), indent=4))

def gen_findings_to_file(graph: Graph, formatting: str, file: str) -> None:
    """Generates findings of risk, writes them to a file."""

    report = gen_report(graph)
    content = report.as_dictionary() # default format == text

    path = os.path.abspath(os.curdir() + file)
    if not os.path.isfile(path): # default file == /dev/null
        path = os.devnull

    if formatting == 'json':
        content = json.dumps(content, indent=4)

    with open(path, 'w') as f:
        f.write(content)

def gen_report(graph: Graph) -> Report:
    """Generates a Report object with findings and metadata about report-generation"""
    findings = gen_all_findings(graph)
    return Report(
        graph.metadata['account_id'],
        dt.datetime.now(dt.timezone.utc),
        findings,
        'Findings identified using Principal Mapper ({}) from NCC Group: https://github.com/nccgroup/PMapper'.format(
            principalmapper.__version__
        )
    )


def gen_all_findings(graph: Graph) -> List[Finding]:
    """Generates findings of risk, returns a list of finding-dictionary objects."""
    result = []
    result.extend(gen_privesc_findings(graph))
    result.extend(gen_mfa_actions_findings(graph))
    # TODO: result.extend(gen_mfa_evasion_finding(graph))  # policies that allow attackers to change MFA devices
    result.extend(gen_overprivileged_function_findings(graph))
    result.extend(gen_overprivileged_instance_profile_findings(graph))
    result.extend(gen_overprivileged_stack_findings(graph))
    return result


def gen_privesc_findings(graph: Graph) -> List[Finding]:
    """Generates findings related to privilege escalation risks."""
    result = []

    node_path_list = []

    for node in graph.nodes:
        privesc_res, edge_list = can_privesc(graph, node)
        if privesc_res:
            node_path_list.append((node, edge_list))

    if len(node_path_list) > 0:
        description_preamble = 'In AWS, IAM Principals such as IAM Users or IAM Roles have their permissions defined ' \
                               'using IAM Policies. These policies describe different actions, resources, and ' \
                               'conditions where the principal can make a given API call to a service.\n\n' \
                               'The following principals could escalate privileges:\n\n'

        description_body = ''
        for node, edge_list in node_path_list:
            end_of_list = edge_list[-1].destination
            description_body += '* {} can escalate privileges by accessing the administrative principal {}:\n'.format(
                node.searchable_name(), end_of_list.searchable_name())
            for edge in edge_list:
                description_body += '   * {}\n'.format(edge.describe_edge())
            description_body += '\n'

        result.append(Finding(
            'IAM {} Can Escalate Privileges'.format('Principals' if len(node_path_list) > 1 else 'Principal'),
            'High',
            'A lower-privilege IAM User or Role is able to gain administrative privileges. This could lead to the '
            'lower-privilege principal being used to compromise the account\'s resources.',
            description_preamble + description_body,
            'Review the IAM Policies that are applicable to the affected IAM User(s) or Role(s). Either reduce the '
            'permissions of the administrative principal(s), or reduce the permissions of the principal(s) that can '
            'access the administrative principals.'
        ))

    return result


def gen_mfa_actions_findings(graph: Graph) -> List[Finding]:
    """Generates findings related to risk from IAM Users able to call sensitive actions without needing MFA."""
    result = []
    affected_users = []
    for node in graph.nodes:
        if ':user/' in node.arn and node.is_admin and node.access_keys > 0:
            # Check if the given admin user with access keys can call sensitive actions without MFA
            # TODO: Check for other actions in here?
            actions = ['iam:CreateUser', 'iam:CreateRole', 'iam:CreateGroup', 'iam:PutUserPolicy', 'iam:PutRolePolicy',
                       'iam:PutGroupPolicy', 'iam:AttachUserPolicy', 'iam:AttachRolePolicy', 'iam:AttachGroupPolicy',
                       'sts:AssumeRole']
            if _can_call_without_mfa(node, actions):
                affected_users.append(node)

    if len(affected_users) > 0:
        description_preamble = 'In AWS, IAM Users can be configured to use an MFA device. When an IAM User has MFA ' \
                               'enabled, they are required to provide the second factor of authentication when they ' \
                               'log in to the AWS Console. However, unless there is a specific IAM policy attached ' \
                               'to the user, they will not need to provide a second factor of authentication when ' \
                               'making API calls.\n\nThe following administrative IAM Users have at least one set of ' \
                               'access keys, and can call sensitive actions to alter permissions or add users ' \
                               'without using a second factor of authentication:\n\n'

        description_body = ''
        for node in affected_users:
            description_body += '* {}\n'.format(node.searchable_name())

        result.append(Finding(
            'Administrative IAM {} Can Call Sensitive Actions Without MFA'.format(
                'Users' if len(affected_users) > 1 else 'User'
            ),
            'Medium',
            'An adminstrative IAM User is able to call sensitive actions, such as creating more principals or '
            'modifying permissions, without using MFA.',
            description_preamble + description_body,
            'Implement and attach an IAM Policy to the noted user(s) that rejects requests when MFA is not used.'
        ))

    return result


def _can_call_without_mfa(node: Node, actions: List[str]) -> bool:
    """Returns true if node can call sensitive action without MFA"""
    for action in actions:
        auth, needmfa = query_interface.local_check_authorization_handling_mfa(
            node,
            action,
            '*',
            {}
        )
        if auth and not needmfa:
            return True
    return False


def gen_overprivileged_instance_profile_findings(graph: Graph) -> List[Finding]:
    """Generates findings related to risk from EC2 instances being loaded with overprivileged instance profiles."""
    result = []
    affected_roles = []
    for node in graph.nodes:
        if ':role/' in node.arn and node.is_admin and node.instance_profile is not None:
            affected_roles.append(node)

    if len(affected_roles) > 0:
        description_preamble = 'In AWS, EC2 instances can be given an instance profile. These instance profiles ' \
                               'are associated with an IAM Role, and grants access to the permissions of the IAM ' \
                               'Role. Because EC2 instances are at a higher risk of exposure and compromise, both ' \
                               'to external attackers and authorized users in the AWS account, they should not have ' \
                               'access to administrative privileges. The following IAM Roles have administrative ' \
                               'permissions and are associated with an instance profile:\n\n'

        description_body = ''
        for node in affected_roles:
            description_body += '* {}\n'.format(node.searchable_name())

        result.append(Finding(
            'Instance {} Administrator Privileges'.format(
                'Profiles Have' if len(affected_roles) > 1 else 'Profile Has'
            ),
            'High',
            'If an instance with the noted instance profile(s) is compromised, then the AWS account as a whole is at '
            'risk of compromise.',
            description_preamble + description_body,
            'Reduce the scope of permissions attached to the noted instance profile(s).'
        ))

    return result


def gen_overprivileged_function_findings(graph: Graph) -> List[Finding]:
    """Generates findings related to risk from Lambda functions being loaded with overprivileged roles"""
    result = []
    affected_roles = []
    for node in graph.nodes:
        if ':role/' in node.arn and node.is_admin:
            if query_interface.resource_policy_authorization('lambda.amazonaws.com', arns.get_account_id(node.arn),
                                                             node.trust_policy, 'sts:AssumeRole', node.arn, {}, False)\
                    == query_interface.ResourcePolicyEvalResult.SERVICE_MATCH:
                affected_roles.append(node)

    if len(affected_roles) > 0:
        description_preamble = 'In AWS, Lambda functions can be assigned an IAM Role to use during execution. These ' \
                               'IAM Roles give the function access to call the AWS API with the permissions of the ' \
                               'IAM Role, depending on the policies attached to it. If the Lambda function can be ' \
                               'compromised, and the attacker can alter the code it executes, the attacker could ' \
                               'make AWS API calls with the IAM Role\'s permissions. The following IAM Roles have ' \
                               'administrative privileges, and can be passed to Lambda functions:\n\n'

        description_body = ''
        for node in affected_roles:
            description_body += '* {}\n'.format(node.searchable_name())

        result.append(Finding(
            'IAM Roles Available to Lambda Functions Have Administrative Privileges' if len(affected_roles) > 1 else
            'IAM Role Available to Lambda Functions Has Administrative Privileges',
            'Medium',
            'If an attacker can inject code or commands into the function, or if a lower-privileged principal can '
            'alter the function, the AWS account as a whole could be compromised.',
            description_preamble + description_body,
            'Reduce the scope of permissions attached to the noted IAM Role(s).'
        ))

    return result


def gen_overprivileged_stack_findings(graph: Graph) -> List[Finding]:
    """Generates findings related to risk from CloudFormation stacks being loaded with overprivileged roles"""
    result = []
    affected_roles = []
    for node in graph.nodes:
        if ':role/' in node.arn and node.is_admin:
            if query_interface.resource_policy_authorization('cloudformation.amazonaws.com',
                                                             arns.get_account_id(node.arn), node.trust_policy,
                                                             'sts:AssumeRole', node.arn, {}, False) == \
                    query_interface.ResourcePolicyEvalResult.SERVICE_MATCH:
                affected_roles.append(node)

    if len(affected_roles) > 0:
        description_preamble = 'In AWS, CloudFormation stacks can be given an IAM Role. When a stack has an IAM ' \
                               'Role, it can use that IAM Role to make AWS API calls to create the resources ' \
                               'defined in the template for that stack. If the IAM Role has administrator access ' \
                               'to the account, and an attacker is able to make the right CloudFormation API calls, ' \
                               'they would be able to use the IAM Role to escalate privileges and compromise the ' \
                               'account as a whole. The following IAM Roles can be used in CloudFormation and ' \
                               'have administrative privileges:\n\n'

        description_body = ''
        for node in affected_roles:
            description_body += '* {}\n'.format(node.searchable_name())

        result.append(Finding(
            'IAM Roles Available to CloudFormation Stacks Have Administrative Privileges' if len(affected_roles) > 1
            else 'IAM Role Available to CloudFormation Stacks Has Administrative Privileges',
            'Low',
            'If an attacker has the right permissions in the AWS Account, they can grant themselves adminstrative '
            'access to the account to compromise the account.',
            description_preamble + description_body,
            'Reduce the scope of permissions attached to the noted IAM Role(s).'
        ))

    return result


def print_report(report: Report) -> None:
    """Given a report, uses print() to print out their contents in a Markdown format."""

    # Preamble
    print('----------------------------------------------------------------')
    print('# Principal Mapper Findings')
    print()
    print('Findings identified in AWS account {}'.format(report.account))
    print()
    print('Date and Time: {}'.format(report.date_and_time.isoformat()))
    print()
    print(report.source)

    # Findings
    if len(report.findings) == 0:
        print()
        print("None found.")
        print()
    else:
        for finding in report.findings:
            print("## {}\n\n### Severity\n\n{}\n\n### Impact\n\n{}\n\n### Description\n\n{}\n\n### Recommendation\n\n{}"
                  "\n\n".format(finding.title, finding.severity, finding.impact, finding.description,
                                finding.recommendation)
                  )

    # Footer

    print()
    print('----------------------------------------------------------------')

