#
# $Id$
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
# $Log$
#

-include $(ROLLSROOT)/etc/Rolls.mk
include Rolls.mk

default: roll

all: base nas vm fe

reall:
	ssh nas-0-0 'service img-storage-nas restart'&
	ssh compute-0-1 'service img-storage-vm restart'&
	ssh compute-0-2 'service img-storage-vm restart'&
	ssh compute-0-3 'service img-storage-vm restart'&
	service img-storage-vm restart&

base:
	cd src/img-storage && make rpm
	scp RPMS/noarch/img-storage-6.2-1.noarch.rpm nas-0-0: && ssh nas-0-0 'yum reinstall ./img-storage-6.2-1.noarch.rpm' &
	scp RPMS/noarch/img-storage-6.2-1.noarch.rpm compute-0-1: && ssh compute-0-1 'yum reinstall ./img-storage-6.2-1.noarch.rpm'&
	scp RPMS/noarch/img-storage-6.2-1.noarch.rpm compute-0-2: && ssh compute-0-2 'yum reinstall ./img-storage-6.2-1.noarch.rpm'&
	scp RPMS/noarch/img-storage-6.2-1.noarch.rpm compute-0-3: && ssh compute-0-3 'yum reinstall ./img-storage-6.2-1.noarch.rpm'&
	scp RPMS/noarch/img-storage-6.2-1.noarch.rpm compute-0-4: && ssh compute-0-4 'yum reinstall ./img-storage-6.2-1.noarch.rpm'&
	scp RPMS/noarch/img-storage-6.2-1.noarch.rpm compute-0-5: && ssh compute-0-5 'yum reinstall ./img-storage-6.2-1.noarch.rpm'&
	yum reinstall RPMS/noarch/img-storage-6.2-1.noarch.rpm

nas:
	cd src/img-storage-nas && make rpm
	scp RPMS/noarch/img-storage-nas-6.2-0.noarch.rpm nas-0-0:
	ssh nas-0-0 'yum reinstall ./img-storage-nas-6.2-0.noarch.rpm'
	ssh nas-0-0 'service img-storage-nas restart'

vm:
	cd src/img-storage-vm && make rpm
	scp RPMS/noarch/img-storage-vm-6.2-0.noarch.rpm compute-0-1:
	ssh compute-0-1 'yum reinstall ./img-storage-vm-6.2-0.noarch.rpm'
	scp RPMS/noarch/img-storage-vm-6.2-0.noarch.rpm compute-0-2:
	ssh compute-0-2 'yum reinstall ./img-storage-vm-6.2-0.noarch.rpm'
	scp RPMS/noarch/img-storage-vm-6.2-0.noarch.rpm compute-0-3:
	ssh compute-0-3 'yum reinstall ./img-storage-vm-6.2-0.noarch.rpm'
	ssh compute-0-1 'service img-storage-vm restart'
	ssh compute-0-2 'service img-storage-vm restart'
	ssh compute-0-3 'service img-storage-vm restart'
	yum reinstall RPMS/noarch/img-storage-vm-6.2-1.noarch.rpm
	service img-storage-vm restart

fe:
	cd src/rocks-command-imgstorage && make rpm
	yum reinstall /usr/src/redhat/RPMS/x86_64/rocks-command-imgstorage-6.2-1.x86_64.rpm

test:
	nosetests tests
