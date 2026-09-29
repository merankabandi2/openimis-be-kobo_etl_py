import argparse

from django.test import TestCase

from kobo_etl.management.commands.pullkobodata import Command
from kobo_etl.services.KoboServices import SCOPE_SYNCS


def _scope_choices():
    parser = argparse.ArgumentParser()
    Command().add_arguments(parser)
    for action in parser._actions:
        if action.dest == "scope":
            return set(action.choices)
    raise AssertionError("no 'scope' argument registered")


class PullKoboDataChoicesTest(TestCase):
    def test_choices_are_all_and_every_sync_scope(self):
        self.assertEqual(_scope_choices(), {"all", *SCOPE_SYNCS})
