import logging
import os

import yaml
import builtins
from termcolor import colored


# TODO: Need to fix somehow -- omnigibson gets imported first BEFORE we can actually modify the macros
from omnigibson.macros import gm

# Create logger
logging.basicConfig(format='[%(levelname)s] [%(name)s] %(message)s')
log = logging.getLogger(__name__)

builtins.ISAAC_LAUNCHED_FROM_JUPYTER = (
    os.getenv("ISAAC_JUPYTER_KERNEL") is not None
)  # We set this in the kernel.json file

# Always enable nest_asyncio because MaterialPrim calls asyncio.run()
import nest_asyncio
nest_asyncio.apply()

__version__ = "0.0.5"

log.setLevel(logging.DEBUG if gm.DEBUG else logging.INFO)

# can override assets_path and dataset_path from environment variable
if "OMNIGIBSON_ASSET_PATH" in os.environ:
    gm.ASSET_PATH = os.environ["OMNIGIBSON_ASSET_PATH"]
gm.ASSET_PATH = os.path.expanduser(gm.ASSET_PATH)
if not os.path.isabs(gm.ASSET_PATH):
    gm.ASSET_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), gm.ASSET_PATH)

if "OMNIGIBSON_DATASET_PATH" in os.environ:
    gm.DATASET_PATH = os.environ["OMNIGIBSON_DATASET_PATH"]
gm.DATASET_PATH = os.path.expanduser(gm.DATASET_PATH)
if not os.path.isabs(gm.DATASET_PATH):
    gm.DATASET_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), gm.DATASET_PATH)

if "OMNIGIBSON_KEY_PATH" in os.environ:
    gm.KEY_PATH = os.environ["OMNIGIBSON_KEY_PATH"]
gm.KEY_PATH = os.path.expanduser(gm.KEY_PATH)
if not os.path.isabs(gm.KEY_PATH):
    gm.KEY_PATH = os.path.join(os.path.dirname(os.path.realpath(__file__)), gm.KEY_PATH)

root_path = os.path.dirname(os.path.realpath(__file__))

# Store paths to example configs
example_config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "configs")

# Initialize global variables
app = None  # (this is a singleton so it's okay that it's global)
sim = None  # (this is a singleton so it's okay that it's global)
Environment = None
REGISTERED_SCENES = None
REGISTERED_OBJECTS = None
REGISTERED_ROBOTS = None
REGISTERED_CONTROLLERS = None
REGISTERED_TASKS = None
ALL_SENSOR_MODALITIES = None


# Helper functions for starting omnigibson
def print_save_usd_warning(_):
    log.warning("Exporting individual USDs has been disabled in OG due to copyrights.")


def create_app():
    global app
    from omni.isaac.kit import SimulationApp
    app = SimulationApp({"headless": gm.HEADLESS})
    import omni

    # Possibly hide windows if in debug mode
    if gm.GUI_VIEWPORT_ONLY:
        hide_window_names = ["Console", "Main ToolBar", "Stage", "Layer", "Property", "Render Settings", "Content",
                             "Flow", "Semantics Schema Editor"]
        for name in hide_window_names:
            window = omni.ui.Workspace.get_window(name)
            if window is not None:
                window.visible = False
                app.update()

    omni.kit.widget.stage.context_menu.ContextMenu.save_prim = print_save_usd_warning

    return app


def create_sim():
    global sim
    from omnigibson.simulator import Simulator
    sim = Simulator()
    return sim


def print_logo():
    raw_texts = [
        ("       ___                  _", "  ____ _ _                     "),
        ("      / _ \ _ __ ___  _ __ (_)", "/ ___(_) |__  ___  ___  _ __  "),
        ("     | | | | '_ ` _ \| '_ \| |", " |  _| | '_ \/ __|/ _ \| '_ \ "),
        ("     | |_| | | | | | | | | | |", " |_| | | |_) \__ \ (_) | | | |"),
        ("      \___/|_| |_| |_|_| |_|_|", "\____|_|_.__/|___/\___/|_| |_|"),
    ]

    print()
    for (red_text, grey_text) in raw_texts:
        red_text = colored(red_text, "light_red", attrs=["bold"])
        grey_text = colored(grey_text, "light_grey", attrs=["bold", "dark"])
        print(red_text + grey_text)

    print()


def logo_small():
    red_text = colored("Omni", "light_red", attrs=["bold"])
    grey_text = colored("Gibson", "light_grey", attrs=["bold", "dark"])
    return red_text + grey_text


def start():
    global app, sim, Environment, REGISTERED_SCENES, REGISTERED_OBJECTS, REGISTERED_ROBOTS, REGISTERED_CONTROLLERS, \
        REGISTERED_TASKS, ALL_SENSOR_MODALITIES

    log.info(f"{'-' * 10} Starting {logo_small()} {'-' * 10}")

    # First create the app, then create the sim
    app = create_app()
    sim = create_sim()

    print_logo()
    log.info(f"{'-' * 10} Welcome to {logo_small()}! {'-' * 10}")

    # Import any remaining items we want to access directly from the main omnigibson import
    from omnigibson.envs import Environment
    from omnigibson.scenes import REGISTERED_SCENES
    from omnigibson.objects import REGISTERED_OBJECTS
    from omnigibson.robots import REGISTERED_ROBOTS
    from omnigibson.controllers import REGISTERED_CONTROLLERS
    from omnigibson.tasks import REGISTERED_TASKS
    from omnigibson.sensors import ALL_SENSOR_MODALITIES
    return app, sim, Environment, REGISTERED_SCENES, REGISTERED_OBJECTS, REGISTERED_ROBOTS, REGISTERED_CONTROLLERS, \
        REGISTERED_TASKS, ALL_SENSOR_MODALITIES


# Automatically start omnigibson's omniverse backend unless explicitly told not to
if not (os.getenv("OMNIGIBSON_NO_OMNIVERSE", 'False').lower() in {'true', '1', 't'}):
    app, sim, Environment, REGISTERED_SCENES, REGISTERED_OBJECTS, REGISTERED_ROBOTS, REGISTERED_CONTROLLERS, \
        REGISTERED_TASKS, ALL_SENSOR_MODALITIES = start()


def shutdown():
    global app
    from omnigibson.utils.ui_utils import suppress_omni_log
    log.info(f"{'-' * 10} Shutting Down {logo_small()} {'-' * 10}")

    # Suppress carb warning here that we have no control over -- it's expected
    with suppress_omni_log(channels=["carb"]):
        app.close()

    exit(0)
