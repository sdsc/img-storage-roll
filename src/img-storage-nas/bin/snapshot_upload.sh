#!/bin/bash
 
# Save standard output and standard error
#exec 3>&1 4>&2
# Redirect standard output to a log file
#exec 1>/tmp/stdout.log
# Redirect standard error to a log file
#exec 2>/tmp/stderr.log

#set -e

PREFIX="IMG-STORAGE-"

LOCAL_SNAPSHOTS_TRIM=10

TEMP=`getopt -o p:v:r:y:u:t:h --long zpool:,zvol:,remotehost:,remotezpool:,user:,throttle:,help -n 'snapshot_upload' -- "$@"`

[ "$?" != "0" ] &&  logger "$0 - Called with wrong parameters" && exit 1 || :

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

THROTTLE_STR=
if [ -n "$THROTTLE" ]; then
    THROTTLE_STR="-x $THROTTLE"
fi

OUT=$((/sbin/zfs snap "$ZPOOL/$ZVOL@$SNAP_NAME") 2>&1)
[ "$?" != "0" ] &&  logger "$0 - Error creating local snapshot $ZPOOL/$ZVOL@$SNAP_NAME ${OUT//$'\n'/ }" && exit 1 || :

OUT=$((su $IMGUSER -c "/bin/bbcp -o -4 $THROTTLE_STR -s 1 -N io \
       -T '/usr/bin/ssh -x -a -oFallBackToRsh=no %4 %I -l %U %H /bin/bbcp' \
       '/sbin/zfs send $ZPOOL/$ZVOL@$SNAP_NAME' \
       '$REMOTEHOST:/sbin/zfs receive -F $REMOTEZPOOL/$ZVOL'") 2>&1)
[ "$?" != "0" ] &&  logger "$0 - Error uploading snapshot $REMOTEHOST:$ZPOOL/$ZVOL ${OUT//$'\n'/ }" && exit 1 || :

#trim local snapshots
OUT=$((/sbin/zfs list -Hpr -t snapshot -o name -s creation "$ZPOOL/$ZVOL" | head -n "-$LOCAL_SNAPSHOTS_TRIM" | xargs -r -l1 /sbin/zfs destroy) 2>&1)
[ "$?" != "0" ] &&  logger "$0 - Error deleting local snapshots $ZPOOL/$ZVOL ${OUT//$'\n'/ }" && exit 1 || :

