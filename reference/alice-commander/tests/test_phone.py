import asyncio,json,tempfile,unittest,time
from pathlib import Path
from unittest.mock import patch,AsyncMock
from integrations.phone import security,phone_state,kdeconnect,adb_manager,scrcpy_manager

class PhoneSecurity(unittest.TestCase):
 def test_endpoint_must_match_trusted_lan_phone_and_tls_port(self):
  self.assertEqual(security.endpoint('192.168.1.124:37183','192.168.1.124'),'192.168.1.124:37183')
  for value in ('26.26.26.1:35825','192.168.1.123:37183','192.168.1.124:5555','192.168.0.19:37183','localhost:1234'):
   with self.subTest(value=value),self.assertRaises(ValueError):security.endpoint(value,'192.168.1.124')
 def test_urls_reject_credentials_tokens_and_executable_schemes(self):
  self.assertEqual(security.safe_url('https://example.com/docs'),'https://example.com/docs')
  for value in ('file:///etc/passwd','javascript:alert(1)','https://a:b@example.com','https://example.com?token=abc','https://example.com\n'):
   with self.assertRaises(ValueError):security.safe_url(value)
 def test_file_roots_symlinks_hidden_and_credentials(self):
  with tempfile.TemporaryDirectory() as t:
   home=Path(t);(home/'Downloads').mkdir();(home/'Downloads/good.txt').write_text('safe')
   self.assertEqual(security.safe_file(home/'Downloads/good.txt',home),home/'Downloads/good.txt')
   (home/'Downloads/link.txt').symlink_to(home/'Downloads/good.txt')
   for name in ('secret.txt','.env','archive.zip','script.sh'):
    p=home/'Downloads'/name;p.write_text('x')
    with self.assertRaises(ValueError):security.safe_file(p,home)
   with self.assertRaises(ValueError):security.safe_file(home/'Downloads/link.txt',home)
   with self.assertRaises(ValueError):security.safe_file('/etc/passwd',home)
 def test_connection_cooldown_survives_new_invocation(self):
  with tempfile.TemporaryDirectory() as t,patch.object(phone_state,'DATA',Path(t)):
   phone_state.reserve('connect',15)
   with self.assertRaises(ValueError):phone_state.reserve('connect',15)
 def test_phone_commands_not_claimed_cli_verified(self):
  from voice.catalog import initial
  rows=initial();self.assertEqual(rows['phone.battery']['cli_status'],'not_tested');self.assertFalse(rows['phone.battery']['physical_confirmed'])
 def test_single_canonical_phone_mapping_and_old_commands_preserved(self):
  from commands.registry import COMMANDS
  from voice.scenarios import SCENARIOS
  from integrations.phone.phone_commands import ROWS
  self.assertEqual(len(ROWS),9);self.assertEqual(len(COMMANDS),39)
  for cid,phrase,name in ROWS:self.assertEqual(SCENARIOS[name],cid)

