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
import sys
import time
import cPickle
import tokenproxy

TITLE = 'EyeContact'
PREFS_URL = '/:/plugins/org.bitspin.plexapp.eyecontact/prefs/set'

PREFS_HOST         = 'eyetv_live_host'
PREFS_PORT         = 'eyetv_live_port'
PREFS_PASSCODE     = 'eyetv_live_pass'
PREFS_DEVID        = 'eyetv_live_devid'
PREFS_TOKEN        = 'eyetv_live_token'
PREFS_HLS          = 'eyetv_live_laika'
PREFS_LOFI         = 'eyetv_live_lofi'

#=============================================================================
def ServiceRequest(url):
	return cPickle.loads(String.Decode(URLService.NormalizeURL('eyetv://%s' % url)))

def IsUp():
	return ServiceRequest('status')['isUp']

def TsUNIXToNSDate(seconds):
	"""
	Given the current seconds since epoch return a dst-adjusted NSDate version
	"""
	try:
		ts = time.localtime(seconds)
		if ts.tm_isdst == 1:
			seconds = seconds - 3600
		return long(seconds - time.mktime(time.strptime('1.1.2001', '%d.%m.%Y')))
	except Exception, e:
		return 0

def ChangePref(key, value):
	addr = Network.Address
	if addr == None:
		if Network.PublicAddress != None:
			addr = Network.PublicAddress
			Log('Need to use Network.PublicAddress since Address is None!!')
		else:
			Log('Need to guess Network.Address since it\'s None!!')
			addr = '127.0.0.1'

	if value == None:
		Log('Unable to ChangePref(%s, %s) - None is not a supported value!' % (str(key), str(value)))
		return False

	try:
		action = HTTP.Request(url='http://%s:32400%s?%s=%s' % (addr, PREFS_URL, String.URLEncode(key), String.URLEncode(value)))
		action.load()

		mo = MessageContainer('Result:', action.content)
	except Exception, e:
		mo = MessageContainer('Result:', str(e))

	return mo

def SortedKeys(keys):
	try:
		s = [long(x) for x in keys]
	except ValueError:
		s = list(keys)
	s.sort()
	return [str(x) for x in s]

#=============================================================================

def Start():
	Plugin.AddViewGroup("Details", viewMode="InfoList", mediaType="items")
	Plugin.AddViewGroup("List", viewMode="List", mediaType="items")
	Plugin.AddViewGroup("EPGInfo", viewMode="MediaPreview", mediaType="movies")

	ObjectContainer.title1 = TITLE
	ObjectContainer.view_group = 'List'
	Log('Started.')

def ValidatePrefs():
	res = DelayedValidation(do_updates=False)

	if (res):
		title, message = res
		return MessageContainer(title, message)
	return True

def DelayedValidation(do_updates=True):
	res_msgs  = []

	if Prefs[PREFS_DEVID].upper() == 'BROWSER':
		if Prefs[PREFS_LOFI] == False:
			if do_updates:
				ChangePref(PREFS_LOFI, 'true')

			res_msgs.append(L('PREFS_CHANGED_EPG'))

	if Prefs[PREFS_TOKEN]:
		if re.match('[a-fA-F0-9]{32}', Prefs[PREFS_TOKEN]) == None:
			if do_updates:
				ChangePref(PREFS_LOFI, 'true')

			res_msgs.append(L('PREFS_TOKEN_INVALID'))
			res_msgs.append(L('PREFS_CHANGED_EPG'))

	if Prefs[PREFS_HOST].lower() in ['127.0.0.1', 'localhost']:
			if do_updates:
				if Network.Address == None:
					ChangePref(PREFS_HOST, str(Network.PublicAddress))
				else:
					ChangePref(PREFS_HOST, str(Network.Address))

			res_msgs.append(F('PREFS_CHANGED_HOST', Network.Address))

	if res_msgs:
		return (L('PREFS_CHANGED_TITLE'), '\n'.join([str(msg) for msg in res_msgs]))
	return None

@handler('/video/eyecontact', TITLE)
def MainMenu():
	DelayedValidation()
	
	is_up = IsUp()
	if is_up:
		cap = 'EyeTV @ %s [online]' % Prefs[PREFS_HOST]
	else:
		cap = 'EyeTV @ %s [offline]' % Prefs[PREFS_HOST]

	oc = ObjectContainer(title2=cap, no_cache=True)

	if is_up:
		oc.add(DirectoryObject(title=L('MAIN_MENU_CHANNELS'), key=Callback(FavoritesMenu)))
		if Prefs[PREFS_LOFI] == False and Prefs[PREFS_DEVID].upper() in ['IPHONE', 'IPAD']:
			oc.add(DirectoryObject(title=L('MAIN_MENU_EPG'), key=Callback(FavoritesMenu, context='epg')))
			oc.add(DirectoryObject(title=L('MAIN_MENU_SCHEDULES'), key=Callback(SchedulesMenu)))

	oc.add(DirectoryObject(title=L('MAIN_MENU_PREFS'), key=Callback(PrefsMenu)))

	return oc

