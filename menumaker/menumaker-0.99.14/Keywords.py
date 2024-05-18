"""Module to handle keywords and sets of keywords"""

import types
import itertools


class Keyword(str):

    """Keyword is a case insensitive string with the spaces omitted,
        that is Keyword(Foo Bar) == Keyword(foobar)"""

    def __init__(self, s):
        t = ""
        if not s is None:
            for x in s.split():
                # FIXME : speed up the hashing by xor'ing the parts on which self is split
                # instead of performing this string concatenation
                t += x
        self.hash = hash(t.lower())
        str.__init__(self)

    def __hash__(self):
        return self.hash

    def __eq__(self, other):
        if not isinstance(other, Keyword):
            other = Keyword(other)
        # Use direct hash comparison to save a call to self.__hash__()
        return self.hash == other.hash


class Set(set):

    """Mutable set of keywords. Besides keywords, it can operate on ordinary strings as well,
        which get implicitly converted into the Keyword instances"""

    def __init__(self, *args):
        xargs = []
        for x in args:
            if isinstance(x, Keyword):
                xargs.append(x)
            else:
                xargs.append(Keyword(x))

        set.__init__(self, xargs)

    def __contains__(self, x):
        if isinstance(x, Keyword):
            return set.__contains__(self, x)
        else:
            return set.__contains__(self, Keyword(x))
