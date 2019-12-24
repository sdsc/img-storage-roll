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

import os.path

import rocks.commands
import rocks.db.mappings.img_manager
import rocks.db.vmextend



class Command(rocks.commands.list.host.command):
	"""
	Lists the nas of each vm

	<arg optional='1' type='string' name='host' repeat='1'>
	Zero, one or more host names. If no host names are supplied,
	information for all hosts will be listed.
	</arg>

	<example cmd='list host vm compute-0-0'>
	List the nas setting for for compute-0-0.
	</example>

	"""

	def run(self, params, args):
		self.beginOutput()

		for node in self.newdb.getNodesfromNames(args,
				preload=['vm_defs', 'vm_defs.disks',
				'vm_defs.disks.img_nas_server']):

			if not node.vm_defs:
				continue

			# disks
			for disk in node.vm_defs.disks:

				if disk.img_nas_server:
					name = disk.img_nas_server.server_name
					zpool = disk.img_nas_server.zpool_name
				else:
					name = None
					zpool = None

				self.addOutput(node.name, [name, zpool])

		self.endOutput(['vm-host','nas', 'zpool'])




RollName = "img-storage"