@route('/video/eyecontact/prefs')
def PrefsMenu():
	DelayedValidation()
	oc = ObjectContainer(no_cache=True)

	if not Prefs[PREFS_LOFI]:
		oc.add(DirectoryObject(title=L('PREFS_TOKEN_WIZARD'), key=Callback(TokenScanWizard, step='1')))
	oc.add(PrefsObject(title=L('PREFS_SETTINGS')))
	return oc

@route('/video/eyecontact/lists')
def FavoritesMenu(context = None):
	if IsUp() == False:
		return MessageContainer(L('DEVICE_OFFLINE_TITLE'), L('DEVICE_OFFLINE_MSG'))

	lists = ServiceRequest('favorites')
	oc = ObjectContainer(title2=L('MAIN_MENU_CHANNELS'), no_cache=True)

	if context == 'epg':
		callback    = EPGList
	else:
		callback    = ChannelList

	lists.sort(cmp=lambda a,b: int(long(a['uniqueID']) - long(b['uniqueID'])))
	for l in lists:
		if l['uniqueID'] == '0':
			oc.add(DirectoryObject(title=L('CHANNELS_ALL_CHANNELS'), key=Callback(callback, uuid=l['uniqueID'])))
		else:
			oc.add(DirectoryObject(title=l['name'], key=Callback(callback, uuid=l['uniqueID'])))
	return oc

@route('/video/eyecontact/schedules')
def SchedulesMenu():
	if IsUp() == False:
		return MessageContainer(L('DEVICE_OFFLINE_TITLE'), L('DEVICE_OFFLINE_MSG'))

	schedules = ServiceRequest('schedules')
	oc = ObjectContainer(title2=L('MAIN_MENU_SCHEDULES'), no_cache=True)

	if not schedules:
		oc.add(DirectoryObject(title=L('SCHEDULES_LIST_EMPTY'), key="#"))
		return oc

	schedules.sort(cmp=lambda a,b: int(a['start'] - b['start']))
	for schedule in schedules:

		date  = time.strftime('%x %X - ', time.localtime(schedule['start']))
		title = schedule['title']
		title = date + title

		oc.add(PopupDirectoryObject(
			title   = title,
			key     = Callback(EPGActions, title=schedule['channel'], service=schedule['service'], uuid=schedule['uuid'], mode='epg2'),
			tagline = schedule['title'],
			summary = '%s%smin\n%s' % (date, schedule['duration'] / 60, schedule['summary'])
		))
	return oc

@route('/video/eyecontact/channels/{uuid}')
def ChannelList(uuid):
	if IsUp() == False:
		return MessageContainer(L('DEVICE_OFFLINE_TITLE'), L('DEVICE_OFFLINE_MSG'))

	channels = ServiceRequest('channels/%s' % uuid)
	oc  = ObjectContainer(title2=L('CHANNELS_TITLE'), view_group='Details', content=ContainerContent.Playlists, no_cache=True)

	for nr in SortedKeys(channels.keys()):
		service = channels[nr]['service']
		uuid    = channels[nr]['uuid']
		vo = URLService.MetadataObjectForURL('eyetv://show/%s/%s' % (service, uuid))

		if channels[nr]['live']:
			vo.title = '%3s - %s - "%s"' % (nr, channels[nr]['name'], vo.title)
		else:
			vo.title = '%3s - %s' % (nr, channels[nr]['name'])

		oc.add(vo)
	return oc

@route('/video/eyecontact/epg/{uuid}')
def EPGList(uuid):
	if IsUp() == False:
		return MessageContainer(L('DEVICE_OFFLINE_TITLE'), L('DEVICE_OFFLINE_MSG'))

	channels = ServiceRequest('channels/%s' % uuid)
	oc = ObjectContainer(title2=L('EPG_LIST_TITLE'), view_group='Details', content=ContainerContent.Playlists, no_cache=True)

	for nr in SortedKeys(channels.keys()):
		if not channels[nr]['live']:
			channels[nr]['live'] = '00:00: %s' % L('EPG_NOT_AVAILABLE')
		if not channels[nr]['next']:
			channels[nr]['next'] = '00:00: %s' % L('EPG_NOT_AVAILABLE')

		oc.add(PopupDirectoryObject(
			title   = '%3s - %s - "%s"' % (nr, channels[nr]['name'], channels[nr]['live']),
			key     = Callback(EPGActions, title=channels[nr]['name'], service=channels[nr]['service'], uuid=channels[nr]['uuid'], mode='epg1'),
			tagline = channels[nr]['live'],
			summary = '%s\n%s' % (channels[nr]['live'], channels[nr]['next'])
		))

	return oc

