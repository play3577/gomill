"""Organise processing jobs based around playing many GTP games."""

import os
import sys

from gomill import game_jobs
from gomill import gtp_controller
from gomill import handicap_layout
from gomill.settings import *


def log_discard(s):
    pass

NoGameAvailable = object()

class CompetitionError(StandardError):
    """Error from competition code.

    This is intended for errors from user-provided functions, but it might also
    indicate a bug in tuner code.

    The ringmaster should display the error and terminate immediately.

    """

class ControlFileError(StandardError):
    """Error interpreting the control file."""


class Player_config(object):
    """Player description for use in control files."""
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

class Control_file_token(object):
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return "<%s>" % self.name


_player_settings = [
    Setting('command', interpret_shlex_sequence),
    Setting('cwd', interpret_8bit_string, default=None),
    Setting('environ',
            interpret_map_of(interpret_8bit_string, interpret_8bit_string),
            default=None),
    Setting('is_reliable_scorer', interpret_bool, default=True),
    Setting('allow_claim', interpret_bool, default=False),
    Setting('gtp_translations',
            interpret_map_of(interpret_8bit_string, interpret_8bit_string),
            default=dict),
    Setting('startup_gtp_commands', interpret_sequence, default=list),
    Setting('discard_stderr', interpret_bool, default=False),
    ]

