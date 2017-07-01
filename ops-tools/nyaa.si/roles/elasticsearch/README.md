# ansible-elasticsearch
[![Ansible Galaxy](https://img.shields.io/badge/ansible--galaxy-elastic.elasticsearch-blue.svg)](https://galaxy.ansible.com/elastic/elasticsearch/)

**THIS ROLE IS FOR 5.x. FOR 2.x SUPPORT PLEASE USE THE 2.x BRANCH.**

Ansible role for 5.x Elasticsearch.  Currently this works on Debian and RedHat based linux systems.  Tested platforms are:

* Ubuntu 14.04/16.04
* Debian 8
* Centos 7

The latest Elasticsearch versions of 5.x are actively tested.  **Only Ansible versions > 2.2.0 are supported.**

## Usage

Create your Ansible playbook with your own tasks, and include the role elasticsearch.  You will have to have this repository accessible within the context of playbook, e.g.

e.g. 

```
cd /my/repos/
git clone git@github.com:elastic/ansible-elasticsearch.git
cd /my/ansible/playbook
mkdir -p roles
ln -s /my/repos/ansible-elasticsearch ./roles/elasticsearch
```

Then create your playbook yaml adding the role elasticsearch.  By default, the user is only required to specify a unique es_instance_name per role application.  This should be unique per node. 
The application of the elasticsearch role results in the installation of a node on a host.

The simplest configuration therefore consists of: 

```
---
- name: Simple Example
  hosts: localhost
  roles:
    - { role: elasticsearch, es_instance_name: "node1" }
  vars:
```

The above installs a single node 'node1' on the hosts 'localhost'.

This role also uses [Ansible tags](http://docs.ansible.com/ansible/playbooks_tags.html). Run your playbook with the `--list-tasks` flag for more information.

### Basic Elasticsearch Configuration

All Elasticsearch configuration parameters are supported.  This is achieved using a configuration map parameter 'es_config' which is serialized into the elasticsearch.yml file.  
The use of a map ensures the Ansible playbook does not need to be updated to reflect new/deprecated/plugin configuration parameters.

In addition to the es_config map, several other parameters are supported for additional functions e.g. script installation.  These can be found in the role's defaults/main.yml file.

The following illustrates applying configuration parameters to an Elasticsearch instance.  By default, Elasticsearch 5.1.2is installed.

```
- name: Elasticsearch with custom configuration
  hosts: localhost
  roles:
    #expand to all available parameters
    - { role: elasticsearch, es_instance_name: "node1", es_data_dirs: "/opt/elasticsearch/data", es_log_dir: "/opt/elasticsearch/logs", 
    es_config: {
        node.name: "node1", 
        cluster.name: "custom-cluster",
        discovery.zen.ping.unicast.hosts: "localhost:9301",
        http.port: 9201,
        transport.tcp.port: 9301,
        node.data: false,
        node.master: true,
        bootstrap.memory_lock: true,
        } 
    }
  vars:
    es_scripts: false
    es_templates: false
    es_version_lock: false
    es_heap_size: 1g
    es_api_port:9201
```
`
The role utilises Elasticsearch version defaults.  The following should be set to ensure a successful cluster forms.

* ```es_config['http.port']``` - the http port for the node
* ```es_config['transport.tcp.port']``` - the transport port for the node
* ```es_config['discovery.zen.ping.unicast.hosts']``` - the unicast discovery list, in the comma separated format ```"<host>:<port>,<host>:<port>"``` (typically the clusters dedicated masters)
* ```es_config['network.host']``` - sets both network.bind_host and network.publish_host to the same host value. The network.bind_host setting allows to control the host different network components will bind on.  

The network.publish_host setting allows to control the host the node will publish itself within the cluster so other nodes will be able to connect to it. 

See https://www.elastic.co/guide/en/elasticsearch/reference/current/modules-network.html for further details on default binding behaviour and available options.
The role makes no attempt to enforce the setting of these are requires users to specify them appropriately.  IT is recommended master nodes are listed and thus deployed first where possible.

A more complex example:

```
---
- name: Elasticsearch with custom configuration
  hosts: localhost
  roles:
    #expand to all available parameters
    - { role: elasticsearch, es_instance_name: "node1", es_data_dirs: "/opt/elasticsearch/data", es_log_dir: "/opt/elasticsearch/logs", 
    es_config: {
        node.name: "node1", 
        cluster.name: "custom-cluster", 
        discovery.zen.ping.unicast.hosts: "localhost:9301", 
        http.port: 9201, 
        transport.tcp.port: 9301, 
        node.data: false, 
        node.master: true, 
        bootstrap.memory_lock: true, 
        } 
    }
  vars:
    es_scripts: false
    es_templates: false
    es_version_lock: false
    es_heap_size: 1g
    es_scripts: false
    es_templates: false
    es_version_lock: false
    es_start_service: false
    es_plugins_reinstall: false
    es_api_port:9201
    es_plugins:
        - plugin: ingest-geoip
          proxy_host: proxy.example.com
          proxy_port: 8080
```

#### Important Note

**The role uses es_api_host and es_api_port to communicate with the node for actions only achievable via http e.g. to install templates and to check the NODE IS ACTIVE.  These default to "localhost" and 9200 respectively.  
If the node is deployed to bind on either a different host or port, these must be changed.**

### Multi Node Server Installations

The application of the elasticsearch role results in the installation of a node on a host. Specifying the role multiple times for a host therefore results in the installation of multiple nodes for the host. 

An example of a two server deployment is shown below.  The first server holds the master and is thus declared first.  Whilst not mandatory, this is recommended in any multi node cluster configuration.  The second server hosts two data nodes.

**Note the structure of the below playbook for the data nodes.  Whilst a more succinct structures are possible which allow the same role to be applied to a host multiple times, we have found the below structure to be the most reliable with respect to var behaviour.  This is the tested approach.**

```
- hosts: master_nodes
  roles:
    - { role: elasticsearch, es_instance_name: "node1", es_heap_size: "1g",
    es_config: {
        cluster.name: "test-cluster",
        discovery.zen.ping.unicast.hosts: "elastic02:9300",
        http.port: 9200,
        transport.tcp.port: 9300,
        node.data: false,
        node.master: true,
        bootstrap.memory_lock: false,
        }
    }
  vars:
    es_scripts: false
    es_templates: false
    es_version_lock: false
    ansible_user: ansible
    es_plugins:
     - plugin: ingest-geoip



- hosts: data_nodes
  roles:
    - { role: elasticsearch, es_instance_name: "node1", es_data_dirs: "/opt/elasticsearch", 
    es_config: {
        discovery.zen.ping.unicast.hosts: "elastic02:9300",
        http.port: 9200,
        transport.tcp.port: 9300,
        node.data: true,
        node.master: false,
        bootstrap.memory_lock: false,
        cluster.name: "test-cluster"
        } 
    }
  vars:
    es_scripts: false
    es_templates: false
    es_version_lock: false
    ansible_user: ansible
    es_api_port: 9200
    es_plugins:
    - plugin: ingest-geoip
    
    
- hosts: data_nodes
  roles:
    - { role: elasticsearch, es_instance_name: "node2", es_api_port:9201,
    es_config: {
        discovery.zen.ping.unicast.hosts: "elastic02:9300",
        http.port: 9201,
        transport.tcp.port: 9301,
        node.data: true,
        node.master: false,
        bootstrap.memory_lock: false,
        cluster.name: "test-cluster",
        } 
    }
  vars:
    es_scripts: false
    es_templates: false
    es_version_lock: false
    es_api_port: 9201
    ansible_user: ansible
    es_plugins:
    - plugin: ingest-geoip

```

Parameters can additionally be assigned to hosts using the inventory file if desired.

Make sure your hosts are defined in your ```inventory``` file with the appropriate ```ansible_ssh_host```,  ```ansible_ssh_user``` and ```ansible_ssh_private_key_file``` values.

Then run it:

```
ansible-playbook -i hosts ./your-playbook.yml
```

### Installing X-Pack Features

X-Pack features, such as Security, are supported. This feature is currently experimental.  To enable X-Pack set the parameter `es_enable_xpack` to true and list the required features in the parameter `es_xpack_features`.  

The parameter `es_xpack_features` by default enables all features i.e. it defaults to ["alerting","monitoring","graph","security"]

The following additional parameters allow X-Pack to be configured:

* ```es_message_auth_file``` System Key field to allow message authentication. This file should be placed in the 'files' directory.
* ```es_role_mapping``` Role mappings file declared as yml as described [here](https://www.elastic.co/guide/en/x-pack/current/mapping-roles.html)

```
es_role_mapping:
  power_user:
    - "cn=admins,dc=example,dc=com"
  user:
    - "cn=users,dc=example,dc=com"
    - "cn=admins,dc=example,dc=com"
```

* ```es_users``` - Users can be declared here as yml. Two sub keys 'native' and 'file' determine the realm under which realm the user is created.  Beneath each of these keys users should be declared as yml entries. e.g.

```
es_users:
  native:
    kibana4_server:
      password: changeMe
      roles:
        - kibana4_server
  file:
    es_admin:
      password: changeMe
      roles:
        - admin
    testUser:
      password: changeMeAlso!
      roles:
        - power_user
        - user
```
            
            
* ```es_roles``` - Elasticsearch roles can be declared here as yml. Two sub keys 'native' and 'file' determine how the role is created i.e. either through a file or http(native) call.  Beneath each key list the roles with appropriate permissions, using the file based format described [here] (https://www.elastic.co/guide/en/x-pack/current/file-realm.html) e.g.

```
es_roles:
  file:
    admin:
      cluster:
        - all
      indices:
        - names: '*'
          privileges:
            - all
    power_user:
      cluster:
        - monitor
      indices:
        - names: '*'
          privileges:
            - all
    user:
      indices:
        - names: '*'
          privileges:
            - read
    kibana4_server:
      cluster:
          - monitor
      indices:
        - names: '.kibana'
          privileges:
            - all
  native:
    logstash:
      cluster:
        - manage_index_templates
      indices:
        - names: 'logstash-*'
          privileges:
            - write
            - delete
            - create_index
```                
                
* ```es_xpack_license``` - X-Pack license.  The license should be declared as a json blob.  Alternative use Ansible vault or copy the license to the target machine as part of a playbook and access via a lookup e.g.

```
es_xpack_license: "{{ lookup('file', '/tmp/license.json')  }}"
``` 

X-Pack configuration parameters can be added to the elasticsearch.yml file using the normal `es_config` parameter.

For a full example see [here](https://github.com/elastic/ansible-elasticsearch/blob/master/test/integration/xpack.yml)

####Important Note for Native Realm Configuration

In order for native users and roles to be configured, the role calls the Elasticsearch API.  Given security is installed this requires definition of two parameters:

* ```es_api_basic_auth_username``` - admin username
* ```es_api_basic_auth_password``` - admin password

These can either be set to a user declared in the file based realm, with admin permissions, or the default "elastic" superuser (default password is changeme).


### Additional Configuration

Additional parameters to es_config allow the customization of the Java and Elasticsearch versions, in addition to role behaviour. Options include:

* ```es_major_version``` (e.g. "5.1" ). Should be consistent with es_version. For versions >= 5.0 this must be "5.x".
* ```es_version``` (e.g. "5.1.2").  
* ```es_api_host``` The host name used for actions requiring HTTP e.g. installing templates. Defaults to "localhost".
* ```es_api_port``` The port used for actions requiring HTTP e.g. installing templates. Defaults to 9200. **CHANGE IF THE HTTP PORT IS NOT 9200**
* ```es_api_basic_auth_username``` The Elasticsearch username for making admin changing actions. Used if Security is enabled. Ensure this user is admin.
* ```es_api_basic_auth_password``` The password associated with the user declared in `es_api_basic_auth_username`
* ```es_start_service``` (true (default) or false)
* ```es_plugins_reinstall``` (true or false (default) )
* ```es_plugins``` an array of plugin definitions e.g.:
```yml
  es_plugins:
    - plugin: elasticsearch-cloud-aws
```
* ```es_allow_downgrades``` For development purposes only. (true or false (default) )
* ```es_java_install``` If set to false, Java will not be installed. (true (default) or false)
* ```update_java``` Updates Java to the latest version. (true or false (default))
* ```es_max_map_count``` maximum number of VMA (Virtual Memory Areas) a process can own. Defaults to 262144.
* ```es_max_open_files``` the maximum file descriptor number that can be opened by this process. Defaults to 65536.

Earlier examples illustrate the installation of plugins using `es_plugins`.  For officially supported plugins no version or source delimiter is required. The plugin script will determine the appropriate plugin version based on the target Elasticsearch version.  For community based plugins include the full url.  This approach should NOT be used for the X-Pack plugin.  See X-Pack below for details here.
 
If installing Monitoring or Alerting, ensure the license plugin is also specified.  Security configuration is currently not supported but planned for later versions.

* ```es_user``` - defaults to elasticsearch.
* ```es_group``` - defaults to elasticsearch.
* ```es_user_id``` - default is undefined.
* ```es_group_id``` - default is undefined.

Both ```es_user_id``` and ```es_group_id``` must be set for the user and group ids to be set. 

By default, each node on a host will be installed to use unique pid, plugin, work, data and log directories.  These directories are created, using the instance and host name, beneath default locations ]
controlled by the following parameters:

* ```es_pid_dir``` - defaults to "/var/run/elasticsearch".
* ```es_data_dirs``` - defaults to "/var/lib/elasticsearch".  This can be a list or comma separated string e.g. ["/opt/elasticsearch/data-1","/opt/elasticsearch/data-2"] or "/opt/elasticsearch/data-1,/opt/elasticsearch/data-2"
* ```es_log_dir``` - defaults to "/var/log/elasticsearch".
* ```es_restart_on_change``` - defaults to true.  If false, changes will not result in Elasticsearch being restarted.
* ```es_plugins_reinstall``` - defaults to false.  If true, all currently installed plugins will be removed from a node.  Listed plugins will then be re-installed.  

This role ships with sample scripts and templates located in the [files/scripts/](files/scripts) and [files/templates/](files/templates) directories, respectively. These variables are used with the Ansible [with_fileglob](http://docs.ansible.com/ansible/playbooks_loops.html#id4) loop. When setting the globs, be sure to use an absolute path.
* ```es_scripts_fileglob``` - defaults to `<role>/files/scripts/`.
* ```es_templates_fileglob``` - defaults to `<role>/files/templates/`.

### Proxy

To define proxy globaly, set the following variables:

* ```es_proxy_host``` - global proxy host
* ```es_proxy_port``` - global proxy port

To define proxy only for a particular plugin during its installation:

```
  es_plugins:
    - plugin: elasticsearch-cloud-aws
      proxy_host: proxy.example.com
      proxy_port: 8080
```

> For plugins installation, proxy_host and proxy_port are used first if they are defined and fallback to the global proxy settings if not.

## Notes

* The role assumes the user/group exists on the server.  The elasticsearch packages create the default elasticsearch user.  If this needs to be changed, ensure the user exists.
* The playbook relies on the inventory_name of each host to ensure its directories are unique
* Changing an instance_name for a role application will result in the installation of a new component.  The previous component will remain.
* KitchenCI has been used for testing.  This is used to confirm images reach the correct state after a play is first applied.  We currently test only the latest version of 5.x on
all supported platforms. 
* The role aims to be idempotent.  Running the role multiple times, with no changes, should result in no state change on the server.  If the configuration is changed, these will be applied and 
Elasticsearch restarted where required.
* Systemd is used for Ubuntu versions >= 15, Debian >=8, Centos >=7.  All other versions use init for service scripts.
* In order to run x-pack tests a license file with security enabled is required. A trial license is appropriate. Set the environment variable `ES_XPACK_LICENSE_FILE` to the full path of the license file prior to running tests.

## IMPORTANT NOTES RE PLUGIN MANAGEMENT

* If the ES version is changed, all plugins will be removed.  Those listed in the playbook will be re-installed.  This is behaviour is required in ES 5.x.
* If no plugins are listed in the playbook for a node, all currently installed plugins will be removed.
* The role does not currently support automatic detection of differences between installed and listed plugins (other than if none are listed).   Should users wish to change installed plugins should set es_plugins_reinstall to true.  This will cause all currently installed plugins to be removed and those listed to be installed.  Change detection will be implemented in future releases.

## Questions on Usage

We welcome questions on how to use the role.  However, in order to keep the github issues list focused on "issues" we ask the community to raise questions at https://discuss.elastic.co/c/elasticsearch.  This is monitored by the maintainers.
