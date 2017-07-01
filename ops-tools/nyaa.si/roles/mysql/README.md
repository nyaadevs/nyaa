---
# An example how to use this role.

- hosts: mysql
  gather_facts: yes
  roles:
    - role: mysql
      mysql_users:
        - hosts:
            - localhost
            - "{{ ansible_hostname }}"
          name: owner
          password: owner-pass
          privileges: "*.*:ALL,GRANT"
      mysql_databases: []
