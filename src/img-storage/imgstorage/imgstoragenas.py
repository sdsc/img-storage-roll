#!/opt/rocks/bin/python
#
# @Copyright@
#
#                               Rocks(r)
#                        www.rocksclusters.org
#                        version 5.6 (Emerald Boa)
#                        version 6.1 (Emerald Boa)
#
# Copyright (c) 2000 - 2013 The Regents of the University of California.
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
#       "This product includes software developed by the Rocks(r)
#       Cluster Group at the San Diego Supercomputer Center at the
#       University of California, San Diego and its contributors."
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
# THIS SOFTWARE IS PROVIDED BY THE REGENTS AND CONTRIBUTORS ``AS IS''
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
from rabbitmqclient import RabbitMQCommonClient, RabbitMQLocator
from imgstorage import runCommand, ActionError, ZvolBusyActionError
import logging

import traceback

import time
import json

from multiprocessing.pool import ThreadPool

from pysqlite2 import dbapi2 as sqlite3
import sys
import signal
import pika
import socket
import rocks.db.helper
import uuid

class NasDaemon():
    def __init__(self):
        self.stdin_path = '/dev/null'
        self.stdout_path = '/tmp/out.log'
        self.stderr_path = '/tmp/err.log'
        self.pidfile_path =  '/var/run/img-storage-nas.pid'
        self.pidfile_timeout = 5
        self.function_dict = {'map_zvol':self.map_zvol, 'unmap_zvol':self.unmap_zvol, 'zvol_mapped':self.zvol_mapped, 'zvol_unmapped': self.zvol_unmapped, 'list_zvols': self.list_zvols, 'del_zvol': self.del_zvol, 'zvol_synced':self.zvol_synced, 'list_sync': self.list_sync }

        self.ZPOOL = RabbitMQLocator.ZPOOL
        self.SQLITE_DB = '/opt/rocks/var/img_storage.db'
        self.NODE_NAME = RabbitMQLocator.NODE_NAME
        self.ib_net = RabbitMQLocator.IB_NET

        self.sync_result = None
        self.SYNC_CHECK_TIMEOUT = 10
        self.SYNC_PULL_TIMEOUT = 60*5
 
        rocks.db.helper.DatabaseHelper().closeSession() # to reopen after daemonization

        self.logger = logging.getLogger('imgstorage.imgstoragenas.NasDaemon')

    def run(self):
        self.pool = ThreadPool(processes=1)
        with sqlite3.connect(self.SQLITE_DB) as con:
            cur = con.cursor()
            cur.execute('CREATE TABLE IF NOT EXISTS zvol_calls(zvol TEXT PRIMARY KEY NOT NULL, reply_to TEXT NOT NULL, time INT NOT NULL)')
            cur.execute('CREATE TABLE IF NOT EXISTS zvols(zvol TEXT PRIMARY KEY NOT NULL, iscsi_target TEXT UNIQUE, remotehost TEXT)')
            cur.execute('CREATE TABLE IF NOT EXISTS sync_queue(zvol TEXT PRIMARY KEY NOT NULL, remotehost TEXT, is_sending BOOLEAN, is_delete_remote BOOLEAN, time INT)')
            con.commit()

        self.queue_connector = RabbitMQCommonClient('rocks.vm-manage', 'direct', self.process_message, lambda a: self.startup())
        self.queue_connector.run()

    def failAction(self, routing_key, action, error_message):
        if(routing_key != None and action != None):
            self.queue_connector.publish_message({'action': action, 'status': 'error', 'error':error_message}, exchange='', routing_key=routing_key)
        self.logger.error("Failed %s: %s"%(action, error_message))

    def startup(self):
        self.schedule_zvols_pull()
        self.schedule_next_sync()

    """
    Received map_zvol command from frontend, passing to compute node
    """
    def map_zvol(self, message, props):
        remotehost = message['remotehost']
        zvol_name = message['zvol']
        self.logger.debug("Setting zvol %s"%zvol_name)

        with sqlite3.connect(self.SQLITE_DB) as con:
            cur = con.cursor()
            try :
                self.lock_zvol(zvol_name, props.reply_to)

                cur.execute('SELECT count(*) FROM zvols WHERE zvol = ?',[zvol_name])
                if(cur.fetchone()[0] == 0):
                    runCommand(['zfs', 'create', '-o', 'primarycache=metadata', '-o', 'volblocksize=128K', '-V', '%sgb'%message['size'], '%s/%s'%(self.ZPOOL, zvol_name)])
                    cur.execute('INSERT OR REPLACE INTO zvols VALUES (?,?,?) ',(zvol_name, None, None))
                    con.commit()
                    self.logger.debug('Created new zvol %s'%zvol_name)

                cur.execute('SELECT iscsi_target FROM zvols WHERE zvol = ?',[zvol_name])
                row = cur.fetchone()
                if (row != None and row[0] != None): #zvol is mapped
                    raise ActionError('Error when mapping zvol: already mapped')

                ip = None
                use_ib = False

                if(self.ib_net):
                    try:
                        ip = socket.gethostbyname('%s.%s'%(remotehost, self.ib_net))
                        use_ib = True
                    except:
                        pass

                if not use_ib:
                    try:
                        ip = socket.gethostbyname(remotehost)
                    except:
                        raise ActionError('Host %s is unknown'%remotehost)

                iscsi_target = ''

                out = runCommand(['tgt-setup-lun', '-n', zvol_name, '-d', '/dev/%s/%s'%(self.ZPOOL, zvol_name), ip])
                for line in out:
                    if "Creating new target" in line:
                        iscsi_target = line['Creating new target (name='.__len__():line.index(',')]
                self.logger.debug('Mapped %s to iscsi target %s'%(zvol_name, iscsi_target))

                cur.execute('INSERT OR REPLACE INTO zvols VALUES (?,?,?) ',(zvol_name, iscsi_target,remotehost))
                con.commit()

                def failDeliver(target, zvol, reply_to, remotehost):
                    self.detach_target(target, true)
                    self.failAction(props.reply_to, 'zvol_mapped', 'Compute node %s is unavailable'%remotehost)
                    self.release_zvol(zvol_name)

                self.queue_connector.publish_message(
                        {'action': 'map_zvol', 'target':iscsi_target, 
                            'nas': ('%s.%s'%(self.NODE_NAME, self.ib_net)) if use_ib else self.NODE_NAME,
                            'size': message['size'], 'zvol':zvol_name},
                        remotehost,
                        self.NODE_NAME,
                        on_fail=lambda: failDeliver(iscsi_target, zvol_name, props.reply_to, remotehost))
                self.logger.debug("Setting iscsi %s sent"%iscsi_target)
            except ActionError, err:
                if not isinstance(err, ZvolBusyActionError): self.release_zvol(zvol_name)
                self.failAction(props.reply_to, 'zvol_mapped', str(err))

    """
    Received zvol unmap_zvol command from frontend, passing to compute node
    """
    def unmap_zvol(self, message, props):
        zvol_name = message['zvol']
        self.logger.debug("Tearing down zvol %s"%zvol_name)

        with sqlite3.connect(self.SQLITE_DB) as con:
            cur = con.cursor()
            try :
                cur.execute('SELECT remotehost, iscsi_target FROM zvols WHERE zvol = ?',[zvol_name])
                row = cur.fetchone()
                if row == None: raise ActionError('ZVol %s not found in database'%zvol_name)
                remotehost, target = row
                if remotehost == None: raise ActionError('ZVol %s is not mapped'%zvol_name)

                self.lock_zvol(zvol_name, props.reply_to)
                self.queue_connector.publish_message(
                        {'action': 'unmap_zvol', 'target':target, 'zvol':zvol_name},
                        remotehost,
                        self.NODE_NAME,
                        on_fail=lambda: self.failAction(props.reply_to, 'zvol_unmapped', 'Compute node %s is unavailable'%remotehost)
                )
                self.logger.debug("Tearing down zvol %s sent"%zvol_name)

            except ActionError, err:
                if not isinstance(err, ZvolBusyActionError): self.release_zvol(zvol_name)
                self.failAction(props.reply_to, 'zvol_unmapped', str(err))

    """
    Received zvol delete command from frontend
    """
    def del_zvol(self, message, props):
        zvol_name = message['zvol']
        self.logger.debug("Deleting zvol %s"%zvol_name)
        with sqlite3.connect(self.SQLITE_DB) as con:
            cur = con.cursor()
            try :
                self.lock_zvol(zvol_name, props.reply_to)
                cur.execute('SELECT remotehost, iscsi_target FROM zvols WHERE zvol = ?',[zvol_name])
                row = cur.fetchone()
                if row == None: raise ActionError('ZVol %s not found in database'%zvol_name)
                if row[0] != None: raise ActionError('Error deleting zvol %s: is mapped'%zvol_name)

                self.logger.debug("Invoking zfs destroy %s/%s"%(self.ZPOOL,zvol_name))
                runCommand(['zfs', 'destroy', '%s/%s'%(self.ZPOOL, zvol_name), '-r'])
                self.logger.debug('zfs destroy success %s'%zvol_name)

                cur.execute('DELETE FROM zvols WHERE zvol = ?',[zvol_name])
                con.commit()

                self.release_zvol(zvol_name)
                self.queue_connector.publish_message({'action': 'zvol_deleted', 'status': 'success'}, exchange='', routing_key=props.reply_to)
            except ActionError, err:
                if not isinstance(err, ZvolBusyActionError): self.release_zvol(zvol_name)
                self.failAction(props.reply_to, 'zvol_deleted', str(err))

    """
    Received zvol_mapped notification from compute node, passing to frontend
    """
    def zvol_mapped(self, message, props):
        target = message['target']

        zvol = None
        reply_to = None

        self.logger.debug("Got zvol mapped message %s"%target)
        with sqlite3.connect(self.SQLITE_DB) as con:
            try:
                if(message['status'] != 'success'): raise ActionError('Error attaching iSCSI target to compute node: %s'%message.get('error'))
                    
                cur = con.cursor()
                cur.execute('SELECT reply_to, zvol_calls.zvol FROM zvol_calls JOIN zvols ON zvol_calls.zvol = zvols.zvol WHERE zvols.iscsi_target = ?',[target])
                reply_to, zvol = cur.fetchone()

                if(not self.is_sync_node(props.reply_to)):
                    self.release_zvol(zvol)
                else:
                    cur.execute('DELETE FROM sync_queue WHERE zvol = ?', [zvol])
                    cur.execute('INSERT INTO sync_queue SELECT zvol,?,1,1,? FROM zvols WHERE iscsi_target = ? ', [props.reply_to, time.time(), target])
                    con.commit() 

                self.queue_connector.publish_message({'action': 'zvol_mapped', 'bdev':message['bdev'], 'status': 'success'}, 
                        exchange='', routing_key=reply_to)
            except ActionError, err:
                self.release_zvol(zvol)
                self.failAction(props.reply_to, 'zvol_mapped', str(err))

    """
    Received zvol_unmapped notification from compute node, passing to frontend
    """
    def zvol_unmapped(self, message, props):
        target = message['target']
        zvol = message['zvol']
        self.logger.debug("Got zvol %s unmapped message"%(target))

        reply_to = None

        try:
            with sqlite3.connect(self.SQLITE_DB) as con:
                cur = con.cursor()

                # get request destination
                cur.execute('SELECT reply_to FROM zvol_calls WHERE zvol = ?',[zvol])
                [reply_to] = cur.fetchone()

                if(message['status'] == 'error'):
                    raise ActionError('Error detaching iSCSI target from compute node: %s'%message.get('error'))

                if(not self.is_sync_node(props.reply_to)):
                    self.detach_target(target, True)
                    self.release_zvol(zvol)
                else:
                    self.detach_target(target, False)
                    cur.execute('UPDATE sync_queue SET is_delete_remote = 1 WHERE zvol = ?', [zvol])
                    if(cur.rowcount == 0):
                        cur.execute('INSERT INTO sync_queue VALUES(?,?,0,1,?)', [zvol, props.reply_to, time.time()])
                    con.commit()

                self.queue_connector.publish_message({'action': 'zvol_unmapped', 'status': 'success'}, exchange='', routing_key=reply_to)

        except ActionError, err:
            self.release_zvol(zvol)
            self.failAction(reply_to, 'zvol_unmapped', str(err))

    """
    Received zvol_synced notification from compute node
    """
    def zvol_synced(self, message, props):
        zvol = message['zvol']
        with sqlite3.connect(self.SQLITE_DB) as con:
            cur = con.cursor()
            cur.execute('SELECT iscsi_target FROM zvols WHERE zvol = ?',[zvol])
            [target] = cur.fetchone()    
            self.detach_target(target, False)
            self.release_zvol(zvol)


    def schedule_next_sync(self):
        with sqlite3.connect(self.SQLITE_DB) as con:
            cur = con.cursor()
            cur.execute('SELECT remotehost, is_sending, zvol, is_delete_remote FROM sync_queue ORDER BY time ASC LIMIT 1')
            row = cur.fetchone()

            if(row):
                remotehost, is_sending, zvol, is_delete_remote  = row
                self.logger.debug("Have sync job %s"%zvol)

                if(not self.sync_result):
                    if(self.ib_net):
                        remotehost += ".%s"%self.ib_net

                    self.logger.debug("Starting new sync %s"%(zvol))
                    if is_sending:
                        self.sync_result = self.pool.apply_async(self.upload_snapshot, [zvol, remotehost])
                    else:
                        self.sync_result = self.pool.apply_async(self.download_snapshot, [zvol, remotehost])

                elif(self.sync_result.ready()):
                    self.logger.debug("Sync %s is ready"%zvol)

                    try:
                        self.sync_result.get()
                        if(is_sending):
                            cur.execute('SELECT iscsi_target FROM zvols WHERE zvol = ?',[zvol])
                            target = cur.fetchone()[0]
                            self.queue_connector.publish_message(
                                {'action': 'sync_zvol', 'zvol':zvol, 'target':target},
                                remotehost, #reply back to compute node
                                self.NODE_NAME,
                                on_fail=lambda: self.logger.error('Compute node %s is unavailable to sync zvol %s'%(remotehost, zvol)))
                        elif(is_delete_remote):
                            # TODO make sure this doesn't take too long, as it's executing in main thread
                            runCommand(['su', 'zfs', '-c', '/usr/bin/ssh %s "/sbin/zfs destroy %s/%s -r"'%(remotehost, self.ZPOOL, zvol)]) 
                            cur.execute('UPDATE zvols SET remotehost = NULL where zvol = ?',[zvol])
                            con.commit()
                            self.release_zvol(zvol)
                        else:
                            out = runCommand(['su', 'zfs', '-c', '/usr/bin/ssh %s "/sbin/zfs list -Hpr -t snapshot -o name -s creation  %s/%s"'%
                               (remotehost, self.ZPOOL, zvol)]) 

                            def destroy_remote_snapshot(snapshot):
                                # TODO make sure this doesn't take too long, as it's executing in main thread
                                runCommand(['su', 'zfs', '-c', '/usr/bin/ssh %s "/sbin/zfs destroy %s"'%(remotehost, snapshot)]) 
                            map(destroy_remote_snapshot, out[:-2])
                    except ActionError, msg:
                        self.logger.exception('Error performing sync for %s: %s'%(zvol, str(msg)))
                    finally:
                        self.sync_result = None
                        cur.execute('DELETE FROM sync_queue WHERE zvol = ?', [zvol])
                        con.commit()
                        
            self.queue_connector._connection.add_timeout(self.SYNC_CHECK_TIMEOUT, self.schedule_next_sync)

    def schedule_zvols_pull(self):
        self.logger.debug("Scheduling new pull jobs")
        with sqlite3.connect(self.SQLITE_DB) as con:
            try:
                cur = con.cursor()
                cur.execute('SELECT zvol, remotehost FROM zvols WHERE iscsi_target IS NULL and remotehost IS NOT NULL ORDER BY zvol DESC;')
                rows = cur.fetchall()
                for row in rows:
                    zvol, remotehost = row
                    cur.execute('INSERT or IGNORE INTO sync_queue VALUES(?,?,0,0,?)', [zvol, remotehost, time.time()])
                    con.commit()
            except Exception, ex:
                self.logger.exception(ex)

        self.queue_connector._connection.add_timeout(self.SYNC_PULL_TIMEOUT, self.schedule_zvols_pull)

    def upload_snapshot(self, zvol, remotehost):
        snap_name = uuid.uuid4()
        runCommand(['zfs', 'snap', '%s/%s@%s'%(self.ZPOOL, zvol, snap_name)])
        runCommand(['zfs', 'send', '%s/%s@%s'%(self.ZPOOL, zvol, snap_name)], 
                ['su', 'zfs', '-c', '/usr/bin/ssh %s "/sbin/zfs receive -F %s/%s"'%(remotehost, self.ZPOOL, zvol)])

    def download_snapshot(self, zvol, remotehost):
        snap_name = uuid.uuid4()
        runCommand(['su', 'zfs', '-c', '/usr/bin/ssh %s "/sbin/zfs snap %s/%s@%s"'%(remotehost, self.ZPOOL, zvol, snap_name)])
        runCommand(['su', 'zfs', '-c', '/usr/bin/ssh %s "/sbin/zfs send -i %s/%s@%s %s/%s@%s"'%
                        (remotehost, self.ZPOOL, zvol, self.find_last_snapshot(zvol), self.ZPOOL, zvol, snap_name)], 
                ['zfs', 'receive', '-F', '%s/%s'%(self.ZPOOL, zvol)])

        def destroy_local_snapshot(snapshot):
           runCommand(['/sbin/zfs', 'destroy', snapshot]) 

        out = runCommand(['/sbin/zfs', 'list', '-Hpr', '-t', 'snapshot', '-o', 'name', '-s', 'creation', '%s/%s'%(self.ZPOOL, zvol)])
        map(destroy_local_snapshot, out[:-2])


    def detach_target(self, target, is_remove_host):
        if(target):
            tgt_num = self.find_iscsi_target_num(target)
            if(tgt_num):
                runCommand(['tgtadm', '--lld', 'iscsi', '--op', 'delete', '--mode', 'target', '--tid', tgt_num])# remove iscsi target

        with sqlite3.connect(self.SQLITE_DB) as con:
            cur = con.cursor()
            if(is_remove_host):
                cur.execute('UPDATE zvols SET iscsi_target = NULL, remotehost = NULL where iscsi_target = ?',[target])
            else:
                cur.execute('UPDATE zvols SET iscsi_target = NULL where iscsi_target = ?',[target])
            con.commit()

    def list_zvols(self, message, properties):
        with sqlite3.connect(self.SQLITE_DB) as con:
            cur = con.cursor()
            cur.execute('SELECT * from zvols')
            r = [dict((cur.description[i][0], value) for i, value in enumerate(row)) for row in cur.fetchall()]
            self.queue_connector.publish_message({'action': 'zvol_list', 'status': 'success', 'body':r}, exchange='', routing_key=properties.reply_to)

    def process_message(self, properties, message):
        self.logger.debug("Received message %s"%message)

        if message['action'] in self.function_dict.keys():
            try:
                self.function_dict[message['action']](message, properties)
            except:
                self.logger.exception("Unexpected error: %s %s"%(sys.exc_info()[0], sys.exc_info()[1]))
                self.queue_connector.publish_message({'status': 'error', 'error':sys.exc_info()[1].message}, exchange='', routing_key=properties.reply_to)

    def stop(self):
        self.queue_connector.stop()
        self.logger.info('RabbitMQ connector stopping called')

    def lock_zvol(self, zvol_name, reply_to):
        with sqlite3.connect(self.SQLITE_DB) as con:
            cur = con.cursor()
            try:
                cur.execute('INSERT INTO zvol_calls VALUES (?,?,?)',(zvol_name, reply_to, time.time()))
                con.commit()
            except sqlite3.IntegrityError:
                raise ZvolBusyActionError('ZVol %s is busy'%zvol_name)

    def release_zvol(self, zvol):
        with sqlite3.connect(self.SQLITE_DB) as con:
            cur = con.cursor()
            cur.execute('DELETE FROM zvol_calls WHERE zvol = ?',[zvol])
            con.commit()

    def find_iscsi_target_num(self, target):
        out = runCommand(['tgtadm', '--op', 'show', '--mode', 'target'])
        for line in out:
            if line.startswith('Target ') and line.split()[2] == target:
                return line.split()[1][:-1]
        return None

    """ Get information from attributes if image sync is enabled for the node """
    def is_sync_node(self, remotehost):
        try:
            db = rocks.db.helper.DatabaseHelper()
            db.connect()
            is_sync_node = db.getHostAttr(remotehost, 'img_sync')
            db.close()
        except Exception, e:
            self.logger.exception("Unable to get img_sync attribute: " + str(e))
            return False
        return is_sync_node


    def find_last_snapshot(self, zvol):
        out = runCommand(['zfs', 'list', '-Hpr', '-t', 'snapshot', '-o', 'name', '-s', 'creation', '%s/%s'%(self.ZPOOL, zvol)])
        if(not out):        raise ActionError("No shapshots found")
        return out[-1].split('@')[1]


    def list_sync(self, message, properties):
        with sqlite3.connect(self.SQLITE_DB) as con:
            cur = con.cursor()
            cur.execute('SELECT sync_queue.is_sending, sync_queue.zvol, sync_queue.remotehost, sync_queue.time from sync_queue ORDER BY sync_queue.time ASC;')
            r = [dict((cur.description[i][0], value) for i, value in enumerate(row)) for row in cur.fetchall()]
            self.queue_connector.publish_message({'action': 'return_sync', 'status': 'success', 'body':r}, exchange='', routing_key=properties.reply_to)


