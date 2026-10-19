def classFactory(iface):
    from .plugin import StageOnePlugin
    return StageOnePlugin(iface)
