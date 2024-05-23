import builtins
import logging
import os
import shutil
import signal
import tempfile

from omnigibson.controllers import REGISTERED_CONTROLLERS
from omnigibson.envs import Environment, VectorEnvironment
from omnigibson.macros import gm
from omnigibson.objects import REGISTERED_OBJECTS
from omnigibson.robots import REGISTERED_ROBOTS
from omnigibson.scenes import REGISTERED_SCENES
from omnigibson.sensors import ALL_SENSOR_MODALITIES
from omnigibson.simulator import launch_simulator as launch
from omnigibson.tasks import REGISTERED_TASKS

# Create logger
logging.basicConfig(format="[%(levelname)s] [%(name)s] %(message)s")
log = logging.getLogger(__name__)

builtins.ISAAC_LAUNCHED_FROM_JUPYTER = (
    os.getenv("ISAAC_JUPYTER_KERNEL") is not None
)  # We set this in the kernel.json file

# Always enable nest_asyncio because MaterialPrim calls asyncio.run()
import nest_asyncio

nest_asyncio.apply()

__version__ = "1.0.0"

root_path = os.path.dirname(os.path.realpath(__file__))

# Store paths to example configs
example_config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "configs")

# Initialize global variables
app = None  # (this is a singleton so it's okay that it's global)
sim = None  # (this is a singleton so it's okay that it's global)


# Create and expose a temporary directory for any use cases. It will get destroyed upon omni
# shutdown by the shutdown function.
tempdir = tempfile.mkdtemp()


def clear():
    """
    Clear the stage and then call launch_simulator again to make og.sim point to a new simulator instance
    """
    global sim

    import omnigibson.lazy as lazy
    from omnigibson.object_states.update_state_mixin import GlobalUpdateStateMixin
    from omnigibson.prims.material_prim import MaterialPrim
    from omnigibson.sensors.vision_sensor import VisionSensor
    from omnigibson.transition_rules import TransitionRuleAPI
    from omnigibson.utils.python_utils import clear as clear_python_utils
    from omnigibson.utils.usd_utils import clear as clear_usd_utils

    # Stop the physics
    sim.stop()

    # Clear all scenes
    for scene in sim.scenes:
        scene.clear()

    # Remove the skybox, floor plane and viewer camera
    if sim._skybox is not None:
        sim._skybox.remove()

    if sim._floor_plane is not None:
        sim._floor_plane.remove()

    if sim._viewer_camera is not None:
        sim._viewer_camera.remove()

    if sim._camera_mover is not None:
        sim._camera_mover.clear()

    # Clear the vision sensor cache
    VisionSensor.clear()

    # Clear all global update states
    for state in sim.object_state_types_requiring_update:
        if issubclass(state, GlobalUpdateStateMixin):
            state.global_initialize()

    # Clear all materials
    MaterialPrim.clear()

    if gm.ENABLE_TRANSITION_RULES:
        # Clear all transition rules
        TransitionRuleAPI.clear()

    # Clear uniquely named items and other internal states
    clear_python_utils()
    clear_usd_utils()

    assert lazy.omni.isaac.core.utils.stage.close_stage()
    sim = None
    lazy.omni.isaac.core.simulation_context.SimulationContext.clear_instance()
    launch()


def cleanup(*args, **kwargs):
    # TODO: Currently tempfile removal will fail due to CopyPrim command (for example, GranularSystem in dicing_apple example.)
    try:
        shutil.rmtree(tempdir)
    except PermissionError:
        log.info("Permission error when removing temp files. Ignoring")
    from omnigibson.simulator import logo_small

    log.info(f"{'-' * 10} Shutting Down {logo_small()} {'-' * 10}")


def shutdown(due_to_signal=False):
    if app is not None:
        # If Isaac is running, we do the cleanup in its shutdown callback to avoid open handles.
        # TODO: Automated cleanup in callback doesn't work for some reason. Need to investigate.
        # Manually call cleanup for now.
        cleanup()
        app.close()
    else:
        # Otherwise, we do the cleanup here.
        cleanup()

        # If we're not shutting down due to a signal, we need to manually exit
        if not due_to_signal:
            exit(0)


def shutdown_handler(*args, **kwargs):
    shutdown(due_to_signal=True)
    return signal.default_int_handler(*args, **kwargs)


# Something somewhere disables the default SIGINT handler, so we need to re-enable it
signal.signal(signal.SIGINT, shutdown_handler)
