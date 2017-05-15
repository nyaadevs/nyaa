#!/usr/bin/env bash

curl -v -XPUT 'localhost:9200/nyaav2?pretty' -H"Content-Type: application/yaml" --data-binary @es_mapping.yml
