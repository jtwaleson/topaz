#!/usr/bin/env python

import os
import sys


if __name__ == "__main__":
    os.execv(sys.executable, [sys.executable] + ["-m", "rupypy"] + sys.argv[1:])
