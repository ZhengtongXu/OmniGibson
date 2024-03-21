import numpy as np

from omnigibson.macros import create_module_macros
from omnigibson.controllers import IsGraspingState, ControlType, GripperController
from omnigibson.utils.python_utils import assert_valid_key
import omnigibson.utils.transform_utils as T

VALID_MODES = {
    "binary",
    "ternary",
    "smooth",
    "smooth_delta"
    "independent",
}


# Create settings for this module
m = create_module_macros(module_path=__file__)

# is_grasping heuristics parameters
m.POS_TOLERANCE = 0.002  # arbitrary heuristic
m.VEL_TOLERANCE = 0.01  # arbitrary heuristic


class MultiFingerGripperController(GripperController):
    """
    Controller class for multi finger gripper control. This either interprets an input as a binary
    command (open / close), continuous command (open / close with scaled velocities), or per-joint continuous command

    Each controller step consists of the following:
        1. Clip + Scale inputted command according to @command_input_limits and @command_output_limits
        2a. Convert command into gripper joint control signals
        2b. Clips the resulting control by the motor limits
    """

    def __init__(
        self,
        control_freq,
        motor_type,
        control_limits,
        dof_idx,
        command_input_limits="default",
        command_output_limits="default",
        inverted=False,
        mode="binary",
        open_qpos=None,
        closed_qpos=None,
        limit_tolerance=0.001,
    ):
        """
        Args:
            control_freq (int): controller loop frequency
            motor_type (str): type of motor being controlled, one of {position, velocity, effort}
            control_limits (Dict[str, Tuple[Array[float], Array[float]]]): The min/max limits to the outputted
                control signal. Should specify per-dof type limits, i.e.:

                "position": [[min], [max]]
                "velocity": [[min], [max]]
                "effort": [[min], [max]]
                "has_limit": [...bool...]

                Values outside of this range will be clipped, if the corresponding joint index in has_limit is True.
            dof_idx (Array[int]): specific dof indices controlled by this robot. Used for inferring
                controller-relevant values during control computations
            command_input_limits (None or "default" or Tuple[float, float] or Tuple[Array[float], Array[float]]):
                if set, is the min/max acceptable inputted command. Values outside this range will be clipped.
                If None, no clipping will be used. If "default", range will be set to (-1, 1)
            command_output_limits (None or "default" or Tuple[float, float] or Tuple[Array[float], Array[float]]):
                if set, is the min/max scaled command. If both this value and @command_input_limits is not None,
                then all inputted command values will be scaled from the input range to the output range.
                If either is None, no scaling will be used. If "default", then this range will automatically be set
                to the @control_limits entry corresponding to self.control_type
            inverted (bool): whether or not the command direction (grasp is negative) and the control direction are
                inverted, e.g. to grasp you need to move the joint in the positive direction.
            mode (str): mode for this controller. Valid options are:

                "binary": 1D command, if preprocessed value > 0 is interpreted as an max open
                    (send max pos / vel / tor signal), otherwise send max close control signals
                "ternary": 1D command, if preprocessed value > 0.33 is interpreted as an max open
                    (send max pos / vel / tor signal), < 0.33 as max close control, and otherwise stay
                    still
                "smooth": 1D command, sends symmetric signal to both finger joints equal to the preprocessed commands
                "smooth_delta": 1D command, sends symmetric signal to both finger joints equal to the preprocessed commands
                    adding the command on top of the existing value
                "independent": 2D command, sends independent signals to each finger joint equal to the preprocessed command

            open_qpos (None or Array[float]): If specified, the joint positions representing a fully-opened gripper.
                This is to allow representing the open state as a partially opened gripper, rather than the full
                opened gripper. If None, will simply use the native joint limits of the gripper joints. Only relevant
                if using @mode=binary and @motor_type=position
            closed_qpos (None or Array[float]): If specified, the joint positions representing a fully-closed gripper.
                This is to allow representing the closed state as a partially closed gripper, rather than the full
                closed gripper. If None, will simply use the native joint limits of the gripper joints. Only relevant
                if using @mode=binary and @motor_type=position
            limit_tolerance (float): sets the tolerance from the joint limit ends, below which controls will be zeroed
                out if the control is using velocity or torque control
        """
        # Store arguments
        assert_valid_key(key=motor_type.lower(), valid_keys=ControlType.VALID_TYPES_STR, name="motor_type")
        self._motor_type = motor_type.lower()
        assert_valid_key(key=mode, valid_keys=VALID_MODES, name="mode for multi finger gripper")
        self._inverted = inverted
        self._mode = mode
        self._limit_tolerance = limit_tolerance
        self._open_qpos = open_qpos if open_qpos is None else np.array(open_qpos)
        self._closed_qpos = closed_qpos if closed_qpos is None else np.array(closed_qpos)

        # Create other args to be filled in at runtime
        self._is_grasping = IsGraspingState.FALSE

        # If we're using binary signal, we override the command output limits
        if mode == "binary" or mode == "ternary":
            command_output_limits = (-1.0, 1.0)

        # When in delta mode, it doesn't make sense to infer output range using the joint limits (since that's an
        # absolute range and our values are relative). So reject the default mode option in that case.
        assert not (
            mode == "smooth_delta" and command_output_limits == "default"
        ), "Cannot use 'default' command output limits in delta commands mode of JointController. Try None instead."


        # Run super init
        super().__init__(
            control_freq=control_freq,
            control_limits=control_limits,
            dof_idx=dof_idx,
            command_input_limits=command_input_limits,
            command_output_limits=command_output_limits,
        )

    def reset(self):
        # Call super first
        super().reset()

        # reset grasping state
        self._is_grasping = IsGraspingState.FALSE

    def _preprocess_command(self, command):
        # We extend this method to make sure command is always 2D
        if self._mode != "independent":
            command = (
                np.array([command] * self.command_dim)
                if type(command) in {int, float}
                else np.array([command[0]] * self.command_dim)
            )

        # Flip the command if the direction is inverted.
        if self._inverted:
            command = self._command_input_limits[1] - (command - self._command_input_limits[0])

        # Return from super method
        return super()._preprocess_command(command=command)

    def _update_goal(self, command, control_dict):
        # Directly store command as the goal
        return dict(target=command)

    def compute_control(self, goal_dict, control_dict):
        """
        Converts the (already preprocessed) inputted @command into deployable (non-clipped!) gripper
        joint control signal

        Args:
            goal_dict (Dict[str, Any]): dictionary that should include any relevant keyword-mapped
                goals necessary for controller computation. Must include the following keys:
                    target: desired gripper target
            control_dict (Dict[str, Any]): dictionary that should include any relevant keyword-mapped
                states necessary for controller computation. Must include the following keys:
                    joint_position: Array of current joint positions
                    joint_velocity: Array of current joint velocities

        Returns:
            Array[float]: outputted (non-clipped!) control signal to deploy
        """
        target = goal_dict["target"]
        joint_pos = control_dict["joint_position"][self.dof_idx]
        
        # Choose what to do based on control mode
        if self._mode == "binary":
            # Use max control signal
