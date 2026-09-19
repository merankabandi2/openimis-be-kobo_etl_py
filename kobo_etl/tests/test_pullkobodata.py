import argparse
import ast
import inspect
import textwrap

from django.test import TestCase

from kobo_etl.management.commands.pullkobodata import Command


def _dispatcher_scope_keys():
    """Extract the match/case literal keys handled by Command.sync_kobo, except the wildcard."""
    source = textwrap.dedent(inspect.getsource(Command.sync_kobo))
    tree = ast.parse(source)
    return {
        node.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.MatchValue) and isinstance(node.value, ast.Constant)
    }


def _scope_choices():
    parser = argparse.ArgumentParser()
    Command().add_arguments(parser)
    for action in parser._actions:
        if action.dest == "scope":
            return set(action.choices)
    raise AssertionError("no 'scope' argument registered")


class PullKoboDataChoicesTest(TestCase):
    def test_choices_include_every_dispatcher_key(self):
        dispatcher_keys = _dispatcher_scope_keys()
        choices = _scope_choices()

        self.assertTrue(dispatcher_keys, "expected to find case labels in sync_kobo")
        self.assertTrue(
            dispatcher_keys.issubset(choices),
            f"argparse choices {choices} are missing dispatcher keys {dispatcher_keys - choices}",
        )
