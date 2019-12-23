"""Smoke test for atvremote."""

import sys

from contextlib import contextmanager
from io import StringIO

from aiohttp.test_utils import (AioHTTPTestCase, unittest_run_loop)

import pyatv
from pyatv import __main__ as atvremote
from tests import zeroconf_stub
from tests.utils import stub_sleep
from tests.airplay.fake_airplay_device import DEVICE_PIN, DEVICE_CREDENTIALS
from tests.mrp.fake_mrp_atv import (
    FakeAppleTV, AppleTVUseCases)


IP_1 = '10.0.0.1'
IP_2 = '127.0.0.1'
DMAP_ID = 'dmap_id'
MRP_ID = 'mrp_id'
AIRPLAY_ID = 'AA:BB:CC:DD:EE:FF'


@contextmanager
def capture_output(argv, inputs):
    new_out, new_err, new_in = StringIO(), StringIO(), StringIO(inputs)
    old_out, old_err, old_in = sys.stdout, sys.stderr, sys.stdin
    old_argv = sys.argv
    try:
        sys.stdout, sys.stderr, sys.stdin = new_out, new_err, new_in
        sys.argv = argv
        yield sys.stdout, sys.stderr
    finally:
        sys.stdout, sys.stderr, sys.stdin = old_out, old_err, old_in
        sys.argv = old_argv


class AtvremoteTest(AioHTTPTestCase):

    def setUp(self):
        AioHTTPTestCase.setUp(self)
        stub_sleep()
        self.setup_environment()
        self.stdout = None
        self.stderr = None
        self.retcode = None
        self.inputs = []

    def setup_environment(self):
        airplay_port = self.server.port

        services = []
        services.append(zeroconf_stub.homesharing_service(
                DMAP_ID, b'Apple TV 1', IP_1, b'aaaa'))
        services.append(zeroconf_stub.mrp_service(
                'DDDD', b'Apple TV 2', IP_2, MRP_ID, port=self.fake_atv.port))
        services.append(zeroconf_stub.airplay_service(
                'Apple TV 2', IP_2, AIRPLAY_ID, port=airplay_port))
        zeroconf_stub.stub(pyatv, *services)

        self.usecase.airplay_playback_playing()
        self.usecase.airplay_playback_idle()

    async def get_application(self, loop=None):
        self.fake_atv = FakeAppleTV(self, self.loop)
        self.usecase = AppleTVUseCases(self.fake_atv)
        return self.fake_atv.app

    def user_input(self, text):
        self.inputs.append(text)

    def has_output(self, *strings):
        for string in strings:
            self.assertIn(string, self.stdout)

    def exit_ok(self):
        self.assertEqual(self.retcode, 0)

    async def atvremote(self, *args):
        argv = ['atvremote'] + list(args)
        inputs = '\n'.join(self.inputs) + '\n'
        with capture_output(argv, inputs) as (out, err):
            self.retcode = await atvremote.appstart(self.loop)
            self.stdout = out.getvalue()
            self.stderr = err.getvalue()

    @unittest_run_loop
    async def test_scan_devices(self):
        await self.atvremote("scan")
        self.has_output("Apple TV 1",
                        "Apple TV 2",
                        IP_1,
                        IP_2,
                        MRP_ID,
                        AIRPLAY_ID,
                        DMAP_ID)
        self.exit_ok()

    @unittest_run_loop
    async def test_pair_airplay(self):
        self.user_input(str(DEVICE_PIN))
        await self.atvremote(
            "--address", IP_2,
            "--protocol", "airplay",
            "--id", MRP_ID,
            "--airplay-credentials", DEVICE_CREDENTIALS,
            "pair")
        self.has_output("Enter PIN",
                        "seems to have succeeded",
                        DEVICE_CREDENTIALS)

    @unittest_run_loop
    async def test_airplay_play_url(self):
        self.user_input(str(DEVICE_PIN))
        await self.atvremote(
            "--id", MRP_ID,
            "--airplay-credentials", DEVICE_CREDENTIALS,
            "play_url=http://fake")
        self.exit_ok()

    @unittest_run_loop
    async def test_mrp_idle(self):
        await self.atvremote("--id", MRP_ID, "playing")
        self.has_output("Media type: Unknown", "Device state: Idle")
        self.exit_ok()

    @unittest_run_loop
    async def test_manual_connect(self):
        self.user_input(str(DEVICE_PIN))
        await self.atvremote(
            "--address", IP_2,
            "--protocol", "mrp",
            "--port", str(self.fake_atv.port),
            "--id", MRP_ID,
            "--manual",
            "playing")
        self.has_output("Media type: Unknown", "Device state: Idle")
        self.exit_ok()