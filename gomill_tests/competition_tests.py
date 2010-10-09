"""Tests for competitions.py"""

import os

from gomill import competitions

from gomill_tests import gomill_test_support

def make_tests(suite):
    suite.addTests(gomill_test_support.make_simple_tests(globals()))

def test_player_command(tc):
    Player_config = competitions.Player_config
    comp = competitions.Competition('test')
    config = {
        'players' : {
            't1' : Player_config("test"),
            't2' : Player_config("/bin/test foo"),
            't3' : Player_config(["bin/test", "foo"]),
            't4' : Player_config("~/test foo"),
            }
        }
    comp.initialise_from_control_file(config)
    tc.assertEqual(comp.players['t1'].cmd_args, ["test"])
    tc.assertEqual(comp.players['t2'].cmd_args, ["/bin/test", "foo"])
    tc.assertEqual(comp.players['t3'].cmd_args, ["bin/test", "foo"])
    tc.assertEqual(comp.players['t4'].cmd_args,
                   [os.path.expanduser("~") + "/test", "foo"])

def test_player_is_reliable_scorer(tc):
    Player_config = competitions.Player_config
    comp = competitions.Competition('test')
    config = {
        'players' : {
            't1' : Player_config("test"),
            't2' : Player_config("test", is_reliable_scorer=False),
            't3' : Player_config("test", is_reliable_scorer=True),
            }
        }
    comp.initialise_from_control_file(config)
    tc.assertTrue(comp.players['t1'].is_reliable_scorer)
    tc.assertFalse(comp.players['t2'].is_reliable_scorer)
    tc.assertTrue(comp.players['t3'].is_reliable_scorer)

def test_player_cwd(tc):
    Player_config = competitions.Player_config
    comp = competitions.Competition('test')
    comp.set_base_directory("/base")
    config = {
        'players' : {
            't1' : Player_config("test"),
            't2' : Player_config("test", cwd="/abs"),
            't3' : Player_config("test", cwd="rel/sub"),
            't4' : Player_config("test", cwd="."),
            't5' : Player_config("test", cwd="~/tmp/sub"),
            }
        }
    comp.initialise_from_control_file(config)
    tc.assertIsNone(comp.players['t1'].cwd)
    tc.assertEqual(comp.players['t2'].cwd, "/abs")
    tc.assertEqual(comp.players['t3'].cwd, "/base/rel/sub")
    tc.assertEqual(comp.players['t4'].cwd, "/base/.")
    tc.assertEqual(comp.players['t5'].cwd, os.path.expanduser("~") + "/tmp/sub")

def test_player_stderr(tc):
    Player_config = competitions.Player_config
    comp = competitions.Competition('test')
    config = {
        'players' : {
            't1' : Player_config("test"),
            't2' : Player_config("test", discard_stderr=True),
            't3' : Player_config("test", discard_stderr=False),
            }
        }
    comp.initialise_from_control_file(config)
    tc.assertIs(comp.players['t1'].discard_stderr, False)
    tc.assertIs(comp.players['t2'].discard_stderr, True)
    tc.assertIs(comp.players['t3'].discard_stderr, False)

def test_player_startup_gtp_commands(tc):
    Player_config = competitions.Player_config
    comp = competitions.Competition('test')
    config = {
        'players' : {
            't1' : Player_config(
                "test", startup_gtp_commands=["foo"]),
            't2' : Player_config(
                "test", startup_gtp_commands=["foo bar baz"]),
            't3' : Player_config(
                "test", startup_gtp_commands=[["foo", "bar", "baz"]]),
            't4' : Player_config(
                "test", startup_gtp_commands=[
                    "xyzzy test",
                    ["foo", "bar", "baz"]]),
            }
        }
    comp.initialise_from_control_file(config)
    tc.assertListEqual(comp.players['t1'].startup_gtp_commands,
                       [("foo", [])])
    tc.assertListEqual(comp.players['t2'].startup_gtp_commands,
                       [("foo", ["bar", "baz"])])
    tc.assertListEqual(comp.players['t3'].startup_gtp_commands,
                       [("foo", ["bar", "baz"])])
    tc.assertListEqual(comp.players['t4'].startup_gtp_commands,
                       [("xyzzy", ["test"]),
                        ("foo", ["bar", "baz"])])