<<<<<<< HEAD
            u = (
                self._control_limits[ControlType.get_type(self._motor_type)][1][self.dof_idx]
                if target[0] >= 0.0
                else self._control_limits[ControlType.get_type(self._motor_type)][0][self.dof_idx]
            )

        elif self._mode == "ternary":
            if target[0] > 0.33:
                u = self._control_limits[ControlType.get_type(self._motor_type)][1][self.dof_idx]
            elif target[0] < -0.33:
                u = self._control_limits[ControlType.get_type(self._motor_type)][0][self.dof_idx]
            else:
                u = control_dict["joint_{}".format(self._motor_type)][self.dof_idx]

        # If we're using delta commands, add this value
        elif self._mode == "smooth_delta":
            # Compute the base value for the command.
            base_value = control_dict["joint_{}".format(self._motor_type)][self.dof_idx]

            # Apply the command to the base value.
            u = base_value + target[0]

        # Otherwise, control is simply the command itself        
=======
            if target[0] >= 0.0:
                u = self._control_limits[ControlType.get_type(self._motor_type)][1][self.dof_idx] \
                    if self._open_qpos is None else self._open_qpos
            else:
                u = self._control_limits[ControlType.get_type(self._motor_type)][0][self.dof_idx] \
                    if self._closed_qpos is None else self._closed_qpos