class PhoneActions(unittest.IsolatedAsyncioTestCase):
 async def test_foreign_scrcpy_unit_is_never_stopped(self):
  with patch.object(scrcpy_manager,'state',AsyncMock(return_value={'running':True,'owned':False})),patch.object(scrcpy_manager,'run',AsyncMock()) as run:
   with self.assertRaises(ValueError):await scrcpy_manager.stop()
   run.assert_not_called()
 async def test_stop_only_owned_unit(self):
  with patch.object(scrcpy_manager,'state',AsyncMock(return_value={'running':True,'owned':True})),patch.object(scrcpy_manager,'run',AsyncMock()) as run:
   await scrcpy_manager.stop();self.assertEqual(run.call_args.args[0],['/usr/bin/systemctl','--user','stop','alice-phone-mirror.service'])
 async def test_station_rejected_before_any_adb_shell(self):
  with patch.object(adb_manager,'devices',AsyncMock(return_value={'station':{'state':'device','description':'product:yandexmini'}})),patch.object(adb_manager,'run',AsyncMock()) as run:
   with self.assertRaises(ValueError):await adb_manager.identity('station')
   run.assert_not_called()
 async def test_confirm_dialog_keeps_link_out_of_argv(self):
  from integrations.phone import dialog
  with patch.object(dialog,'run',AsyncMock()) as run:
   await dialog.confirmed('https://example.com/private-data')
   self.assertNotIn('private-data',' '.join(run.call_args.args[0]))
   self.assertIn(b'private-data',run.call_args.kwargs['input_data'])
 async def test_share_sends_url_over_dbus_without_process_arguments(self):
  import dbus
  method=__import__('unittest.mock',fromlist=['Mock']).Mock();obj=__import__('unittest.mock',fromlist=['Mock']).Mock();obj.get_dbus_method.return_value=method;bus=__import__('unittest.mock',fromlist=['Mock']).Mock();bus.get_object.return_value=obj
  with patch.object(kdeconnect,'plugin',AsyncMock(return_value='trusted')),patch('dbus.SessionBus',return_value=bus),patch.object(kdeconnect,'run',AsyncMock()) as process:
   await kdeconnect.share('https://example.com/private');method.assert_called_once_with('https://example.com/private',timeout=10);process.assert_not_called()
 async def test_adb_reconnect_rejects_unenrolled_network_service(self):
  c={'adb':{'serial':'192.168.1.124:32931','mdns_alias':'adb-phone._adb-tls-connect._tcp','fingerprint':'expected'}}
  with patch.object(adb_manager,'require_enabled',return_value=c),patch.object(adb_manager,'trusted',AsyncMock(side_effect=ValueError('offline'))),patch.object(kdeconnect,'addresses',AsyncMock(return_value=['192.168.1.124'])),patch.object(adb_manager,'run',AsyncMock(return_value='adb-other _adb-tls-connect._tcp 192.168.1.124:32931')) as run:
   self.assertEqual(await adb_manager.reconnect(),'offline');self.assertEqual(run.await_count,1)
 async def test_adb_reconnect_checks_identity_before_saving(self):
  c={'adb':{'serial':'192.168.1.124:32931','mdns_alias':'adb-phone._adb-tls-connect._tcp','fingerprint':'expected'}}
  with patch.object(adb_manager,'require_enabled',return_value=c),patch.object(adb_manager,'trusted',AsyncMock(side_effect=ValueError('offline'))),patch.object(kdeconnect,'addresses',AsyncMock(return_value=['192.168.1.124'])),patch.object(adb_manager,'run',AsyncMock(side_effect=['adb-phone _adb-tls-connect._tcp 192.168.1.124:32932','connected to 192.168.1.124:32932','disconnected'])) as run,patch.object(adb_manager,'identity',AsyncMock(return_value={'fingerprint':'different'})),patch.object(adb_manager,'write') as write:
   self.assertEqual(await adb_manager.reconnect(),'offline');write.assert_not_called();self.assertEqual(run.await_args_list[-1].args[0][:2],['/usr/bin/adb','disconnect'])
 async def test_reconnect_only_uses_previously_enrolled_alias(self):
  c={'adb':{'serial':'192.168.1.124:32931','mdns_alias':'adb-phone._adb-tls-connect._tcp','fingerprint':'expected'}}
  with patch.object(adb_manager,'require_enabled',return_value=c),patch.object(adb_manager,'identity',AsyncMock(side_effect=[ValueError('offline'),{'fingerprint':'expected'}])) as identify,patch.object(adb_manager,'write') as write:
   self.assertEqual(await adb_manager.trusted(),'adb-phone._adb-tls-connect._tcp');self.assertEqual(identify.await_args_list[1].args[0],'adb-phone._adb-tls-connect._tcp');write.assert_called_once()
 async def test_reconnect_alias_with_wrong_identity_is_rejected(self):
  c={'adb':{'serial':'192.168.1.124:32931','mdns_alias':'adb-phone._adb-tls-connect._tcp','fingerprint':'expected'}}
  with patch.object(adb_manager,'require_enabled',return_value=c),patch.object(adb_manager,'identity',AsyncMock(side_effect=[ValueError('offline'),{'fingerprint':'different'}])),patch.object(adb_manager,'write') as write:
   with self.assertRaises(ValueError):await adb_manager.trusted()
   write.assert_not_called()
 async def test_battery_falls_back_only_to_verified_phone(self):
  with patch.object(kdeconnect,'plugin',AsyncMock(return_value='trusted')),patch.object(kdeconnect,'dbus',AsyncMock(return_value='-1')),patch.object(adb_manager,'trusted',AsyncMock(return_value='authorised')) as verified,patch.object(kdeconnect,'run',AsyncMock(return_value='  level: 67\n  status: 2\n')) as run:
   result=await kdeconnect.battery();self.assertEqual(result['battery_percent'],67);self.assertEqual(result['battery_source'],'ADB (только чтение)');verified.assert_awaited_once();self.assertEqual(run.call_args.args[0],['/usr/bin/adb','-s','authorised','shell','dumpsys','battery'])
 async def test_battery_fallback_rejects_untrusted_adb(self):
  with patch.object(kdeconnect,'plugin',AsyncMock(return_value='trusted')),patch.object(kdeconnect,'dbus',AsyncMock(return_value='-1')),patch.object(adb_manager,'trusted',AsyncMock(side_effect=ValueError('untrusted'))),patch.object(kdeconnect,'run',AsyncMock()) as run:
   with self.assertRaises(ValueError):await kdeconnect.battery()
   run.assert_not_called()
 async def test_connect_is_idempotent_when_phone_already_connected(self):
  with patch.object(kdeconnect,'trusted',AsyncMock(return_value='phone')),patch.object(kdeconnect,'reserve') as reserve,patch.object(kdeconnect,'run',AsyncMock()) as run:
   result=await kdeconnect.refresh();self.assertTrue(result['already_connected']);reserve.assert_not_called();run.assert_not_called()
 async def test_reachable_phone_retries_with_limited_refresh(self):
  values=['true','phone','false','true','true']
  with patch.object(kdeconnect,'require_enabled',return_value={'kde_id':'trusted'}),patch.object(kdeconnect,'dbus',AsyncMock(side_effect=values)),patch.object(kdeconnect,'reserve') as reserve,patch.object(kdeconnect,'run',AsyncMock()) as run,patch('integrations.phone.kdeconnect.asyncio.sleep',AsyncMock()):
   self.assertEqual(await kdeconnect.trusted(),'trusted');reserve.assert_called_once_with('auto_refresh',20);self.assertEqual(run.await_args.args[0],['/usr/bin/kdeconnect-cli','--refresh'])
 async def test_unpaired_device_is_rejected(self):
  with patch.object(kdeconnect,'require_enabled',return_value={'kde_id':'trusted'}),patch.object(kdeconnect,'dbus',AsyncMock(return_value='false')):
   with self.assertRaises(ValueError):await kdeconnect.trusted()
 async def test_changed_adb_identity_rejected(self):
  with patch.object(adb_manager,'require_enabled',return_value={'adb':{'serial':'phone','fingerprint':'expected'}}),patch.object(adb_manager,'identity',AsyncMock(return_value={'fingerprint':'different'})):
   with self.assertRaises(ValueError):await adb_manager.trusted()
 async def test_disable_rejects_before_kde_or_adb(self):
  from integrations.phone.phone_commands import execute
  with patch('integrations.phone.phone_commands.require_enabled',side_effect=ValueError('disabled')),patch.object(kdeconnect,'battery',AsyncMock()) as battery:
   with self.assertRaises(ValueError):await execute('phone.battery')
   battery.assert_not_called()
 async def test_lock_never_falls_back_to_adb(self):
  from integrations.phone.phone_commands import execute
  with patch('integrations.phone.phone_commands.require_enabled',return_value={}),patch('integrations.phone.phone_commands.outcome'),patch.object(adb_manager,'run',AsyncMock()) as run:
   with self.assertRaises(ValueError):await execute('phone.lock')
   run.assert_not_called()
