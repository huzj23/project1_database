#!/bin/bash
set -u

/usr/bin/printf '%s\n' '=== GSO object directories ==='
/usr/bin/find /data/raw/huzijian/project1_database/models/gso \
  -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | /usr/bin/sort
/usr/bin/printf '%s\n' '=== GSO URDF count ==='
/usr/bin/find /data/raw/huzijian/project1_database/models/gso \
  -type f -name 'object.urdf' -printf '%p\n' | /usr/bin/wc -l
/usr/bin/printf '%s\n' '=== ReplicaCAD stages ==='
/usr/bin/find /data/raw/huzijian/project1_database/models/backgrounds/replicad/stages \
  -mindepth 1 -maxdepth 1 -type f -printf '%f\n' | /usr/bin/sort
/usr/bin/printf '%s\n' '=== Poly Haven Shed HEAD ==='
/usr/bin/curl -L -sS -I \
  https://dl.polyhaven.org/file/ph-assets/Scenes/the_shed.zip | \
  /usr/bin/grep -Ei 'HTTP/|content-length|content-type|last-modified'
/usr/bin/printf '%s\n' 'INVENTORY_DONE'

exec /bin/bash
