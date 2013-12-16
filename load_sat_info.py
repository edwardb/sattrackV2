#!/usr/bin/env python
# -*- coding: utf-8 -*- 
# vim: noai:ts=4:sw=4 
import json
import csv
import sys

with open('/home/emb/projects/sattrack/sat_info.csv') as fin:
    try:
        csvin = csv.DictReader(fin)
        headers = csvin.fieldnames
        by_number = {row['number']: row for row in csvin}
    
    finally:
        fin.close()

json_encoded = json.dumps(by_number)

with open('sat_info.json', 'wb') as fp:
    json.dump(by_number,fp)
    
print('done')
