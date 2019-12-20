#!/bin/bash
#
# @Copyright@
#
#                                 Rocks(r)
#                          www.rocksclusters.org
#                          version 6.2 (SideWinder)
#                          version 7.0 (Manzanita)
#
# Copyright (c) 2000 - 2017 The Regents of the University of California.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# 1. Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
# notice unmodified and in its entirety, this list of conditions and the
# following disclaimer in the documentation and/or other materials provided
# with the distribution.
#
# 3. All advertising and press materials, printed or electronic, mentioning
# features or use of this software must display the following acknowledgement:
#
#         "This product includes software developed by the Rocks(r)
#         Cluster Group at the San Diego Supercomputer Center at the
#         University of California, San Diego and its contributors."
#
# 4. Except as permitted for the purposes of acknowledgment in paragraph 3,
# neither the name or logo of this software nor the names of its
# authors may be used to endorse or promote products derived from this
# software without specific prior written permission.  The name of the
# software includes the following terms, and any derivatives thereof:
# "Rocks", "Rocks Clusters", and "Avalanche Installer".  For licensing of
# the associated name, interested parties should contact Technology
# Transfer & Intellectual Property Services, University of California,
# San Diego, 9500 Gilman Drive, Mail Code 0910, La Jolla, CA 92093-0910,
# Ph: (858) 534-5815, FAX: (858) 534-7345, E-MAIL:invent@ucsd.edu
#
# THIS SOFTWARE IS PROVIDED BY THE REGENTS AND CONTRIBUTORS ``AS IS
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO,
# THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
# PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE REGENTS OR CONTRIBUTORS
# BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR
# CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF
# SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR
# BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY,
# WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE
# OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN
# IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# @Copyright@
#

# Save standard output and standard error
#exec 3>&1 4>&2
# Redirect standard output to a log file
#exec 1>/tmp/stdout.log
# Redirect standard error to a log file
#exec 2>/tmp/stderr.log

#set -e

# See roll's README.md for explanation
BBCP="bbcp"
if type /opt/bbcp/bin/bbcp > /dev/null 2>&1; then
  BBCP="/opt/bbcp/bin/bbcp"
fi

PREFIX="IMG-STORAGE-"

LOCAL_SNAPSHOTS_TRIM=3

TEMP=`getopt -o p:v:r:y:u:t:h --long zpool:,zvol:,remotehost:,remotezpool:,user:,throttle:,help -n 'snapshot_upload' -- "$@"`

[ "$?" != "0" ] &&  logger -p user.error "$0 - Called with wrong parameters" && exit 1 || :

eval set -- "$TEMP"
function help_message {
cat << EOT
Usage: $0 [-h|--help] PARAMETERS [OPTIONAL PARAMETERS]

 -p, --zpool=ZPOOL              Required, local zpool name
 -v, --zvol=ZVOL                Required, zvol name
 -r, --remotehost=REMOTEHOST    Required, compute host name
 -y, --remotezpool=REMOTEZPOOL  Required, remote zpool name
 -u, --user=IMGUSER             Required, username to access zfs with
 -t, --throttle=THROTTLE        Optional, limit the transfer to a maximum of RATE bytes per second.
                                          A suffix of "K", "M", "G" can be added  to  denote  kilobytes (*1024),
                                          megabytes, and so on.

Example: $0 -p tank -v vm-vc1-1-vol -r comet-01-10 -y tank -u img-storage -t 10M
EOT
}

ZPOOL=
ZVOL=
REMOTEHOST=
REMOTEZPOOL=
THROTTLE=
IMGUSER=

while true; do
  case "$1" in
    -p|--zpool ) ZPOOL="$2"; shift 2;;
    -v|--zvol ) ZVOL="$2"; shift 2;;
    -r|--remotehost ) REMOTEHOST="$2"; shift 2;;
    -y|--remotezpool ) REMOTEZPOOL="$2"; shift 2;;
    -u|--user ) IMGUSER="$2"; shift 2;;
    -t|--throttle ) THROTTLE="$2"; shift 2;;
    -h|--help ) help_message; exit 0; shift ;;
    -- ) shift; break ;;
    * ) break ;;
  esac
done

if [ -z "$ZPOOL" ]; then echo "zpool parameter is required"; help_message; exit 1; fi
if [ -z "$ZVOL" ]; then echo "zvol parameter is required"; help_message; exit 1; fi
if [ -z "$REMOTEHOST" ]; then echo "remotehost parameter is required"; help_message; exit 1; fi
if [ -z "$REMOTEZPOOL" ]; then echo "remotezpool parameter is required"; help_message; exit 1; fi
if [ -z "$IMGUSER" ]; then echo "user parameter is required"; help_message; exit 1; fi

SNAP_NAME=$PREFIX`/usr/bin/uuidgen`

OUT=$((/sbin/zfs snap "$ZPOOL/$ZVOL@$SNAP_NAME") 2>&1)
[ "$?" != "0" ] &&  logger -p user.error "$0 - Error creating local snapshot $ZPOOL/$ZVOL@$SNAP_NAME ${OUT//$'\n'/ }" && exit 1 || :

if type $BBCP > /dev/null 2>&1; then
  THROTTLE_STR=
  if [ -n "$THROTTLE" ]; then
      THROTTLE_STR="-x $THROTTLE"
  fi

  OUT=$((su $IMGUSER -c "$BBCP -o -4 $THROTTLE_STR -s 1 -N io \
         -T '/usr/bin/ssh -x -a -oFallBackToRsh=no %4 %I -l %U %H $BBCP' \
         '/sbin/zfs send $ZPOOL/$ZVOL@$SNAP_NAME' \
         '$REMOTEHOST:/sbin/zfs receive -F $REMOTEZPOOL/$ZVOL'") 2>&1)
else
  THROTTLE_STR=
  if [ -n "$THROTTLE" ]; then
      THROTTLE_STR=" | pv -L $THROTTLE -q "
  fi

  OUT=$((/sbin/zfs send "$ZPOOL/$ZVOL@$SNAP_NAME" $THROTTLE_STR | su $IMGUSER -c "ssh $REMOTEHOST \"/sbin/zfs receive -F $REMOTEZPOOL/$ZVOL\"")2>&1)
fi
[ "$?" != "0" ] &&  logger -p user.error "$0 - Error uploading snapshot $REMOTEHOST:$ZPOOL/$ZVOL ${OUT//$'\n'/ }" && exit 1 || :

#trim local snapshots
OUT=$((/sbin/zfs list -Hpr -t snapshot -o name -s creation "$ZPOOL/$ZVOL" | head -n "-$LOCAL_SNAPSHOTS_TRIM" | xargs -r -l1 /sbin/zfs destroy) 2>&1)
[ "$?" != "0" ] &&  logger -p user.error "$0 - Error deleting local snapshots $ZPOOL/$ZVOL ${OUT//$'\n'/ }" && exit 1 || :
