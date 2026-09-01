"""ระบบปลั๊กอินภายนอกที่ค้นพบเครื่องมือจาก manifest ที่ commit ไว้ใน repository"""

from app.plugins.loader import LoadedPlugin, PluginError, load_plugins
from app.plugins.manifest import PluginManifest, PluginOperation

__all__ = [
    "LoadedPlugin",
    "PluginError",
    "PluginManifest",
    "PluginOperation",
    "load_plugins",
]
