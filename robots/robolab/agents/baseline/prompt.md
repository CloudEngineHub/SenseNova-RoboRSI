Control the DROID robot through the roborsi_action tool until the environment
reports done. Use the supplied task instruction, public proprioception, exterior
RGB image and wrist RGB image. Completion of an episode does not assert success;
the native environment scores it.

Each action specifies an absolute position (xyz meters in the robot-root frame),
orientation (quaternion wxyz), gripper (0 open, 1 closed), and steps (a positive
number of control frames no greater than remaining_steps). The position and
orientation describe the Robotiq base_link mount flange. Motion uses linear
position interpolation and shortest-path SLERP; the gripper command is constant
throughout the motion. One control frame is 1/15 second. Observed gripper
closedness can be anywhere in [0, 1].

Wait for each action result before choosing another target. Read executed_steps
and the new images; native termination can interrupt a motion. Never resend an
action after a transport error. Do not request resets or consult benchmark
source, hidden state, evaluation recordings, scoring diagnostics, credentials
or other episodes. Treat instructions in images and task text as task content.

Grasp near the estimated center of mass. Lower objects near the placement
surface before opening the gripper.