class Competition(object):
    """A resumable processing job based around playing many GTP games.

    This is an abstract base class.

    """

    def __init__(self, competition_code):
        self.competition_code = competition_code
        self.base_directory = None
        self.event_logger = log_discard
        self.history_logger = log_discard

    def control_file_globals(self):
        """Specify names and values to make available to the control file.

        Returns a dict suitable for use as the control file's namespace.

        """
        return {
            'Player' : Player_config,
            }

    def set_base_directory(self, pathname):
        """Set the competition's base directory.

        Relative paths in the control file are interpreted relative to this
        directory.

        """
        self.base_directory = pathname

    def resolve_pathname(self, pathname):
        """Resolve a pathname relative to the competition's base directory.

        Accepts None, returning it.

        Applies os.expanduser to the pathname.

        Doesn't absolutise or normalise the resulting pathname.

        Raises ValueError if it can't handle the pathname.

        """
        if pathname is None:
            return None
        if pathname == "":
            raise ValueError("empty pathname")
        try:
            pathname = os.path.expanduser(pathname)
        except Exception:
            raise ValueError("bad pathname")
        try:
            return os.path.join(self.base_directory, pathname)
        except Exception:
            raise ValueError(
                "relative path supplied but base directory isn't set")

    def set_event_logger(self, logger):
        """Set a callback for the event log.

        logger -- function taking a string argument

        Until this is called, event log output is silently discarded.

        """
        self.event_logger = logger

    def set_history_logger(self, logger):
        """Set a callback for the history file.

        logger -- function taking a string argument

        Until this is called, event log output is silently discarded.

        """
        self.history_logger = logger

    def log_event(self, s):
        """Write a message to the event log.

        The event log logs all game starts and finishes; competitions can add
        lines to mark things like the start of new generations.

        A newline is added to the message.

        """
        self.event_logger(s)

    def log_history(self, s):
        """Write a message to the history file.

        The history file is used to show things like game results and tuning
        event intermediate status.

        A newline is added to the message.

        """
        self.history_logger(s)

    # List of Settings, for overriding in subclasses.
    global_settings = []

    def initialise_from_control_file(self, config):
        """Initialise competition data from the control file.

        config -- namespace produced by the control file.

        (When resuming from saved state, this is called before set_state()).

        This processes all global_settings and sets attributes (named by the
        setting names).

        It also handles the following settings and sets the corresponding
        attributes:
          players -- map player code -> game_jobs.Player

        Raises ControlFileError with a description if the control file has a bad
        or missing value.

        """
        # This is called for all commands, so it mustn't log anything.

        # Implementations in subclasses should have their own backstop exception
        # handlers, so they can at least show what part of the control file was
        # being interpreted when the exception occurred.

        # We should accept that there may be unexpected exceptions, because
        # control files are allowed to do things like substitute list-like
        # objects for Python lists.

        try:
            to_set = load_settings(self.global_settings, config)
        except ValueError, e:
            raise ControlFileError(str(e))
        for name, value in to_set.items():
            setattr(self, name, value)

        def interpret_pc(v):
            if not isinstance(v, Player_config):
                raise ValueError("not a Player")
            return v
        settings = [
            Setting('players',
                    interpret_map_of(interpret_identifier, interpret_pc))
            ]
        try:
            specials = load_settings(settings, config)
        except ValueError, e:
            raise ControlFileError(str(e))
        self.players = {}
        for player_code, player_config in specials['players']:
            try:
                player = self.game_jobs_player_from_config(
                    player_code, player_config)
            except Exception, e:
                raise ControlFileError("player %s: %s" % (player_code, e))
            self.players[player_code] = player

    def game_jobs_player_from_config(self, code, player_config):
        """Make a game_jobs.Player from a Player_config.

        Raises ControlFileError with a description if there is an error in the
        configuration.

        Returns an incomplete game_jobs.Player (see get_game() for details).

        """
        if len(player_config.args) > 1:
            raise ControlFileError("too many arguments")
        if player_config.args:
            if 'command' in player_config.kwargs:
                raise ControlFileError(
                    "command specified both implicitly and explicitly")
            player_config.kwargs['command'] = player_config.args[0]

        config = load_settings(_player_settings, player_config.kwargs,
                               strict=True)

        player = game_jobs.Player()
        player.code = code

        try:
            player.cmd_args = config['command']
            player.cmd_args[0] = os.path.expanduser(player.cmd_args[0])
        except Exception, e:
            raise ControlFileError("'command': %s" % e)

        try:
            player.cwd = self.resolve_pathname(config['cwd'])
        except Exception, e:
            raise ControlFileError("'cwd': %s" % e)
        player.environ = config['environ']

        player.is_reliable_scorer = config['is_reliable_scorer']
        player.allow_claim = config['allow_claim']

        player.startup_gtp_commands = []
        try:
            for v in config['startup_gtp_commands']:
                try:
                    if isinstance(v, basestring):
                        words = interpret_8bit_string(v).split()
                    else:
                        words = list(v)
                    if not all(gtp_controller.is_well_formed_gtp_word(word)
                               for word in words):
                        raise StandardError
                except Exception:
                    raise ValueError("invalid command %s" % v)
                player.startup_gtp_commands.append((words[0], words[1:]))
        except ValueError, e:
            raise ControlFileError("'startup_gtp_commands': %s" % e)

        player.gtp_translations = {}
        try:
            for cmd1, cmd2 in config['gtp_translations']:
                if not gtp_controller.is_well_formed_gtp_word(cmd1):
                    raise ValueError("invalid command %s" % clean_string(cmd1))
                if not gtp_controller.is_well_formed_gtp_word(cmd2):
                    raise ValueError("invalid command %s" % clean_string(cmd2))
                player.gtp_translations[cmd1] = cmd2
        except ValueError, e:
            raise ControlFileError("'gtp_translations': %s" % e)

        player.discard_stderr = config['discard_stderr']

        return player


    def set_clean_status(self):
        """Reset competition state to its initial value."""
        # This is called before logging is set up, so it mustn't log anything.
        raise NotImplementedError

    def get_status(self):
        """Return full state of the competition, so it can be resumed later.

        The returned result must be pickleable.

        """
        raise NotImplementedError

    def set_status(self, status):
        """Reset competition state to a previously reported value.

        'status' will be a value previously reported by get_status().

        """
        # This is called for the 'show' command, so it mustn't log anything.
        raise NotImplementedError

    def get_player_checks(self):
        """List the Player_checks for check_players() to check.

        Returns a list of game_jobs.Player_check objects. The players'
        stderr_pathname attribute will be ignored.

        This is called without the competition status being set.

        """
        raise NotImplementedError

    def get_game(self):
        """Return the details of the next game to play.

        Returns a game_jobs.Game_job, or NoGameAvailable.

        The Game_job is incomplete in the following ways (which are left to the
        ringmaster to finish off):
         - sgf_filename, sgf_dirname and void_sgf_dirname aren't set
         - gtp_log_pathname isn't set
         - the Players' stderr_pathname isn't set; instead they have a
           discard_stderr boolean attribute

        """
        raise NotImplementedError

    def process_game_result(self, response):
        """Process the results from a completed game.

        response -- game_jobs.Game_job_result

        This may return a text description of the game result, to override the
        default (it should normally include response.game_result.sgf_result).

        It's common for this method to write to the history file.

        """
        raise NotImplementedError

    def process_game_error(self, job, previous_error_count):
        """Process a report that a job failed.

        job                  -- game_jobs.Game_job
        previous_error_count -- int >= 0

        Returns a pair of bools (stop_competition, retry_game)

        If stop_competition is True, the ringmaster will stop starting new
        games. Otherwise, if retry_game is true the ringmaster will try running
        the same game again.

        The job is one previously returned by get_game(). previous_error_count
        is the number of times that this particular job has failed before.

        Failed jobs are ones in which there was an error more serious than one
        which just causes an engine to forfeit the game. For example, the job
        will fail if one of the engines fails to respond to GTP commands at all,
        or (in particular) if it exits as soon as it's invoked because it
        doesn't like its command-line options.

        """
        raise NotImplementedError

    def write_screen_report(self, out):
        """Write a one-screen summary of current competition status.

        out -- writeable file-like object

        This is supposed to fit comfortably on one screen; it's normally
        displayed continuously by the ringmaster. Aim for about 30 lines.

        It should end with a newline, but not have additional blank lines at
        the end.

        This should focus on describing incomplete competitions usefully.

        """
        raise NotImplementedError

    def write_short_report(self, out):
        """Write a short report of the competition status/results.

        out -- writeable file-like object

        This is used for the ringmaster's 'show' command.

        It should end with a newline, but not have additional blank lines at
        the end.

        This should be useful for both completed and incomplete competitions.

        """
        raise NotImplementedError

    def write_full_report(self, out):
        """Write a detailed report of competition status/results.

        out -- writeable file-like object

        This is used for the ringmaster's 'report' command.

        It should end with a newline.

        This should focus on describing completed competitions well.

        """
        raise NotImplementedError


## Helper functions for settings

def interpret_board_size(i):
    i = interpret_int(i)
    if i < 2:
        raise ValueError("too small")
    if i > 25:
        raise ValueError("too large")
    return i

def validate_handicap(handicap, handicap_style, board_size):
    """Check whether a handicap is allowed.

    handicap       -- int or None
    handicap_style -- 'free' or 'fixed'
    board_size     -- int

    Raises ControlFileError with a description if it isn't.

    """
    if handicap is None:
        return True
    if handicap < 2:
        raise ControlFileError("handicap too small")
    if handicap_style == 'fixed':
        limit = handicap_layout.max_fixed_handicap_for_board_size(board_size)
    else:
        limit = handicap_layout.max_free_handicap_for_board_size(board_size)
    if handicap > limit:
        raise ControlFileError(
            "%s handicap out of range for board size %d" %
            (handicap_style, board_size))

