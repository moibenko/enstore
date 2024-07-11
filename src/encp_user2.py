#!/usr/bin/env python
###############################################################################
# src/$RCSfile$   $Revision$
#
import os

import encp
import delete_at_exit


if __name__ == "__main__":   # pragma: no cover
    use_profiler = os.getenv('USE_PROFILER')
    if use_profiler:
        import cProfile
        from pstats import SortKey, Stats
        with cProfile.Profile() as profile:
            exit_code = encp.start(2)  # 2 means dcache
            (
                Stats(profile)
                .strip_dirs()
                .sort_stats(SortKey.CALLS)
                .print_stats()
            )
        os._exit(exit_code)
    else:
        delete_at_exit.quit(encp.start(2))  # 2 means dcahce
