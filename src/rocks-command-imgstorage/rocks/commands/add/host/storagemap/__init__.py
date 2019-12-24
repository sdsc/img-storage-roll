#!/opt/rocks/bin/python
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
#

import sys
import string
import rocks.commands

from imgstorage.commandlauncher import CommandLauncher

class Command(rocks.commands.HostArgumentProcessor, rocks.commands.add.command):
	"""
	Map a virtual machine image from the NAS (or virtual machine images
	repository) to the remote environment.

	<arg type='string' name='nas' optional='0'>
	The NAS name which will host the storage image
	</arg>

	<arg type='string' name='zpool' optional='0'>
	The zpool name. The final full zvol path name will be formed as
	zpool + "/" + volume
	</arg>

	<arg type='string' name='volume' optional='0'>
	The volume name which will be mapped on the remote environment
	</arg>

	<arg type='string' name='remotehost' optional='0'>
	The machine name that will mount the storage volume
	</arg>

	<arg type='string' name='size' optional='0'>
	The size of the volume in Gigabyte.
	If the disk is already present on the NAS the size will be ignored.
	</arg>

	<param type='string' name='remotepool' optional='1'>
	pool in remote host on which to place storage volume. Required if
        img_sync is true
	</param>

	<param type='bool' name='img_sync' optional='1'>
	Should the volume sync to the local (remotehost) system or be an
        iscsi-only remote mount.  Default: uses remote host\'s
	img_sync attribute
	</param>

	<example cmd='add host storagemap nas-0-0 tank vm-sdsc125-2 vm-container-0-0 35 remotepool=tank2 img_sync=yes'>
	If it does not exist create tank/vm-sdsc125-2 on nas and map it to
	vm-container-0-0 on pool tank2.
	</example>

	<example cmd='add host storagemap nas-0-0 tank vm-sdsc125-2 vm-container 35 img_sync=no'>
	If it does not exist create tank/vm-sdsc125-2 on nas and map it to vm-container-0-0.
	Do NOT sync the image (iscsi mount only)
	</example>

	"""

	def run(self, params, args):
		(args, nas, zpool, volume, remotehost, size) = self.fillPositionalArgs(
				('nas', 'zpool', 'volume', 'remotehost', 'size'))

		sync,remotepool, = self.fillParams( [('img_sync', None),('remotepool',None)] )

		if not nas or not zpool or not volume or not remotehost or not size:
			self.abort("you must pass 5 arguments nas_name zpool volume remotehost size")

		if sync is None:
			sync =  self.db.getHostAttr(remotehost,'img_sync')

		sync = False if sync is None else self.str2bool(sync)

		if sync and remotepool is None:
			self.abort("img_sync was true but not remotepool was specified")

		# debugging output
		print "mapping ", nas, ":", zpool, "/", volume, " on ", remotehost

		launcher = CommandLauncher()
		initiator = launcher.callListInitiator(remotehost)
		device = launcher.callAddHostStoragemap(nas, zpool, volume, remotehost, remotepool, size, sync,initiator)
		self.beginOutput()
		self.addOutput(nas, device)
		self.endOutput(padChar='')
