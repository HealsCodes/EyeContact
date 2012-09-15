# EyeContact - EyeTV access for PLEX Media Server
# Copyright (C) 2011-2012 Rene Koecher <shirk@bitspin.org>
#
# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
# 
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
# 
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA

import re
import time
import socket
import select
import string

from BaseHTTPServer import BaseHTTPRequestHandler as TokenRequestHandler
from StringIO import StringIO

class TokenRequestParser(TokenRequestHandler):
	def __init__(self, request):
		self.rfile = StringIO(request)
		self.raw_requestline = self.rfile.readline()
		self.error_code = None
		self.error_message = None
		self.parse_request()

	def send_error(self, code, message):
		self.error_code = code
		self.error_message = message

def RunTokenProxy(runtime, port):
	res = { 'token' : '', 'error' : '' }
	try:
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

		sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
		sock.bind(('0.0.0.0', port))
		start = time.time()
		sock.listen(4)
		while time.time() - start < runtime:

			if not select.select([sock], [], [], 0.5)[0]:
				continue

			(conn, addr) = sock.accept()
			request = TokenRequestParser(conn.recv(4096))

			# discard invalid requests
			if request.error_code != None:
				conn.sendall('%s 400 Bad Request\r\n\r\n' % request.request_version)
				conn.close()
				continue

			# check the method
			if not request.command in [ 'GET', 'POST' ]:
				# not supported
				conn.sendall('%s 400 Bad Request\r\n\r\n' % request.request_version)
				conn.close()
				continue

			# check required fields
			if not 'host' in request.headers:
				# not supported
				conn.sendall('%s 400 Bad Request\r\n\r\n' % request.request_version)
				conn.close()
				continue

			# check for tokens :)
			if 'x-eyeconnect-token' in request.headers:
				res['token'] = request.headers['x-eyeconnect-token']
				start = 0 # force exit after request

			# extract the target host / port
			try:
				(host, port) = request.headers['host'].split(':')
			except ValueError:
				(host, port) = (request.headers['host'], '80')
			port = int(port)

			# connect to the target
			remote = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			remote.connect((host, port))

			# rebuild the request
			request_str = '%s %s %s\r\n' % (request.command, request.path.split(request.headers['host'])[-1], request.request_version)
			for k in request.headers.keys():
				request_str += '%s: %s\r\n' % (string.capwords(k, '-'), request.headers[k])
			request_str += '\r\n'
			remote.sendall(request_str)

			if request.command == 'POST':
				remote.sendall(self.rfile.read())

			# tunnel the response
			while select.select([remote], [], [], 1)[0]:
				data = remote.recv(128)
				conn.send(data)

			# go away!
			remote.close()
			conn.close()
	except Exception, e:
		res['error'] = str(e)

	finally:
		try:
			sock.close()
		except:
			pass

	if not res['token'] and res['error'] == '':
		res['error'] = 'timeout.'

	if res['token']:
		print 'Token: %s' % res['token']
	else:
		print 'No Token'
	return res

if __name__ == '__main__':
	RunTokenProxy(120, 2171)