>>>>>>> multiple-envs
        else:
            # Use continuous signal
            u = target

        # If we're near the joint limits and we're using velocity / torque control, we zero out the action
        if self._motor_type in {"velocity", "torque"}:
            violate_upper_limit = (
                joint_pos > self._control_limits[ControlType.POSITION][1][self.dof_idx] - self._limit_tolerance
            )
            violate_lower_limit = (
                joint_pos < self._control_limits[ControlType.POSITION][0][self.dof_idx] + self._limit_tolerance
            )
            violation = np.logical_or(violate_upper_limit * (u > 0), violate_lower_limit * (u < 0))
            u *= ~violation

        # Update whether we're grasping or not
        self._update_grasping_state(control_dict=control_dict)

        # Return control
        return u

    def _update_grasping_state(self, control_dict):
        """
        Updates internal inferred grasping state of the gripper being controlled by this gripper controller

        Args:
            control_dict (dict): dictionary that should include any relevant keyword-mapped
                states necessary for controller computation. Must include the following keys:

                    joint_position: Array of current joint positions
                    joint_velocity: Array of current joint velocities
        """
        # Calculate grasping state based on mode of this controller

        # Independent mode of MultiFingerGripperController does not have any good heuristics to determine is_grasping
        if self._mode == "independent":
            is_grasping = IsGraspingState.UNKNOWN

        # No control has been issued before -- we assume not grasping
        elif self._control is None:
            is_grasping = IsGraspingState.FALSE

        else:
            assert m.POS_TOLERANCE > self._limit_tolerance, (
                "Joint position tolerance for is_grasping heuristics checking is smaller than or equal to the "
                "gripper controller's tolerance of zero-ing out velocities, which makes the heuristics invalid."
            )

            finger_pos = control_dict["joint_position"][self.dof_idx]

            # For joint position control, if the desired positions are the same as the current positions, is_grasping unknown
            if (
                    self._motor_type == "position"
                    and np.mean(np.abs(finger_pos - self._control)) < m.POS_TOLERANCE
            ):
                is_grasping = IsGraspingState.UNKNOWN

            # For joint velocity / torque control, if the desired velocities / torques are zeros, is_grasping unknown
            elif (
                    self._motor_type in {"velocity", "torque"}
                    and np.mean(np.abs(self._control)) < m.VEL_TOLERANCE
            ):
                is_grasping = IsGraspingState.UNKNOWN

            # Otherwise, the last control signal intends to "move" the gripper
            else:
                finger_vel = control_dict["joint_velocity"][self.dof_idx]
                min_pos = self._control_limits[ControlType.POSITION][0][self.dof_idx]
                max_pos = self._control_limits[ControlType.POSITION][1][self.dof_idx]

                # Make sure we don't have any invalid values (i.e.: fingers should be within the limits)
                assert np.all(
                    (min_pos <= finger_pos) * (finger_pos <= max_pos)
                ), f"Got invalid finger joint positions when checking for grasp! " \
                   f"min: {min_pos}, max: {max_pos}, finger_pos: {finger_pos}"

                # Check distance from both ends of the joint limits
                dist_from_lower_limit = finger_pos - min_pos
                dist_from_upper_limit = max_pos - finger_pos

                # If the joint positions are not near the joint limits with some tolerance (m.POS_TOLERANCE)
                valid_grasp_pos = (
                        np.mean(dist_from_lower_limit) > m.POS_TOLERANCE
                        and np.mean(dist_from_upper_limit) > m.POS_TOLERANCE
                )

                # And the joint velocities are close to zero with some tolerance (m.VEL_TOLERANCE)
                valid_grasp_vel = np.all(np.abs(finger_vel) < m.VEL_TOLERANCE)

                # Then the gripper is grasping something, which stops the gripper from reaching its desired state
                is_grasping = (
                    IsGraspingState.TRUE if valid_grasp_pos and valid_grasp_vel else IsGraspingState.FALSE
                )

        # Store calculated state
        self._is_grasping = is_grasping

    def compute_no_op_goal(self, control_dict):
        # Just use a zero vector
        return dict(target=np.zeros(self.command_dim))

    def _get_goal_shapes(self):
        return dict(target=(self.command_dim,))

    def is_grasping(self):
        # Return cached value
        return self._is_grasping

    @property
    def control_type(self):
        return ControlType.get_type(type_str=self._motor_type)

    @property
    def command_dim(self):
        return len(self.dof_idx) if self._mode == "independent" else 1
