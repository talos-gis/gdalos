
def talos_module_init():
    from talosgis import talos_utils
    try:
        talos_utils.talos_init()
    except ImportError:
        raise Exception('failed to load talos backend')

radio_enabled = None


def talos_radio_init():
    global radio_enabled
    if radio_enabled is None:
        from talosgis import talos, talos_utils, get_talos_radio_path
        if not hasattr(talos, 'GS_SetRadioParameters'):
            raise Exception('This version does not support radio')
        if hasattr(talos, 'GS_SetRadioPath'):
            try:
                radio_path = get_talos_radio_path()
                talos.GS_SetRadioPath(radio_path)
                radio_enabled = True
            except:
                radio_enabled = False
        else:
            radio_enabled = True

    if not radio_enabled:
        raise Exception('No radio modules found')
