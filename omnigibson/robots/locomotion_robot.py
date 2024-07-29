from abc import abstractmethod

import numpy as np
from omnigibson.utils.transform_utils import euler2quat, quat2mat, quat_multiply

from omnigibson.controllers import LocomotionController
from omnigibson.robots.robot_base import BaseRobot
from omnigibson.utils.python_utils import classproperty
from omnigibson.utils.usd_utils import ControllableObjectViewAPI


class LocomotionRobot(BaseRobot):
    """
    Robot that is is equipped with locomotive (navigational) capabilities.
    Provides common interface for a wide variety of robots.

    NOTE: controller_config should, at the minimum, contain:
        base: controller specifications for the controller to control this robot's base (locomotion).
            Should include:

            - name: Controller to create
            - <other kwargs> relevant to the controller being created. Note that all values will have default
                values specified, but setting these individual kwargs will override them

    """

    def _validate_configuration(self):
        # We make sure that our base controller exists and is a locomotion controller
        assert (
            "base" in self._controllers
        ), "Controller 'base' must exist in controllers! Current controllers: {}".format(list(self._controllers.keys()))
        assert isinstance(
            self._controllers["base"], LocomotionController
        ), "Base controller must be a LocomotionController!"

        # run super
        super()._validate_configuration()

    def _get_proprioception_dict(self):
        dic = super()._get_proprioception_dict()

        joint_positions = ControllableObjectViewAPI.get_joint_positions(self.articulation_root_path)
        joint_velocities = ControllableObjectViewAPI.get_joint_velocities(self.articulation_root_path)

        # Add base info
        dic["base_qpos"] = joint_positions[self.base_control_idx]
        dic["base_qpos_sin"] = np.sin(joint_positions[self.base_control_idx])
        dic["base_qpos_cos"] = np.cos(joint_positions[self.base_control_idx])
        dic["base_qvel"] = joint_velocities[self.base_control_idx]

        return dic

    @property
    def default_proprio_obs(self):
        obs_keys = super().default_proprio_obs
        return obs_keys + ["base_qpos_sin", "base_qpos_cos", "robot_lin_vel", "robot_ang_vel"]

    @property
    def controller_order(self):
        # By default, only base is supported
        return ["base"]

    @property
    def _default_controllers(self):
        # Always call super first
        controllers = super()._default_controllers

        # For best generalizability use, joint controller as default
        controllers["base"] = "JointController"

        return controllers

    @property
    def _default_base_joint_controller_config(self):
        """
        Returns:
            dict: Default base joint controller config to control this robot's base. Uses velocity
                control by default.
        """
        return {
            "name": "JointController",
            "control_freq": self._control_freq,
            "motor_type": "velocity",
            "control_limits": self.control_limits,
            "dof_idx": self.base_control_idx,
            "command_output_limits": "default",
            "use_delta_commands": False,
        }

    @property
    def _default_base_null_joint_controller_config(self):
        """
        Returns:
            dict: Default null joint controller config to control this robot's base i.e. dummy controller
        """
        return {
            "name": "NullJointController",
            "control_freq": self._control_freq,
            "motor_type": "velocity",
            "control_limits": self.control_limits,
            "dof_idx": self.base_control_idx,
            "default_command": np.zeros(len(self.base_control_idx)),
            "use_impedances": False,
        }

    @property
    def _default_controller_config(self):
        # Always run super method first
        cfg = super()._default_controller_config

        # Add supported base controllers
        cfg["base"] = {
            self._default_base_joint_controller_config["name"]: self._default_base_joint_controller_config,
            self._default_base_null_joint_controller_config["name"]: self._default_base_null_joint_controller_config,
        }

        return cfg

    def move_by(self, delta):
        """
        Move robot base without physics simulation

        Args:
            delta (float):float], (x,y,z) cartesian delta base position
        """
        new_pos = np.array(delta) + self.get_position()
        self.set_position(position=new_pos)

    def move_forward(self, delta=0.05):
        """
        Move robot base forward without physics simulation

        Args:
            delta (float): delta base position forward
        """
        self.move_by(quat2mat(self.get_orientation()).dot(np.array([delta, 0, 0])))

    def move_backward(self, delta=0.05):
        """
        Move robot base backward without physics simulation

        Args:
            delta (float): delta base position backward
        """
        self.move_by(quat2mat(self.get_orientation()).dot(np.array([-delta, 0, 0])))

    def move_left(self, delta=0.05):
        """
        Move robot base left without physics simulation

        Args:
            delta (float): delta base position left
        """
        self.move_by(quat2mat(self.get_orientation()).dot(np.array([0, -delta, 0])))

    def move_right(self, delta=0.05):
        """
        Move robot base right without physics simulation

        Args:
            delta (float): delta base position right
        """
        self.move_by(quat2mat(self.get_orientation()).dot(np.array([0, delta, 0])))

    def turn_left(self, delta=0.03):
        """
        Rotate robot base left without physics simulation

        Args:
            delta (float): delta angle to rotate the base left
        """
        quat = self.get_orientation()
        quat = quat_multiply((euler2quat(-delta, 0, 0)), quat)
        self.set_orientation(quat)

    def turn_right(self, delta=0.03):
        """
        Rotate robot base right without physics simulation

        Args:
            delta (float): angle to rotate the base right
        """
        quat = self.get_orientation()
        quat = quat_multiply((euler2quat(delta, 0, 0)), quat)
        self.set_orientation(quat)

    @property
    def base_action_idx(self):
        controller_idx = self.controller_order.index("base")
        action_start_idx = sum([self.controllers[self.controller_order[i]].command_dim for i in range(controller_idx)])
        return np.arange(action_start_idx, action_start_idx + self.controllers["base"].command_dim)

    @property
    @abstractmethod
    def base_joint_names(self):
        """
        Returns:
            list: Array of joint names corresponding to this robot's base joints (e.g.: wheels).

                Note: the ordering within the list is assumed to be intentional, and is
                directly used to define the set of corresponding control idxs.
        """
        raise NotImplementedError

    @property
    def base_control_idx(self):
        """
        Returns:
            n-array: Indices in low-level control vector corresponding to base joints.
        """
        return np.array([list(self.joints.keys()).index(name) for name in self.base_joint_names])

    @classproperty
    def _do_not_register_classes(cls):
        # Don't register this class since it's an abstract template
        classes = super()._do_not_register_classes
        classes.add("LocomotionRobot")
        return classes
