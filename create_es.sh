#!/usr/bin/env bash

# create indices named "nyaa" and "sukebei", these are hardcoded
curl -v -XPUT 'localhost:9200/nyaa?pretty' -H"Content-Type: application/yaml" --data-binary @es_mapping.yml
curl -v -XPUT 'localhost:9200/sukebei?pretty' -H"Content-Type: application/yaml" --data-binary @es_mapping.yml
