import asyncio,json,unittest,tempfile
from pathlib import Path
from unittest.mock import AsyncMock,patch
from agent.router import Router
from agent.desktop import Desktop,ROOT,process
from commands.registry import COMMANDS
from voice.bridge import status

class Safety(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name);(root/'data').mkdir()
        self.rootpatch=patch('agent.router.ROOT',root);self.rootpatch.start()
    async def asyncTearDown(self):
        self.rootpatch.stop();self.tmp.cleanup()
    async def test_unknown_and_arguments(self):
        r=Router()
        for cid,args in [('exec',{}),('terminal.open',{'argv':['rm']}),('terminal.open;id',{}),(None,{})]:
            with self.assertRaises(ValueError):await r.execute(cid,args)
    async def test_rate_and_concurrency(self):
        r=Router();r.desktop.run=AsyncMock(return_value={})
        await r.execute('system.memory')
        with self.assertRaises(ValueError):await r.execute('system.memory')
        await r.lock.acquire()
        try:
            with self.assertRaises(ValueError):await r.execute('system.health')
        finally:r.lock.release()
    async def test_path_escape(self):
        with patch('agent.desktop.Path.read_text',return_value='{}'), patch('agent.desktop.json.loads',return_value={'project':'/etc','allowed_directories':[str(ROOT)]}):
            with self.assertRaises(ValueError):Desktop().project()
    async def test_timeout_kills(self):
        with self.assertRaises(RuntimeError):await process(['/usr/bin/sleep','5'],timeout=.05)
    async def test_voice_fails_closed(self):
        self.assertFalse(status()['wake_effect_enabled']);self.assertFalse(status()['wake_verified'])
        self.assertEqual(len([cid for cid in COMMANDS if not cid.startswith("phone.")]),30)
    async def test_rgb_only_coordinator(self):
        from integrations import rgb
        with patch.object(rgb,'call',new=AsyncMock(return_value={'accepted':True})) as call:
            await rgb.action('rgb.rainbow');self.assertEqual(call.call_args.args[0],'/v1/preview')
            self.assertLessEqual(call.call_args.args[1]['duration'],2)
    async def test_fixed_test_profile(self):
        with patch.object(Desktop,'project',return_value=__import__('pathlib').Path('/tmp')):
            with self.assertRaises(ValueError):await Desktop().run('project.test')

if __name__=='__main__':unittest.main()
