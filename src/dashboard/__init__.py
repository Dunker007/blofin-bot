# Dashboard modules
from .terminal import TerminalDashboard

# Web module loaded on demand to avoid FastAPI import if not using web
def create_web_app(config, client):
    from .web import create_full_app
    return create_full_app(config, client)

__all__ = ["TerminalDashboard", "create_web_app"]
