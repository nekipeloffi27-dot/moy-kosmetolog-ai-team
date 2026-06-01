"""Importing this package wires all agents into the orchestrator dispatch table."""
from agents.pm          import runner as _pm             # noqa: F401
from agents.designer    import runner as _designer       # noqa: F401
from agents.cto_tasking import runner as _cto_tasking    # noqa: F401
from agents.dev         import runner as _dev            # noqa: F401
from agents.cto_review  import runner as _cto_review     # noqa: F401  (M6)
from agents.cto_deploy  import runner as _cto_deploy     # noqa: F401  (M6)