@route('/video/eyecontact/epg/{service}/{uuid}')
def EPGActions(title, mode, service, uuid):
	oc = ObjectContainer(no_history=True, no_cache=True)
	vo = URLService.MetadataObjectForURL('eyetv://show/%s/%s' % (service, uuid))
	vo.title = F('CHANNEL_WATCH_NOW', title)
	oc.add(vo)
	if not uuid == '0000':
		oc.add(DirectoryObject(title=L('CHANNEL_DETAILS')  , key=Callback(EPGActionDetails, service=service, uuid=uuid)))

		if mode == 'epg1':
			oc.add(DirectoryObject(title=L('CHANNEL_EPG')  , key=Callback(EPGActionList, service=service, uuid=uuid)))
		
		elif mode == 'epg2':
			data = ServiceRequest('info/%s|%s' % (service,uuid))
			if data['scheduled']:
				oc.add(DirectoryObject(title=L('SHOW_RECORD_DEL'), key=Callback(RecordControl, service=service, uuid=uuid, cmd='off')))
			else:
				oc.add(DirectoryObject(title=L('SHOW_RECORD_SET'), key=Callback(RecordControl, service=service, uuid=uuid, cmd='on')))
	return oc

@route('/video/eyecontact/epg/{service}/{uuid}/info')
def EPGActionDetails(service, uuid):
	if IsUp() == False:
		return MessageContainer(L('DEVICE_OFFLINE_TITLE'), L('DEVICE_OFFLINE_MSG'))

	oc = ObjectContainer(view_group='EPGInfo', no_history=True, no_cache=False)
	oc.add(URLService.MetadataObjectForURL('eyetv://show/%s/%s' % ('service', uuid)))
	return oc

@route('/video/eyecontact/epg/{service}/{uuid}/full')
def EPGActionList(service, uuid):
	if IsUp() == False:
		return MessageContainer(L('DEVICE_OFFLINE_TITLE'), L('DEVICE_OFFLINE_MSG'))

	shows = ServiceRequest('epg/%s' % service)
	oc = ObjectContainer(title2=L('EPG_LIST_TITLE'), view_group='Details', content=ContainerContent.Playlists, no_cache=True)

	for show in shows:
		if show['scheduled']:
			show['label'] = '[REC] ' + show['label']

		oc.add(PopupDirectoryObject(
			title   = show['label'],
			key     = Callback(EPGActions, title=show['channel'], service=service, uuid=show['uuid'], mode='epg2'),
			tagline = show['name'],
			summary = show['summary']
		))

	return oc

@route('/video/eyecontact/record/{service}/{uuid}/{cmd}')
def RecordControl(service, uuid, cmd):
	res = ServiceRequest('record/%s/%s/%s' % (service, uuid, cmd))
	if cmd == 'on':
		if res:
			return MessageContainer(L('SHOW_RECORD_SCHEDULED_TITLE'), L('SHOW_RECORD_SCHEDULED_MSG'))
		else:
			return MessageContainer(L('SHOW_RECORD_FAILED_TITLE'), L('SHOW_RECORD_FAILED_MSG'))

@route('/video/eyecontact/tokenscan/{step}')
def TokenScanWizard(step):
	if Prefs[PREFS_DEVID].upper() == 'BROWSER':
		return MessageContainer(L('FEATURE_UNAVAIL_TITLE'), L('FEATURE_UNAVAIL_MSG'))

	oc = ObjectContainer(title2='Step %s/9' % step, no_history=True, no_cache=True, replace_parent=True)

	title = L('PREFS_TOKEN_WIZ_NEXT')
	thumb = R('%s_wiz_step%s.png' % (Prefs[PREFS_DEVID], step))

	if step == '1':
		message = F('PREFS_TOKEN_WIZ_STEP1', Prefs[PREFS_DEVID])
		Log('TokenScanWizard: Step 1')

	elif step in ['2', '3', '4', '6', '7']:
		message = L('PREFS_TOKEN_WIZ_STEP' + step)
		Log('TokenScanWizard: Step %s' % step)

	elif step == '5':
		message = F('PREFS_TOKEN_WIZ_STEP5', str(Network.Address), str(Network.PublicAddress))
		Log('TokenScanWizard: Step 5 (%s, %s)' % (str(Network.Address), str(Network.PublicAddress)))

	elif step == '8':
		message = F('PREFS_TOKEN_WIZ_STEP8', Prefs[PREFS_DEVID])
		Log('TokenScanWizard: Step 8 (%s)' % Prefs[PREFS_DEVID])

	elif step == '9':
		Log('TokenScanWizard: Step 9')
		res = tokenproxy.RunTokenProxy(20, 2171)
		Log('res = %s' % str(res))

		if res['error']:
			oc.header = L('ERROR_TITLE')
			oc.message = res['error']
			message = F('PREFS_TOKEN_WIZ_STEP9_0', res['error'])
		else:
			message  = F('PREFS_TOKEN_WIZ_STEP9_1', res['token'])
			message += L('PREFS_TOKEN_WIZ_STEP9_2')
			thumb = R('%s_wiz_step%s_ok.png' % (Prefs[PREFS_DEVID], step))

			ChangePref(PREFS_TOKEN, res['token'])

		title = L('PREFS_TOKEN_WIZ_DONE')
		oc.add(DirectoryObject(title=title, thumb=thumb, summary=message, key=Callback(MainMenu)))
		return oc

	menu = DirectoryObject(title=title, summary=message, key=Callback(TokenScanWizard, step=str(long(step) + 1)))
	if thumb != None:
		menu.thumb = thumb
	oc.add(menu)
	return oc

