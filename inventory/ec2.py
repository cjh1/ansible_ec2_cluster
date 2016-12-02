#!/usr/bin/env python

###############################################################################
#  Copyright 2016 Kitware Inc.
#
#  Licensed under the Apache License, Version 2.0 ( the "License" );
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
###############################################################################

import boto3.ec2
from itertools import groupby
import json
import os
import yaml

class EC2Provider(object):
    def __init__(self, profile):

        self.girder_profile_id = profile.get('_id', None)

        for key, value in profile.items():
            setattr(self, key, value)

    def _get_instance_vars(self, instance):
        '''
        Determine what to set as host specific variables in the dynamic
        inventory output. instance is a boto.ec2.instance.
        '''
        return {
            'instance_id': instance.id,
            'private_ip': instance.private_ip_address,
            'public_ip': instance.public_ip_address,
        }

    def _instances_by_name(self, instances):
        '''
        Return a generator of the instances grouped by their
        ec2_pod_instance_name tag.
        '''
        return groupby(instances,
                       key=lambda instance:
                       {i['Key']: i['Value']
                        for i in instance.tags}['ec2_pod_instance_name'])

    def get_inventory(self, cluster_id):
        '''
        Retrieve the inventory from a set of regions in an Ansible Dynamic
        Inventory compliant format (see
        http://docs.ansible.com/ansible/developing_inventory.html#script-conventions).

        Instances are filtered through instance_filter, grouped by the
        ec2_pod_instance_name tag, and contain host specific variables
        according to get_instance_vars.
        '''
        inventory = {}
        instances = []

        region_instances = self.ec2.instances.filter(Filters=[
            {'Name': 'tag:ec2_pod', 'Values': [cluster_id]},
            {'Name': 'instance-state-name', 'Values': ['running']}])

        instances += [i for i in region_instances]

        # Build up main inventory, instance_name is something like 'head' or
        # 'node' instance_name_instances are the boto.ec2.instance objects
        # that have an ec2_pod_instance_name tag value of instance_name
        for (instance_name, instance_name_instances) \
                in self._instances_by_name(instances):

            inventory[instance_name] = {
                'hosts': [x.public_ip_address
                          for x in instance_name_instances]
            }

        # Build up _meta/hostvars for individual instances
        hostvars = {instance.public_ip_address:
                    self._get_instance_vars(instance)
                    for instance in instances}

        if hostvars:
            inventory['_meta'] = {
                'hostvars': hostvars
            }

        return inventory

    def running_instances(self, cluster_id):
        return len([host for host in self.get_instances(cluster_id).keys()
                    if host != '_meta'])

    def get_master_instance(self, cluster_id):
        cluster_id = str(cluster_id)

        instances = list(self.ec2.instances.filter(Filters=[
            {'Name': 'tag:ec2_pod_instance_name', 'Values': ['head']},
            {'Name': 'tag:ec2_pod', 'Values': [cluster_id]},
            {'Name': 'instance-state-name', 'Values': ['running']}]))

        if len(instances) == 0:
            raise Exception('No master node could be found!')
        if len(instances) > 1:
            raise Exception('More than one master node was found!')

        return self._get_instance_vars(instances[0])

    def get_volumes(self):
        pass

    @property
    def ec2(self):
        try:
            return boto3.resource(
                'ec2',
                self.regionName,
                aws_access_key_id=self.accessKeyId,
                aws_secret_access_key=self.secretAccessKey)
        except AttributeError:
            return boto3.resource(
                'ec2',
                self.region,
                aws_access_key_id=self.accessKeyId,
                aws_secret_access_key=self.secretAccessKey)

    def _get_volume(self, girder_volume, refresh_cache=False):
        volume_id = parse('ec2.id').find(girder_volume)[0].value

        if not volume_id:
            return None

        try:
            if refresh_cache:
                self._volume_cache[volume_id] = self.ec2.Volume(volume_id)

            return self._volume_cache[volume_id]
        except KeyError:
            self._volume_cache[volume_id] = self.ec2.Volume(volume_id)

        return self._volume_cache[volume_id]

    def get_machine_images(self, name=None, owner=None, tags=None, **kwargs):
        filters = []

        if name is not None:
            filters.append({
                'Name': 'name',
                'Values': [name]
            })

        if owner is not None:
            filters.append({
                'Name': 'owner-id',
                'Values': [owner]
            })

        if tags is not None:
            for (key, value) in tags.iteritems():
                filters.append({
                    'Name': 'tag:%s' % key,
                    'Values': value if isinstance(value, list) else [value]
                })

        r = self.client.describe_images(Filters=filters)

        return [{'image_id': image['ImageId']} for image in r['Images']]

    # Proxy these through to the boto3 client
    # Note: these are left over from the original volume
    #       implementation They may not make sense in terms
    #       of a general cloud provider API.

    @property
    def client(self):
        return self.ec2.meta.client

    def create_key_pair(self, *args, **kwargs):
        return self.client.create_key_pair(*args, **kwargs)

    def delete_key_pair(self, *args, **kwargs):
        return self.client.delete_key_pair(*args, **kwargs)

    def describe_account_attributes(self, *args, **kwargs):
        return self.client.describe_account_attributes(*args, **kwargs)

    def describe_availability_zones(self, *args, **kwargs):
        return self.client.describe_availability_zones(*args, **kwargs)

    def describe_regions(self, *args, **kwargs):
        return self.client.describe_regions(*args, **kwargs)

if __name__ == '__main__':
    var_filepath = os.path.join(os.path.dirname(__file__), '..', 'vars', 'local.yml')
    with open(var_filepath) as fp:
        vars = yaml.load(fp)

    p = EC2Provider({
        'accessKeyId': os.environ.get('AWS_ACCESS_KEY_ID'),
        'secretAccessKey': os.environ.get('AWS_SECRET_ACCESS_KEY'),
        'region': vars['cluster_region'],
        'cluster_id': vars['cluster_id']
    })

    print(json.dumps(p.get_inventory(vars['cluster_id'])))
